"""Webster's Dictionary lookup dialog (1828 / 1844 / 1913 — local db/dict.db)."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTextBrowser, QLabel, QSizePolicy,
    QComboBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QKeySequence, QShortcut

from ui.themes import DARK, SURFACE, ELEVATED, OVERLAY, OVERLAY1, SUBTEXT, TEXT, ACCENT, RED


_BTN = "QPushButton {{ background:{bg}; color:{fg}; border:none; border-radius:4px; padding:5px 14px; font-size:12px; }}"

_SOURCES = [
    ("1828 (American Dictionary)", "1828"),
    ("1844 (American Dictionary)", "1844"),
    ("1913 (Revised Unabridged)", "1913"),
]


class DictionaryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Webster's Dictionary")
        self.setMinimumSize(QSize(580, 500))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setStyleSheet(f"QDialog {{ background:{DARK}; color:{TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # ── Search bar ────────────────────────────────────────────────────────
        search_row = QHBoxLayout()

        self._input = QLineEdit()
        self._input.setPlaceholderText("Enter a word…")
        self._input.setStyleSheet(
            f"QLineEdit {{ background:{ELEVATED}; color:{TEXT}; border:1px solid {OVERLAY1};"
            f" border-radius:4px; padding:5px 8px; font-size:13px; }}"
        )
        self._input.returnPressed.connect(self._on_lookup)
        search_row.addWidget(self._input)

        self._source_box = QComboBox()
        self._source_box.setStyleSheet(
            f"QComboBox {{ background:{ELEVATED}; color:{TEXT}; border:1px solid {OVERLAY1};"
            f" border-radius:4px; padding:4px 8px; font-size:12px; min-width:180px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
            f"QComboBox QAbstractItemView {{ background:{ELEVATED}; color:{TEXT};"
            f" selection-background-color:{ACCENT}; }}"
        )
        for label, _ in _SOURCES:
            self._source_box.addItem(label)
        self._source_box.currentIndexChanged.connect(self._on_source_changed)
        search_row.addWidget(self._source_box)

        self._lookup_btn = QPushButton("Look up")
        self._lookup_btn.setStyleSheet(_BTN.format(bg=ACCENT, fg="white"))
        self._lookup_btn.clicked.connect(self._on_lookup)
        search_row.addWidget(self._lookup_btn)

        layout.addLayout(search_row)

        # ── Status label ──────────────────────────────────────────────────────
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{SUBTEXT}; font-size:11px;")
        self._status.setVisible(False)
        layout.addWidget(self._status)

        # ── Definition display ────────────────────────────────────────────────
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            f"QTextBrowser {{ background:{SURFACE}; color:{TEXT};"
            f" border:1px solid {OVERLAY}; border-radius:6px;"
            f" padding:8px; font-size:13px; }}"
        )
        self._browser.document().setDefaultStyleSheet(
            f"body {{ color:{TEXT}; background:{SURFACE};"
            f" font-family: Georgia, serif; line-height: 1.6; }}"
            f"b {{ color:{TEXT}; }} i {{ color:{SUBTEXT}; }}"
            f"a {{ color:{ACCENT}; }}"
            f"ol, ul {{ margin-left: 16px; }} li {{ margin-bottom: 4px; }}"
            f"hr {{ border:none; border-top:1px solid {OVERLAY1}; margin:8px 0; }}"
            f".term {{ color:{ACCENT}; font-weight:bold; }}"
        )
        layout.addWidget(self._browser, 1)

        # ── Close button ──────────────────────────────────────────────────────
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_BTN.format(bg=OVERLAY1, fg=TEXT))
        close_btn.clicked.connect(self.hide)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        QShortcut(QKeySequence("Escape"), self).activated.connect(self.hide)

    # ── Public API ────────────────────────────────────────────────────────────

    def lookup(self, word: str):
        """Pre-populate the search field and trigger a lookup."""
        first_word = word.strip().split()[0] if word.strip() else ""
        if not first_word:
            return
        self._input.setText(first_word)
        self.show()
        self.raise_()
        self._on_lookup()

    # ── Private ───────────────────────────────────────────────────────────────

    def _current_source(self) -> str:
        idx = self._source_box.currentIndex()
        return _SOURCES[idx][1] if 0 <= idx < len(_SOURCES) else "1828"

    def _on_source_changed(self) -> None:
        """Re-run lookup when the user switches dictionary edition."""
        if self._input.text().strip():
            self._on_lookup()

    def _on_lookup(self):
        word = self._input.text().strip()
        if not word:
            return

        from backend.services.dictionary_fetcher import lookup
        result = lookup(word, source=self._current_source())

        if result:
            self._show_html(result["word"], result["html"], result.get("source", ""))
        else:
            source_label = _SOURCES[self._source_box.currentIndex()][0]
            self._browser.setHtml(
                f"<html><body style='color:{RED}; font-family:sans-serif; font-size:13px;"
                f" padding:8px;'>"
                f"No entry found for \"{word}\" in {source_label}."
                f"</body></html>"
            )
            self.setWindowTitle("Webster's Dictionary")
            self._status.setVisible(False)

    def _show_html(self, word: str, html: str, source: str):
        year = source if source else "Webster's"
        self.setWindowTitle(f"Webster's {year} — {word.capitalize()}")
        self._browser.setHtml(html)
        self._status.setVisible(False)
