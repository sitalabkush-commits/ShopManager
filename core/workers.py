"""Background QThreads. Each opens (and closes) its own SQLite connection."""
from PyQt6.QtCore import QThread, pyqtSignal
from . import backup, db, ocr


class ArchiveWorker(QThread):
    done, failed = pyqtSignal(int), pyqtSignal(str)

    def run(self):
        try:
            self.done.emit(db.archive_old())
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            db.close_conn()


class BackupWorker(QThread):
    done, failed = pyqtSignal(str), pyqtSignal(str)

    def __init__(self, force: bool = False):
        super().__init__()
        self.force = force

    def run(self):
        try:
            p = backup.make_backup(self.force)
            self.done.emit(str(p) if p else "")
        except Exception as e:
            self.failed.emit(str(e))


class OcrWorker(QThread):
    done, failed = pyqtSignal(list), pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            self.done.emit(ocr.get_provider().parse(self.path))
        except Exception as e:
            self.failed.emit(str(e))
