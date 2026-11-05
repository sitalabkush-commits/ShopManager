"""Inventory: editable grid straight on the products table (QSqlTableModel)."""
from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlTableModel
from PyQt6.QtWidgets import (QCheckBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton,
                             QTableView, QVBoxLayout, QWidget)

HEADERS = {"barcode": "Barcode", "name": "Item name", "price": "Sale price", "cost": "Cost",
           "stock": "Stock", "tax_rate": "Tax %"}


class InventoryTab(QWidget):
    def __init__(self):
        super().__init__()
        self.model = QSqlTableModel(self)
        self.model.setTable("products")
        self.model.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)
        self.model.setSort(self.model.fieldIndex("name"), Qt.SortOrder.AscendingOrder)
        for col, title in HEADERS.items():
            self.model.setHeaderData(self.model.fieldIndex(col), Qt.Orientation.Horizontal, title)
        self.model.select()
        self.view = QTableView(); self.view.setModel(self.model)
        self.view.setAlternatingRowColors(True); self.view.setSortingEnabled(False)
        self.view.setColumnHidden(self.model.fieldIndex("id"), True)
        self.view.verticalHeader().setDefaultSectionSize(26); self.view.verticalHeader().hide()
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setColumnWidth(self.model.fieldIndex("name"), 320)

        self.search = QLineEdit(placeholderText="Search name / barcode")
        self.search.textChanged.connect(self._filter)
        self.low = QCheckBox("Low stock (≤ 5)"); self.low.toggled.connect(self._filter)
        add = QPushButton("+ Add item"); add.setProperty("role", "primary"); add.clicked.connect(self._add)
        rm = QPushButton("Delete"); rm.setProperty("role", "danger"); rm.clicked.connect(self._delete)
        bar = QHBoxLayout(); bar.addWidget(self.search, 1); bar.addWidget(self.low)
        bar.addWidget(add); bar.addWidget(rm)
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10)
        lay.addLayout(bar); lay.addWidget(self.view)

    def refresh(self):
        self.model.select()

    def _filter(self, *_):
        t = self.search.text().strip().replace("'", "''")
        parts = []
        if t:
            parts.append(f"(name LIKE '%{t}%' OR barcode LIKE '%{t}%')")
        if self.low.isChecked():
            parts.append("stock <= 5")
        self.model.setFilter(" AND ".join(parts))

    def _add(self):
        rec = self.model.record()
        rec.setValue("name", "New item"); rec.setValue("stock", 0)
        if not self.model.insertRecord(-1, rec) or not self.model.submitAll():
            QMessageBox.warning(self, "Add failed", self.model.lastError().text())
        self.model.select()

    def _delete(self):
        rows = {i.row() for i in self.view.selectionModel().selectedIndexes()}
        if rows and QMessageBox.question(self, "Delete", f"Delete {len(rows)} item(s)?") \
                == QMessageBox.StandardButton.Yes:
            for r in sorted(rows, reverse=True):
                self.model.removeRow(r)
            self.model.submitAll(); self.model.select()
