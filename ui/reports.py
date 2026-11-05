"""12-month summary: one aggregate query over active + archive."""
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget
from core import db
from .widgets import KpiCard, cell, make_table


class ReportsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.k = {n: KpiCard(n) for n in ("Revenue (12 mo)", "Profit (12 mo)", "Tax (12 mo)", "Invoices")}
        self.table = make_table(["Month", "Invoices", "Units sold", "Revenue", "Tax", "Profit"])
        btn = QPushButton("Refresh"); btn.clicked.connect(self.refresh)
        bar = QHBoxLayout()
        for c in self.k.values():
            bar.addWidget(c)
        bar.addWidget(btn)
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10)
        lay.addLayout(bar); lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        rows = db.monthly_summary(12)
        self.table.setRowCount(len(rows))
        for r, x in enumerate(rows):
            vals = (x["month"], x["invoices"], f"{x['units'] or 0:g}", f"{x['revenue'] or 0:,.2f}",
                    f"{x['tax'] or 0:,.2f}", f"{x['profit'] or 0:,.2f}")
            for c, v in enumerate(vals):
                self.table.setItem(r, c, cell(v, right=c > 0))
        s = lambda key: sum((x[key] or 0) for x in rows)
        self.k["Revenue (12 mo)"].set(f"₹ {s('revenue'):,.2f}")
        self.k["Profit (12 mo)"].set(f"₹ {s('profit'):,.2f}")
        self.k["Tax (12 mo)"].set(f"₹ {s('tax'):,.2f}")
        self.k["Invoices"].set(f"{int(s('invoices')):,}")
