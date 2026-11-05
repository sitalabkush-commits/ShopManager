"""Global hardware-scanner capture. Scanners type very fast and end with Enter."""
import time
from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractSpinBox, QApplication, QLineEdit, QPlainTextEdit, QTextEdit)

_TEXTY = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)


class BarcodeFilter(QObject):
    """Install on QApplication. Humans type >50 ms between keys, scanners <~30 ms."""
    scanned = pyqtSignal(str)

    def __init__(self, parent=None, max_gap_ms: float = 50, min_len: int = 4):
        super().__init__(parent)
        self.max_gap, self.min_len, self.enabled = max_gap_ms, min_len, True
        self._buf, self._last = "", 0.0

    def eventFilter(self, obj, ev):
        if not self.enabled or ev.type() != QEvent.Type.KeyPress:
            return False
        now = time.monotonic() * 1000
        key, txt = ev.key(), ev.text()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            code, self._buf = self._buf, ""
            if len(code) >= self.min_len:                  # buffer only survives while keys are fast
                self._strip_leaked(code)
                self.scanned.emit(code)
                return True                                # swallow Enter (no accidental form submit)
            return False
        mods = ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                                 | Qt.KeyboardModifier.MetaModifier)
        if txt and txt.isprintable() and not mods:
            if self._buf and now - self._last > self.max_gap:
                self._buf = ""                             # too slow -> human typing, restart
            self._buf += txt
            self._last = now
            # Mid-scan keystrokes must not trigger table editors/shortcuts on non-text widgets.
            if len(self._buf) >= 2 and not isinstance(QApplication.focusWidget(), _TEXTY):
                return True
        else:
            self._buf = ""
        return False

    @staticmethod
    def _strip_leaked(code: str) -> None:
        """Characters already typed into a focused QLineEdit are removed after a confirmed scan."""
        w = QApplication.focusWidget()
        if isinstance(w, QLineEdit) and w.text().endswith(code):
            w.setText(w.text()[:-len(code)])
