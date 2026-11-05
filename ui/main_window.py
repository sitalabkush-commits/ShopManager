"""Main window: tabs, global scanner routing, startup/periodic backup + archive."""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from core import db
from core.workers import ArchiveWorker, BackupWorker
from .barcode import BarcodeFilter
from .billing import BillingTab
from .history import HistoryTab
from .inventory import InventoryTab
from .ocr_import import OcrImportTab
from .reports import ReportsTab
from .settings import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(db.get_setting("shop_name") or "ShopManager"); self.resize(1200, 720)
        self.billing, self.inventory, self.history = BillingTab(), InventoryTab(), HistoryTab()
        self.reports, self.ocr, self.settings = ReportsTab(), OcrImportTab(), SettingsTab()
        self.tabs = QTabWidget()
        for w, name in ((self.billing, "Billing"), (self.inventory, "Inventory"),
                        (self.history, "Billing History"), (self.reports, "Reports"),
                        (self.ocr, "OCR Import"), (self.settings, "Settings")):
            self.tabs.addTab(w, name)
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self._on_tab)
        self.billing.invoice_saved.connect(self._refresh_all)
        self.ocr.committed.connect(self.inventory.refresh)
        self.settings.data_changed.connect(self._refresh_all)

        self.scanner = BarcodeFilter(self)
        self.scanner.scanned.connect(self._on_scan)
        QApplication.instance().installEventFilter(self.scanner)

        self._workers: list = []
        QTimer.singleShot(1500, self._maintenance)                    # startup hook (after UI is shown)
        self.timer = QTimer(self, timeout=self._maintenance); self.timer.start(60 * 60 * 1000)  # hourly check

    def _maintenance(self):
        """Daily backup (no-op if today's exists) + archive of >30-day invoices, off the UI thread."""
        for w, ok in ((BackupWorker(), self._backup_done), (ArchiveWorker(), self._archive_done)):
            self._workers.append(w)
            w.done.connect(ok)
            w.failed.connect(lambda m: self.statusBar().showMessage(f"Maintenance error: {m}", 8000))
            w.finished.connect(lambda w=w: self._workers.remove(w))
            w.start()

    def _backup_done(self, path):
        if path:
            self.statusBar().showMessage(f"Daily backup created: {path}", 6000)

    def _archive_done(self, n):
        if n:
            self.statusBar().showMessage(f"Archived {n} old invoice(s)", 6000)
            self.history.refresh()

    def _on_tab(self, i):
        w = self.tabs.widget(i)
        self.scanner.enabled = w not in (self.settings, self.ocr)     # don't hijack editors
        if w is self.inventory:
            self.inventory.refresh()
        elif w is self.history:
            self.history.refresh()
        elif w is self.reports:
            self.reports.refresh()
        elif w is self.billing:
            self.billing.focus_search()

    def _on_scan(self, code):
        if self.tabs.currentWidget() is not self.billing:
            self.tabs.setCurrentWidget(self.billing)
        self.billing.add_by_barcode(code)

    def _refresh_all(self):
        self.inventory.refresh(); self.history.refresh(); self.reports.refresh()
