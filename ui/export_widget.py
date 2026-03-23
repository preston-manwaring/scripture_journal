from __future__ import annotations
import os
import subprocess

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QFrame, QTextEdit,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize
from PyQt6.QtWebEngineWidgets import QWebEngineView

from backend.db_api import EDITIONS, get_books
from backend.services.latex_generator import generate, OUTPUT_DIR
from ui.themes import DARK, SURFACE, ELEVATED, OVERLAY, OVERLAY1, SUBTEXT, TEXT, ACCENT, RED, GREEN

_BTN = "QPushButton {{ background:{bg}; color:{fg}; border:none; border-radius:4px; padding:5px 14px; font-size:12px; }}"
_LABEL = f"color:{SUBTEXT}; font-size:12px;"


def _combo_style() -> str:
    return f"""
        QComboBox {{ background:{OVERLAY}; color:{TEXT}; border:1px solid {OVERLAY1};
            border-radius:4px; padding:3px 6px; font-size:12px; }}
        QComboBox::drop-down {{ border:none; }}
        QComboBox QAbstractItemView {{ background:{OVERLAY}; color:{TEXT};
            selection-background-color:{ACCENT}; }}
    """


def _spin_style() -> str:
    return (
        f"QSpinBox {{ background:{OVERLAY}; color:{TEXT}; border:1px solid {OVERLAY1};"
        f" border-radius:4px; padding:3px 6px; font-size:12px; }}"
    )


class _PdfWorker(QThread):
    done = pyqtSignal(str)   # pdf_path
    error = pyqtSignal(str)

    def __init__(self, tex_path: str):
        super().__init__()
        self._tex = tex_path

    def run(self):
        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode",
                 "-output-directory", OUTPUT_DIR, self._tex],
                capture_output=True, timeout=60,
            )
            # Decode with replacement to avoid UnicodeDecodeError on pdflatex output
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            if result.returncode == 0:
                self.done.emit(os.path.join(OUTPUT_DIR, "export.pdf"))
            else:
                self.error.emit(stdout + stderr)
        except FileNotFoundError:
            self.error.emit("pdflatex not found — install MacTeX or TeX Live.")
        except subprocess.TimeoutExpired:
            self.error.emit("pdflatex timed out after 60 seconds.")
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export to PDF")
        self.setMinimumSize(QSize(720, 600))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setStyleSheet(f"QDialog {{ background:{DARK}; color:{TEXT}; }}")

        self._tex_path: str | None = None
        self._pdf_worker: _PdfWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── Form ──────────────────────────────────────────────────────────────
        form = QFrame()
        form.setStyleSheet(f"QFrame {{ background:{ELEVATED}; border-radius:8px; }}")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Book:"))
        self._book_combo = QComboBox()
        self._book_combo.setStyleSheet(_combo_style())
        self._book_combo.addItems(get_books())
        row1.addWidget(self._book_combo)
        row1.addStretch()
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Chapters:"))
        self._ch_start = QSpinBox()
        self._ch_start.setRange(1, 99)
        self._ch_start.setValue(1)
        self._ch_start.setStyleSheet(_spin_style())
        row2.addWidget(self._ch_start)
        row2.addWidget(QLabel("to"))
        self._ch_end = QSpinBox()
        self._ch_end.setRange(1, 99)
        self._ch_end.setValue(1)
        self._ch_end.setStyleSheet(_spin_style())
        row2.addWidget(self._ch_end)
        row2.addStretch()
        form_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Edition:"))
        self._ed_combo = QComboBox()
        self._ed_combo.addItems(EDITIONS)
        self._ed_combo.setCurrentText("2013")
        self._ed_combo.setStyleSheet(_combo_style())
        row3.addWidget(self._ed_combo)
        row3.addStretch()
        form_layout.addLayout(row3)

        self._inc_commentary = QCheckBox("Include commentary")
        self._inc_commentary.setChecked(True)
        self._inc_commentary.setStyleSheet(f"color:{TEXT}; font-size:12px;")
        form_layout.addWidget(self._inc_commentary)

        self._inc_media = QCheckBox("Include media")
        self._inc_media.setChecked(True)
        self._inc_media.setStyleSheet(f"color:{TEXT}; font-size:12px;")
        form_layout.addWidget(self._inc_media)

        for lbl in form.findChildren(QLabel):
            lbl.setStyleSheet(_LABEL)

        layout.addWidget(form)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate LaTeX")
        self._gen_btn.setStyleSheet(_BTN.format(bg=ACCENT, fg="white"))
        self._gen_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self._gen_btn)

        self._compile_btn = QPushButton("Compile PDF")
        self._compile_btn.setEnabled(False)
        self._compile_btn.setStyleSheet(_BTN.format(bg=GREEN, fg=DARK))
        self._compile_btn.clicked.connect(self._on_compile)
        btn_row.addWidget(self._compile_btn)

        self._open_btn = QPushButton("Open in Finder")
        self._open_btn.setVisible(False)
        self._open_btn.setStyleSheet(_BTN.format(bg=OVERLAY1, fg=TEXT))
        self._open_btn.clicked.connect(self._on_open_finder)
        btn_row.addWidget(self._open_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_BTN.format(bg=OVERLAY1, fg=TEXT))
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{GREEN}; font-size:12px;")
        layout.addWidget(self._status)

        # ── Error log (shown only when compilation fails) ──────────────────
        self._error_log = QTextEdit()
        self._error_log.setReadOnly(True)
        self._error_log.setVisible(False)
        self._error_log.setMaximumHeight(120)
        self._error_log.setStyleSheet(
            f"QTextEdit {{ background:{SURFACE}; color:{RED}; border:1px solid {OVERLAY};"
            f" border-radius:6px; font-size:11px; font-family:monospace; }}"
        )
        layout.addWidget(self._error_log)

        # ── PDF viewer ────────────────────────────────────────────────────────
        self._pdf_view = QWebEngineView()
        self._pdf_view.setVisible(False)
        self._pdf_view.setMinimumHeight(300)
        self._pdf_view.setStyleSheet(f"background:{SURFACE}; border:1px solid {OVERLAY};")
        layout.addWidget(self._pdf_view)

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_generate(self):
        self._status.setStyleSheet(f"color:{GREEN}; font-size:12px;")
        self._status.setText("Generating LaTeX...")
        self._error_log.setVisible(False)
        self._gen_btn.setEnabled(False)
        try:
            tex_path = generate(
                book=self._book_combo.currentText(),
                chapter_start=self._ch_start.value(),
                chapter_end=self._ch_end.value(),
                edition=self._ed_combo.currentText(),
                include_commentary=self._inc_commentary.isChecked(),
                include_media=self._inc_media.isChecked(),
            )
            self._tex_path = tex_path
            self._compile_btn.setEnabled(True)
            self._status.setText(f"LaTeX generated: {os.path.basename(tex_path)}")
        except Exception as e:
            self._status.setStyleSheet(f"color:{RED}; font-size:12px;")
            self._status.setText(f"Error generating LaTeX: {e}")
        finally:
            self._gen_btn.setEnabled(True)

    def _on_compile(self):
        if not self._tex_path:
            return
        self._compile_btn.setEnabled(False)
        self._status.setStyleSheet(f"color:{GREEN}; font-size:12px;")
        self._status.setText("Compiling PDF...")
        self._error_log.setVisible(False)
        self._pdf_view.setVisible(False)
        self._pdf_worker = _PdfWorker(self._tex_path)
        self._pdf_worker.done.connect(self._on_pdf_done)
        self._pdf_worker.error.connect(self._on_pdf_error)
        self._pdf_worker.start()

    def _on_pdf_done(self, pdf_path: str):
        self._compile_btn.setEnabled(True)
        self._status.setStyleSheet(f"color:{GREEN}; font-size:12px;")
        self._status.setText(f"PDF ready: {os.path.basename(pdf_path)}")
        self._open_btn.setVisible(True)
        self._pdf_view.setVisible(True)
        url = QUrl.fromLocalFile(os.path.abspath(pdf_path))
        self._pdf_view.setUrl(url)

    def _on_pdf_error(self, msg: str):
        self._compile_btn.setEnabled(True)
        self._status.setStyleSheet(f"color:{RED}; font-size:12px;")
        self._status.setText("Compilation failed — see error log below.")
        self._error_log.setPlainText(msg)
        self._error_log.setVisible(True)

    def _on_open_finder(self):
        pdf_path = os.path.join(OUTPUT_DIR, "export.pdf")
        if os.path.exists(pdf_path):
            subprocess.run(["open", "-R", pdf_path])
