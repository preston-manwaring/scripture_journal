from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from backend.database import get_connection
from backend.services.tsv_importer import import_all, needs_import
from ui.themes import DARK, OVERLAY, SUBTEXT, TEXT, ACCENT, DIM
import sys


class _ImportWorker(QThread):
    progress = pyqtSignal(str)   # status message
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            conn = get_connection()
            # Monkey-patch print so TSV importer messages go through our signal
            import builtins
            _orig_print = builtins.print

            def _emit_print(*args, **kwargs):
                msg = " ".join(str(a) for a in args)
                self.progress.emit(msg)

            builtins.print = _emit_print
            try:
                import_all(conn)
            finally:
                builtins.print = _orig_print
                conn.close()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class ImportDialog(QDialog):
    import_done = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("First-run Setup")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Importing scripture data...")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT};")
        layout.addWidget(title)

        self._status = QLabel("Preparing...")
        self._status.setStyleSheet(f"color: {SUBTEXT}; font-size: 12px;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background: {OVERLAY}; border-radius: 4px; height: 8px; }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
        """)
        layout.addWidget(self._bar)

        note = QLabel("This only happens once. The app will open automatically when done.")
        note.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.setStyleSheet(f"QDialog {{ background: {DARK}; }}")

        self._worker = _ImportWorker()
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._status.setText(msg)

    def _on_done(self):
        self._bar.setRange(0, 1)
        self._bar.setValue(1)
        self._status.setText("Done!")
        self.import_done.emit()
        self.accept()

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
