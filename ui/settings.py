"""Settings: general + PIN-protected raw database editor."""
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtSql import QSqlTableModel
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                             QStackedWidget, QTableView, QTabWidget, QVBoxLayout, QWidget)
from core import backup, db
from core.workers import ArchiveWorker, BackupWorker


class DbAdminView(QWidget):
    data_changed = pyqtSignal()
    AUTOLOCK_MS = 5 * 60 * 1000

    def __init__(self):
        super().__init__()
        self.stack = QStackedWidget(self)
        QVBoxLayout(self).addWidget(self.stack)
        # -- lock page
        lock = QWidget(); ll = QVBoxLayout(lock)
        self.lock_msg = QLabel(); self.pin = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.pin.setMaximumWidth(220); self.pin.returnPressed.connect(self._unlock)
        b = QPushButton("Unlock"); b.setProperty("role", "primary"); b.setMaximumWidth(220)
        b.clicked.connect(self._unlock)
        for w in (self.lock_msg, self.pin, b):
            ll.addWidget(w)
        ll.addStretch(1)
        # -- admin page
        adm = QWidget(); al = QVBoxLayout(adm)
        self.combo = QComboBox(); self.combo.currentTextChanged.connect(self._open_table)
        self.view = QTableView(); self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setDefaultSectionSize(24)
        bar = QHBoxLayout(); bar.addWidget(QLabel("Table:")); bar.addWidget(self.combo, 1)
        for text, fn, role in (("Reload", self._reload, ""), ("+ Row", self._add, ""),
                               ("Delete row(s)", self._del, "danger"), ("Revert", self._revert, ""),
                               ("Submit changes", self._submit, "primary")):
            btn = QPushButton(text); btn.clicked.connect(fn)
            if role:
                btn.setProperty("role", role)
            bar.addWidget(btn)
        warn = QLabel("Direct edits bypass app validation. A backup is taken before every submit.")
        warn.setProperty("role", "muted")
        al.addLayout(bar); al.addWidget(self.view, 1); al.addWidget(warn)
        self.stack.addWidget(lock); self.stack.addWidget(adm)
        self.model = None
        self.timer = QTimer(self, singleShot=True, timeout=self.lock)
        self.lock()

    def lock(self):
        self.stack.setCurrentIndex(0); self.pin.clear()
        self.lock_msg.setText("Enter admin PIN" if db.has_pin() else "First use: choose an admin PIN (min 4 chars)")

    def hideEvent(self, e):          # leaving the tab locks the editor
        self.lock(); super().hideEvent(e)

    def _unlock(self):
        pin = self.pin.text()
        if not db.has_pin():
            if len(pin) < 4:
                return
            db.set_pin(pin)
        elif not db.verify_pin(pin):
            self.lock_msg.setText("Wrong PIN"); self.pin.clear(); return
        names = [r["name"] for r in db.conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        self.combo.blockSignals(True); self.combo.clear(); self.combo.addItems(
            [n for n in names if n != "settings"]); self.combo.blockSignals(False)   # hide PIN hash
        self.stack.setCurrentIndex(1); self._open_table(self.combo.currentText())
        self.timer.start(self.AUTOLOCK_MS)

    def _open_table(self, name):
        if not name:
            return
        self.model = QSqlTableModel(self)
        self.model.setTable(name)
        self.model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        self.model.select(); self.view.setModel(self.model)
        self.timer.start(self.AUTOLOCK_MS)

    def _reload(self):
        self.model.select()

    def _add(self):
        self.model.insertRow(self.model.rowCount())

    def _del(self):
        for r in sorted({i.row() for i in self.view.selectionModel().selectedIndexes()}, reverse=True):
            self.model.removeRow(r)

    def _revert(self):
        self.model.revertAll()

    def _submit(self):
        if QMessageBox.question(self, "Submit", "Write pending changes to the database?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            backup.make_backup(force=True)
        except Exception as e:
            QMessageBox.critical(self, "Backup failed", f"Aborted (no changes written).\n{e}"); return
        if self.model.submitAll():
            self.data_changed.emit()
        else:
            QMessageBox.critical(self, "Error", self.model.lastError().text()); self.model.revertAll()


class SettingsTab(QWidget):
    data_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._w = []
        self.shop = QLineEdit(db.get_setting("shop_name")); self.shop.setPlaceholderText("Shop name")
        save = QPushButton("Save"); save.setProperty("role", "primary")
        save.clicked.connect(lambda: db.set_setting("shop_name", self.shop.text().strip()))
        bk = QPushButton("Backup now"); bk.clicked.connect(self._backup)
        ar = QPushButton("Archive now"); ar.clicked.connect(self._archive)
        self.msg = QLabel(); self.msg.setProperty("role", "muted")
        gen = QWidget(); g = QVBoxLayout(gen)
        row = QHBoxLayout(); row.addWidget(self.shop, 1); row.addWidget(save)
        row2 = QHBoxLayout(); row2.addWidget(bk); row2.addWidget(ar); row2.addStretch(1)
        g.addLayout(row); g.addLayout(row2); g.addWidget(self.msg); g.addStretch(1)
        self.admin = DbAdminView(); self.admin.data_changed.connect(self.data_changed)
        tabs = QTabWidget(); tabs.addTab(gen, "General"); tabs.addTab(self.admin, "Database Admin")
        QVBoxLayout(self).addWidget(tabs)

    def _run(self, worker, ok):
        self._w.append(worker)
        worker.done.connect(ok); worker.failed.connect(lambda m: self.msg.setText(f"Error: {m}"))
        worker.finished.connect(lambda: self._w.remove(worker)); worker.start()

    def _backup(self):
        self._run(BackupWorker(force=True), lambda p: self.msg.setText(f"Backup saved: {p}"))

    def _archive(self):
        def ok(n):
            self.msg.setText(f"Archived {n} invoice(s)."); self.data_changed.emit()
        self._run(ArchiveWorker(), ok)
