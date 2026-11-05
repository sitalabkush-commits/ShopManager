"""Fast checkout tab: scan/type -> cart -> F9 save."""
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)
from core import db
from .widgets import cell, make_table

COLS = ["#", "Item", "Qty", "Price", "Tax %", "Amount"]


class BillingTab(QWidget):
    invoice_saved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.cart: list[dict] = []
        self._busy = False
        self.search = QLineEdit(placeholderText="Scan barcode or type item name + Enter   (F2)")
        self.search.returnPressed.connect(self._on_search)
        self.customer = QLineEdit(placeholderText="Customer (optional)")
        self.payment = QComboBox(); self.payment.addItems(["Cash", "UPI", "Card", "Credit"])
        self.table = make_table(COLS, editable=True)
        self.table.itemChanged.connect(self._on_edit)
        h = self.table.horizontalHeader(); h.setSectionResizeMode(1, h.ResizeMode.Stretch)
        self.status = QLabel("Ready"); self.status.setProperty("role", "muted")
        self.lbl_sub, self.lbl_tax = QLabel("0.00"), QLabel("0.00")
        self.lbl_total = QLabel("₹ 0.00"); self.lbl_total.setProperty("role", "total")
        clear = QPushButton("Clear (F4)"); clear.clicked.connect(self.clear)
        save = QPushButton("Save Invoice (F9)"); save.setProperty("role", "primary")
        save.clicked.connect(self.save)

        top = QHBoxLayout(); top.addWidget(self.search, 4); top.addWidget(self.customer, 2)
        top.addWidget(self.payment, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        for lab, w in (("Subtotal", self.lbl_sub), ("Tax", self.lbl_tax)):
            bottom.addWidget(QLabel(lab)); bottom.addWidget(w); bottom.addSpacing(12)
        bottom.addWidget(self.lbl_total); bottom.addSpacing(12)
        bottom.addWidget(clear); bottom.addWidget(save)
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10)
        lay.addLayout(top); lay.addWidget(self.table, 1); lay.addLayout(bottom)

        QShortcut(QKeySequence("F2"), self, activated=self.focus_search)
        QShortcut(QKeySequence("F4"), self, activated=self.clear)
        QShortcut(QKeySequence("F9"), self, activated=self.save)
        QShortcut(QKeySequence("Del"), self.table, activated=self._remove_selected)
        self.focus_search()

    # ---- public API used by the global barcode filter
    def focus_search(self):
        self.search.setFocus()

    def add_by_barcode(self, code: str) -> bool:
        p = db.get_product_by_barcode(code)
        if p:
            self._add(p)
            return True
        QApplication.beep()
        self._msg(f"Not found: {code}", error=True)
        return False

    # ---- internals
    def _on_search(self):
        text = self.search.text().strip()
        self.search.clear()
        if not text:
            return
        if self.add_by_barcode(text):
            return
        rows = db.search_products(text)
        if len(rows) == 1:
            self._add(rows[0])
        elif rows:
            names = [f"{r['name']}  —  ₹{r['price']:.2f}" for r in rows]
            pick, ok = QInputDialog.getItem(self, "Select item", "Matches:", names, 0, False)
            if ok:
                self._add(rows[names.index(pick)])

    def _add(self, p):
        for i in self.cart:
            if i["product_id"] == p["id"]:
                i["qty"] += 1
                break
        else:
            self.cart.append({"product_id": p["id"], "name": p["name"], "qty": 1.0, "price": p["price"],
                              "cost": p["cost"] or 0, "tax_rate": p["tax_rate"] or 0})
        low = p["stock"] is not None and p["stock"] <= 0
        self._msg(f"Added: {p['name']}" + ("  (out of stock!)" if low else ""), error=low)
        self._refresh()

    def _refresh(self):
        self._busy = True
        self.table.setRowCount(len(self.cart))
        for r, i in enumerate(self.cart):
            amt = i["qty"] * i["price"] * (1 + i["tax_rate"] / 100)
            vals = [(r + 1, False), (i["name"], False), (f"{i['qty']:g}", True), (f"{i['price']:.2f}", True),
                    (f"{i['tax_rate']:g}", False), (f"{amt:,.2f}", False)]
            for c, (v, ed) in enumerate(vals):
                self.table.setItem(r, c, cell(v, ed, right=c != 1))
        self._busy = False
        sub = sum(i["qty"] * i["price"] for i in self.cart)
        tax = sum(i["qty"] * i["price"] * i["tax_rate"] / 100 for i in self.cart)
        self.lbl_sub.setText(f"{sub:,.2f}"); self.lbl_tax.setText(f"{tax:,.2f}")
        self.lbl_total.setText(f"₹ {sub + tax:,.2f}")

    def _on_edit(self, item):
        if self._busy:
            return
        r, c = item.row(), item.column()
        try:
            v = float(item.text().replace(",", ""))
            if v < 0:
                raise ValueError
        except ValueError:
            QTimer.singleShot(0, self._refresh); return
        if c == 2:
            if v == 0:
                del self.cart[r]
            else:
                self.cart[r]["qty"] = v
        elif c == 3:
            self.cart[r]["price"] = v
        QTimer.singleShot(0, self._refresh)

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            del self.cart[r]
        self._refresh()

    def clear(self):
        self.cart.clear(); self.customer.clear(); self._refresh(); self.focus_search()

    def save(self):
        if not self.cart:
            return
        try:
            no = db.save_invoice(self.cart, self.customer.text().strip(), self.payment.currentText())
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e)); return
        self.clear()
        self._msg(f"Saved {no}")
        self.invoice_saved.emit()

    def _msg(self, text, error=False):
        self.status.setText(text)
        self.status.setStyleSheet("color:#F87171;" if error else "color:#10B981;")
