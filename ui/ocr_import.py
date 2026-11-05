"""OCR import: parse -> staging bucket -> review/edit -> explicit 'Confirm & Commit'."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)
from core import ocr
from core.workers import OcrWorker
from .widgets import cell, make_table

HEAD = ["Barcode", "Name", "Qty", "Cost", "Sell price", "Tax %"]


class OcrImportTab(QWidget):
    committed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._loading, self._worker = False, None
        self.table = make_table(HEAD, editable=True)
        self.table.itemChanged.connect(self._on_changed)
        h = self.table.horizontalHeader(); h.setSectionResizeMode(1, h.ResizeMode.Stretch)
        self.btn_import = QPushButton("Import bill image…"); self.btn_import.clicked.connect(self._import)
        add = QPushButton("+ Row"); add.clicked.connect(lambda: (ocr.add_blank(), self.load()))
        rm = QPushButton("Delete selected"); rm.clicked.connect(self._delete)
        dis = QPushButton("Discard all"); dis.setProperty("role", "danger"); dis.clicked.connect(self._discard)
        ok = QPushButton("Confirm & Commit"); ok.setProperty("role", "primary"); ok.clicked.connect(self._commit)
        self.info = QLabel("Staging bucket - nothing is saved to inventory until you confirm.")
        self.info.setProperty("role", "muted")
        bar = QHBoxLayout()
        for w in (self.btn_import, add, rm, dis):
            bar.addWidget(w)
        bar.addStretch(1); bar.addWidget(ok)
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10)
        lay.addLayout(bar); lay.addWidget(self.table, 1); lay.addWidget(self.info)
        self.load()

    def load(self):
        rows = ocr.load_staging()
        self._loading = True
        self.table.setRowCount(len(rows))
        for r, x in enumerate(rows):
            for c, f in enumerate(ocr.FIELDS):
                v = x[f]
                it = cell(f"{v:g}" if isinstance(v, float) else v, True, right=c > 1)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, x["id"])
                self.table.setItem(r, c, it)
        self._loading = False
        self.info.setText(f"{len(rows)} row(s) staged. Review/edit, then Confirm & Commit.")

    def _on_changed(self, item):
        if self._loading:
            return
        rid = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        f, txt = ocr.FIELDS[item.column()], item.text().strip()
        try:
            ocr.update_field(rid, f, float(txt.replace(",", "")) if item.column() >= 2 else txt)
            item.setBackground(QBrush())
        except ValueError:
            item.setBackground(QBrush(QColor("#5A2A2A")))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select bill", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if not path:
            return
        self.btn_import.setEnabled(False); self.info.setText("Reading bill…")
        self._worker = OcrWorker(path)
        self._worker.done.connect(lambda rows, p=path: self._parsed(rows, p))
        self._worker.failed.connect(self._failed)
        self._worker.start()

    def _parsed(self, rows, path):
        self.btn_import.setEnabled(True)
        if not rows:
            QMessageBox.information(self, "OCR", "No line items detected. Add rows manually."); return
        ocr.stage_rows(rows, path); self.load()

    def _failed(self, msg):
        self.btn_import.setEnabled(True)
        QMessageBox.critical(self, "OCR failed", msg); self.load()

    def _selected_ids(self):
        rows = {i.row() for i in self.table.selectedItems()}
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def _delete(self):
        ids = self._selected_ids()
        if ids:
            ocr.delete_rows(ids); self.load()

    def _discard(self):
        if self.table.rowCount() and QMessageBox.question(self, "Discard", "Discard the whole bucket?") \
                == QMessageBox.StandardButton.Yes:
            ocr.discard_all(); self.load()

    def _commit(self):
        rows = []
        for r in range(self.table.rowCount()):
            t = [self.table.item(r, c).text().strip() for c in range(6)]
            try:
                d = {"id": self.table.item(r, 0).data(Qt.ItemDataRole.UserRole), "barcode": t[0], "name": t[1],
                     "qty": float(t[2]), "cost": float(t[3]), "price": float(t[4]), "tax_rate": float(t[5])}
            except ValueError:
                QMessageBox.warning(self, "Check row", f"Row {r + 1}: invalid number."); return
            if not d["name"] or d["qty"] <= 0 or min(d["cost"], d["price"], d["tax_rate"]) < 0:
                QMessageBox.warning(self, "Check row", f"Row {r + 1}: name/qty/amounts are invalid."); return
            rows.append(d)
        if not rows:
            return
        if QMessageBox.question(self, "Confirm & Commit", f"Write {len(rows)} item(s) to inventory "
                                "(stock will be increased)?") != QMessageBox.StandardButton.Yes:
            return
        try:
            n = ocr.commit(rows)
        except Exception as e:
            QMessageBox.critical(self, "Commit failed", f"Nothing was saved.\n{e}"); return
        self.load(); self.committed.emit()
        QMessageBox.information(self, "Done", f"{n} item(s) committed.")
