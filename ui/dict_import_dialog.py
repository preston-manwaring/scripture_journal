"""First-run dialog that imports the Webster's dictionary SQL files into db/dict.db."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import QThread, pyqtSignal, Qt

from backend.services.dict_importer import import_all
from ui.themes import DARK, OVERLAY, SUBTEXT, TEXT, ACCENT, DIM


class _DictWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            import_all(progress_cb=self.progress.emit)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class DictImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dictionary Setup")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Importing dictionary data…")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT};")
        layout.addWidget(title)

        self._status = QLabel("Preparing…")
        self._status.setStyleSheet(f"color: {SUBTEXT}; font-size: 12px;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background: {OVERLAY}; border-radius: 4px; height: 8px; }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
        """)
        layout.addWidget(self._bar)

        note = QLabel(
            "Building Webster's 1828, 1844, and 1913 dictionaries from local files.\n"
            "This only happens once and may take about a minute."
        )
        note.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.setStyleSheet(f"QDialog {{ background: {DARK}; }}")

        self._worker = _DictWorker()
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._status.setText(msg)

    def _on_done(self):
        self._bar.setRange(0, 1)
        self._bar.setValue(1)
        self._status.setText("Dictionary import complete!")
        self.accept()

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        # Allow closing on error so the user isn't stuck
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowCloseButtonHint)
        self.show()
