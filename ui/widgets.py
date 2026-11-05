"""Small shared widgets/helpers."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QLabel, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)


def make_table(headers, editable=False) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(26)          # high-density rows
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setShowGrid(False)
    if not editable:
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def cell(text, editable=False, right=False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    flags = it.flags()
    it.setFlags(flags | Qt.ItemFlag.ItemIsEditable if editable else flags & ~Qt.ItemFlag.ItemIsEditable)
    if right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return it


class KpiCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setProperty("role", "card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        t = QLabel(title); t.setProperty("role", "muted")
        self.value = QLabel("-"); self.value.setProperty("role", "kpi")
        lay.addWidget(t); lay.addWidget(self.value)

    def set(self, text: str) -> None:
        self.value.setText(text)
