"""Global black/emerald theme (Fusion + QPalette + QSS)."""
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

BG, CARD, BORDER = "#121212", "#1E1E1E", "#2A2A2A"
TEXT, MUTED = "#EDEDED", "#9E9E9E"
GREEN, GREEN_H, BLUE = "#10B981", "#059669", "#60A5FA"

QSS = f"""
QWidget {{ background:{BG}; color:{TEXT}; font-family:"Segoe UI","Inter",sans-serif; font-size:12px; }}
QFrame[role="card"] {{ background:{CARD}; border:1px solid {BORDER}; border-radius:8px; }}
QFrame[role="card"] QLabel {{ background:transparent; }}
QTabWidget::pane {{ border:0; }}
QTabBar::tab {{ background:{BG}; color:{MUTED}; padding:8px 18px; border-bottom:2px solid transparent; }}
QTabBar::tab:hover {{ color:#fff; }}
QTabBar::tab:selected {{ color:#fff; border-bottom:2px solid {GREEN}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
  background:{CARD}; border:1px solid #333; border-radius:5px; padding:4px 6px;
  selection-background-color:{BLUE}; selection-color:#000; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border:1px solid {BLUE}; }}
QComboBox QAbstractItemView {{ background:{CARD}; selection-background-color:#1D3B5C; }}
QPushButton {{ background:#2A2A2A; border:1px solid #333; border-radius:5px; padding:5px 12px; }}
QPushButton:hover {{ background:#353535; }}
QPushButton:disabled {{ color:#666; }}
QPushButton[role="primary"] {{ background:{GREEN}; color:#04130D; border:0; font-weight:600; }}
QPushButton[role="primary"]:hover {{ background:{GREEN_H}; }}
QPushButton[role="danger"] {{ background:#3A1B1B; color:#F87171; border:1px solid #5A2A2A; }}
QTableView, QTableWidget {{ background:{CARD}; alternate-background-color:#191919; gridline-color:{BORDER};
  border:1px solid {BORDER}; selection-background-color:#1D3B5C; selection-color:#fff; }}
QHeaderView::section {{ background:#242424; color:{MUTED}; border:0; border-right:1px solid {BORDER};
  padding:5px; font-weight:600; }}
QLabel[role="total"] {{ font-size:26px; font-weight:700; color:{GREEN}; }}
QLabel[role="kpi"] {{ font-size:18px; font-weight:700; color:{BLUE}; }}
QLabel[role="muted"] {{ color:{MUTED}; }}
QScrollBar:vertical {{ background:{BG}; width:10px; }}
QScrollBar::handle:vertical {{ background:#3A3A3A; border-radius:5px; min-height:24px; }}
QScrollBar:horizontal {{ background:{BG}; height:10px; }}
QScrollBar::handle:horizontal {{ background:#3A3A3A; border-radius:5px; min-width:24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QStatusBar {{ color:{MUTED}; }}
QToolTip {{ background:{CARD}; color:{TEXT}; border:1px solid #333; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")  # consistent base so the palette applies to native dialogs too
    p = QPalette()
    for role, col in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.Base, CARD),
                      (QPalette.ColorRole.AlternateBase, "#191919"), (QPalette.ColorRole.Button, "#2A2A2A"),
                      (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.WindowText, TEXT),
                      (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.ToolTipBase, CARD),
                      (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.Highlight, "#1D3B5C"),
                      (QPalette.ColorRole.HighlightedText, "#FFFFFF")):
        p.setColor(role, QColor(col))
    app.setPalette(p)
    app.setStyleSheet(QSS)
