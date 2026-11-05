import sys
from PyQt6.QtSql import QSqlDatabase
from PyQt6.QtWidgets import QApplication, QMessageBox
from core import db
from ui.main_window import MainWindow
from ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    try:
        db.init_db()
    except Exception as e:
        QMessageBox.critical(None, "Database error", str(e)); return 1
    qdb = QSqlDatabase.addDatabase("QSQLITE")                # used by QSqlTableModel grids
    qdb.setDatabaseName(str(db.DB_PATH))
    qdb.setConnectOptions("QSQLITE_BUSY_TIMEOUT=5000")
    if not qdb.open():
        QMessageBox.critical(None, "Database error", qdb.lastError().text()); return 1
    win = MainWindow(); win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
