"""Billing history: last 30 days by default; archive is searched on demand."""
from PyQt6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QWidget)
from core import db
from .widgets import cell, make_table

COLS = ["Invoice", "Date", "Customer", "Payment", "Total", "Profit", "Source"]


class ItemsDialog(QDialog):
    def __init__(self, inv_no, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(inv_no); self.resize(560, 320)
        t = make_table(["Item", "Qty", "Price", "Tax %"])
        t.setRowCount(len(rows))
        for r, x in enumerate(rows):
            for c, v in enumerate((x["name"], f"{x['qty']:g}", f"{x['price']:.2f}", f"{x['tax_rate']:g}")):
                t.setItem(r, c, cell(v, right=c > 0))
        QVBoxLayout(self).addWidget(t)


class HistoryTab(QWidget):
    def __init__(self):
        super().__init__()
        self.search = QLineEdit(placeholderText="Search invoice no / customer")
        self.search.returnPressed.connect(self.refresh)
        self.arch = QCheckBox("Include archive (older than 30 days)")
        self.arch.toggled.connect(self.refresh)
        go = QPushButton("Search"); go.setProperty("role", "primary"); go.clicked.connect(self.refresh)
        self.info = QLabel(); self.info.setProperty("role", "muted")
        self.table = make_table(COLS)
        self.table.doubleClicked.connect(self._open)
        self.rows = []
        bar = QHBoxLayout(); bar.addWidget(self.search, 1); bar.addWidget(self.arch); bar.addWidget(go)
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10)
        lay.addLayout(bar); lay.addWidget(self.table, 1); lay.addWidget(self.info)
        self.refresh()

    def refresh(self, *_):
        term = self.search.text().strip()
        rows = db.search_invoices(term, self.arch.isChecked())
        note = "Showing last 30 days."
        if term and not rows and not self.arch.isChecked():       # fall back to the archive automatically
            rows = db.search_invoices(term, True)
            note = "No match in last 30 days - showing archive results."
        elif self.arch.isChecked():
            note = "Showing active + archived invoices."
        self.rows = rows
        self.table.setRowCount(len(rows))
        for r, x in enumerate(rows):
            vals = (x["invoice_no"], x["date"], x["customer"], x["payment"],
                    f"{x['total']:,.2f}", f"{x['profit']:,.2f}", x["source"])
            for c, v in enumerate(vals):
                self.table.setItem(r, c, cell(v, right=c in (4, 5)))
        self.info.setText(f"{note}  {len(rows)} invoice(s).  Double-click for items.")

    def _open(self, idx):
        x = self.rows[idx.row()]
        ItemsDialog(x["invoice_no"], db.invoice_items(x["id"], x["source"] == "Archive"), self).exec()
