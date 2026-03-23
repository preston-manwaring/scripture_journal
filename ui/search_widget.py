"""
Search dialog (Cmd+F).

Two modes
─────────
Standard  — SQLite LIKE search across verse text, commentary notes, and
             media metadata for the active edition.  Results are colour-
             coded by source (verse / note / media).
AI Search — Streams a response from claude-opus-4-6 (adaptive thinking),
             parses out Book of Mormon verse citations, looks them up in
             the DB, and shows clickable results below the narrative.

API key is read from the ANTHROPIC_API_KEY environment variable.
If it is absent the user is prompted to enter it once; the value is
stored in the preferences table for the session.
"""
from __future__ import annotations
import os
import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QTextEdit, QScrollArea, QFrame, QSizePolicy,
    QInputDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QFont

from backend.db_api import search_all, get_verse_text, get_pref, set_pref, BOOK_ORDER
from ui.themes import DARK as _DARK, SURFACE as _SURFACE, ELEVATED as _ELEVATED
from ui.themes import OVERLAY as _OVERLAY, OVERLAY1 as _OVERLAY1
from ui.themes import TEXT as _TEXT, SUBTEXT as _MUTED, ACCENT as _ACCENT

# ── regex for BoM citations ────────────────────────────────────────────────────
_BOOKS_RE = (
    r"(?:1\s+Nephi|2\s+Nephi|Jacob|Enos|Jarom|Omni|Words\s+of\s+Mormon"
    r"|Mosiah|Alma|Helaman|3\s+Nephi|4\s+Nephi|Mormon|Ether|Moroni)"
)
_CITE_RE = re.compile(
    rf"({_BOOKS_RE})\s+(\d+):(\d+(?:[-–]\d+)?)",
    re.IGNORECASE,
)

_BOOK_CANON = {b.lower().replace(" ", ""): b for b in BOOK_ORDER}
_BOOK_CANON.update({b.lower(): b for b in BOOK_ORDER})


def _normalise_book(raw: str) -> str | None:
    """Turn a regex-matched book string into the canonical name or None."""
    key = re.sub(r"\s+", "", raw.strip().lower())
    if key in _BOOK_CANON:
        return _BOOK_CANON[key]
    # fallback: try space-normalised
    key2 = raw.strip().lower()
    return _BOOK_CANON.get(key2)


# ── Workers ───────────────────────────────────────────────────────────────────

def _build_personal_context(question: str, edition: str) -> str:
    """
    Run a keyword search over the user's notes and media for the question text,
    and return a formatted context block (empty string if nothing found).
    """
    try:
        rows = search_all(question, edition, limit_each=20)
    except ValueError:
        return ""

    notes = [r for r in rows if r["source"] == "note"]
    media = [r for r in rows if r["source"] == "media"]
    if not notes and not media:
        return ""

    parts = ["The user has the following personal study notes and media in their journal that may be relevant:\n"]
    if notes:
        parts.append("PERSONAL NOTES:")
        for r in notes:
            ref = f"{r['book']} {r['chapter']}:{r['verse']}"
            parts.append(f"  {ref} — {r['snippet'][:300]}")
    if media:
        parts.append("MEDIA ATTACHMENTS:")
        for r in media:
            ref = f"{r['book']} {r['chapter']}:{r['verse']}"
            label = r.get("label", "")
            snippet = r.get("snippet", "")
            entry = f"  {ref}"
            if label:
                entry += f" [{label}]"
            if snippet:
                entry += f" — {snippet[:200]}"
            parts.append(entry)

    return "\n".join(parts)


class _ClaudeWorker(QThread):
    """Stream a Claude response and emit text chunks + parsed citations."""
    chunk = pyqtSignal(str)          # incremental response text
    citation_found = pyqtSignal(str, int, int)   # book, chapter, verse
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, question: str, edition: str, api_key: str, personal_context: str = ""):
        super().__init__()
        self._question = question
        self._edition  = edition
        self._api_key  = api_key
        self._personal_context = personal_context

    def run(self):
        try:
            import anthropic
        except ImportError:
            self.error.emit("anthropic package not installed — run: pip install anthropic")
            return

        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            system = (
                "You are a knowledgeable Book of Mormon scholar helping a user study the scriptures. "
                "When the user asks a question, suggest the most relevant verses "
                "from the Book of Mormon that address the topic. "
                "Always cite verses in the format 'Book Chapter:Verse' "
                "(e.g., '1 Nephi 3:7', 'Mosiah 3:19', 'Moroni 10:4-5'). "
                "Explain briefly why each verse is relevant. "
                "Include 3–8 specific verse references in your response. "
                "If personal study notes or media attachments are provided, "
                "reference them naturally where relevant to connect the scriptures "
                "to the user's own study and insights."
            )

            user_content = self._question
            if self._personal_context:
                user_content = f"{self._personal_context}\n\nQUESTION:\n{self._question}"

            full_text = ""
            cited: set[tuple] = set()

            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=2048,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{"role": "user", "content": user_content}],
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            self.chunk.emit(delta.text)
                            full_text += delta.text
                            # Parse and emit any new citations as they appear
                            for m in _CITE_RE.finditer(full_text):
                                book = _normalise_book(m.group(1))
                                if not book:
                                    continue
                                chapter = int(m.group(2))
                                verse_str = m.group(3)
                                # Handle ranges like 10-5 → just use first verse
                                verse = int(re.split(r"[-–]", verse_str)[0])
                                key = (book, chapter, verse)
                                if key not in cited:
                                    cited.add(key)
                                    self.citation_found.emit(book, chapter, verse)

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# source → (badge label, badge colour)
_SOURCE_BADGE = {
    "verse": ("Verse", "#7c83e0"),
    "note":  ("Note",  "#a6e3a1"),
    "media": ("Media", "#f38ba8"),
}


# ── Result row widget ─────────────────────────────────────────────────────────

class _VerseResultRow(QFrame):
    navigate = pyqtSignal(str, int, int)   # book, chapter, verse

    def __init__(self, book: str, chapter: int, verse: int, snippet: str,
                 source: str = "verse", label: str = "", parent=None):
        super().__init__(parent)
        self._book, self._chapter, self._verse = book, chapter, verse
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { background: #252536; border-radius: 6px; "
            "border: 1px solid #313244; } "
            "QFrame:hover { border-color: #7c83e0; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(3)

        # Header: reference + source badge (+ optional media label)
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        ref = QLabel(f"<b>{book} {chapter}:{verse}</b>")
        ref.setStyleSheet(f"color: {_ACCENT}; font-size: 12px; background: transparent;")
        header_row.addWidget(ref)

        badge_text, badge_color = _SOURCE_BADGE.get(source, ("", _OVERLAY))
        if badge_text:
            badge = QLabel(badge_text)
            badge.setStyleSheet(
                f"background: {badge_color}; color: #1e1e2e; border-radius: 6px; "
                f"padding: 0px 6px; font-size: 10px; font-weight: bold;"
            )
            header_row.addWidget(badge)

        if label:
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px; background: transparent;")
            lbl.setMaximumWidth(200)
            header_row.addWidget(lbl)

        header_row.addStretch()
        lay.addLayout(header_row)

        body_text = snippet[:160] + ("…" if len(snippet) > 160 else "")
        body = QLabel(body_text)
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {_TEXT}; font-size: 12px; background: transparent;")
        lay.addWidget(body)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.navigate.emit(self._book, self._chapter, self._verse)
        super().mousePressEvent(event)


# ── Standard search tab ───────────────────────────────────────────────────────

class _StandardTab(QWidget):
    navigate_to = pyqtSignal(str, int, int)

    def __init__(self, edition_getter, parent=None):
        super().__init__(parent)
        self._get_edition = edition_getter
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._run_search)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Search verse text…")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {_SURFACE}; color: {_TEXT}; "
            f"border: 1px solid {_OVERLAY}; border-radius: 4px; "
            f"padding: 5px 8px; font-size: 13px; }}"
        )
        self._input.textChanged.connect(self._timer.start)
        row.addWidget(self._input)

        clear_btn = QPushButton("✕")
        clear_btn.setFixedWidth(28)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {_OVERLAY}; color: {_MUTED}; "
            f"border: none; border-radius: 4px; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; }}"
        )
        clear_btn.clicked.connect(self._input.clear)
        row.addWidget(clear_btn)
        lay.addLayout(row)

        self._count = QLabel("")
        self._count.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        lay.addWidget(self._count)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_DARK}; border: none; }}"
            f"QScrollBar:vertical {{ background: {_SURFACE}; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {_OVERLAY}; border-radius: 3px; }}"
        )
        self._results_container = QWidget()
        self._results_container.setStyleSheet(f"background: {_DARK};")
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(4)
        self._results_layout.addStretch()
        scroll.setWidget(self._results_container)
        lay.addWidget(scroll)

    def focus_input(self):
        self._input.setFocus()
        self._input.selectAll()

    def _run_search(self):
        query = self._input.text().strip()
        self._clear_results()
        if len(query) < 2:
            self._count.setText("")
            return
        edition = self._get_edition()
        try:
            rows = search_all(query, edition, limit_each=50)
        except ValueError as exc:
            self._count.setText(str(exc))
            return
        n = len(rows)
        # Count by source for the summary label
        src_counts: dict[str, int] = {}
        for r in rows:
            src_counts[r["source"]] = src_counts.get(r["source"], 0) + 1
        parts = []
        for src in ("verse", "note", "media"):
            if src_counts.get(src):
                parts.append(f"{src_counts[src]} {src}{'s' if src_counts[src]!=1 else ''}")
        self._count.setText(f"{n} result{'s' if n!=1 else ''}" + (f" ({', '.join(parts)})" if parts else ""))
        for r in rows:
            w = _VerseResultRow(
                r["book"], r["chapter"], r["verse"],
                r["snippet"], source=r["source"], label=r.get("label", ""),
            )
            w.navigate.connect(self.navigate_to)
            self._results_layout.insertWidget(self._results_layout.count() - 1, w)

    def _clear_results(self):
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


# ── AI search tab ─────────────────────────────────────────────────────────────

class _AITab(QWidget):
    navigate_to = pyqtSignal(str, int, int)

    def __init__(self, edition_getter, parent=None):
        super().__init__(parent)
        self._get_edition = edition_getter
        self._worker: _ClaudeWorker | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # Question input
        self._input = QTextEdit()
        self._input.setPlaceholderText(
            "Ask a question about the Book of Mormon...\n"
            "e.g. \"What verses talk about faith and prayer?\""
        )
        self._input.setFixedHeight(90)
        self._input.setStyleSheet(
            f"QTextEdit {{ background: {_SURFACE}; color: {_TEXT}; "
            f"border: 1px solid {_OVERLAY}; border-radius: 4px; "
            f"padding: 6px; font-size: 13px; }}"
        )
        lay.addWidget(self._input)

        btn_row = QHBoxLayout()
        self._ask_btn = QPushButton("Ask Claude")
        self._ask_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT}; color: white; "
            f"border: none; border-radius: 4px; padding: 5px 16px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #6b72d0; }}"
            f"QPushButton:disabled {{ background: {_OVERLAY}; color: {_MUTED}; }}"
        )
        self._ask_btn.clicked.connect(self._ask)
        btn_row.addWidget(self._ask_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setVisible(False)
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: {_OVERLAY}; color: {_MUTED}; "
            f"border: none; border-radius: 4px; padding: 5px 12px; font-size: 13px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; }}"
        )
        self._stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        lay.addWidget(self._status)

        # Scrollable area for response + verse cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_DARK}; border: none; }}"
            f"QScrollBar:vertical {{ background: {_SURFACE}; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {_OVERLAY}; border-radius: 3px; }}"
        )
        self._response_container = QWidget()
        self._response_container.setStyleSheet(f"background: {_DARK};")
        self._response_layout = QVBoxLayout(self._response_container)
        self._response_layout.setContentsMargins(0, 0, 0, 0)
        self._response_layout.setSpacing(6)

        # Narrative text label (streaming)
        self._narrative = QLabel("")
        self._narrative.setWordWrap(True)
        self._narrative.setTextFormat(Qt.TextFormat.PlainText)
        self._narrative.setStyleSheet(
            f"color: {_TEXT}; font-size: 13px; background: {_DARK}; "
            f"padding: 4px 0;"
        )
        self._narrative.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._narrative.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._response_layout.addWidget(self._narrative)

        # Verse cards inserted below narrative
        self._cards_container = QWidget()
        self._cards_container.setStyleSheet(f"background: {_DARK};")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(4)
        self._response_layout.addWidget(self._cards_container)
        self._response_layout.addStretch()

        scroll.setWidget(self._response_container)
        lay.addWidget(scroll)

        self._text_buffer = ""
        self._seen_citations: set[tuple] = set()

    def focus_input(self):
        self._input.setFocus()

    def _get_api_key(self) -> str | None:
        key = os.environ.get("ANTHROPIC_API_KEY") or get_pref("anthropic_api_key")
        if key:
            return key
        key, ok = QInputDialog.getText(
            self,
            "Anthropic API Key",
            "Enter your Anthropic API key (stored in preferences):",
        )
        if ok and key.strip():
            set_pref("anthropic_api_key", key.strip())
            return key.strip()
        return None

    def _ask(self):
        question = self._input.toPlainText().strip()
        if not question:
            return
        api_key = self._get_api_key()
        if not api_key:
            return

        # Reset UI
        self._narrative.setText("")
        self._text_buffer = ""
        self._seen_citations = set()
        self._clear_cards()
        self._ask_btn.setEnabled(False)
        self._stop_btn.setVisible(True)

        edition = self._get_edition()
        self._status.setText("Searching your notes…")
        personal_context = _build_personal_context(question, edition)
        if personal_context:
            note_count = personal_context.count("\n  ")
            self._status.setText(f"Found {note_count} relevant note(s) — asking Claude…")
        else:
            self._status.setText("Thinking…")

        self._worker = _ClaudeWorker(question, edition, api_key, personal_context)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.citation_found.connect(self._on_citation)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        self._on_done()

    def _on_chunk(self, text: str):
        self._text_buffer += text
        self._narrative.setText(self._text_buffer)

    def _on_citation(self, book: str, chapter: int, verse: int):
        key = (book, chapter, verse)
        if key in self._seen_citations:
            return
        self._seen_citations.add(key)

        edition = self._get_edition()
        text = get_verse_text(book, chapter, verse, edition)
        if text is None:
            # Try fallback editions
            for ed in ("2013", "1981", "1830"):
                text = get_verse_text(book, chapter, verse, ed)
                if text:
                    break
        if text is None:
            text = "(verse not found in database)"

        card = _VerseResultRow(book, chapter, verse, text)
        card.navigate.connect(self.navigate_to)
        self._cards_layout.addWidget(card)

    def _on_done(self):
        n = len(self._seen_citations)
        ctx = f" · journal context included" if (self._worker and self._worker._personal_context) else ""
        self._status.setText(f"{n} verse{'s' if n != 1 else ''} suggested{ctx}")
        self._ask_btn.setEnabled(True)
        self._stop_btn.setVisible(False)

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")
        self._narrative.setText(f"Could not connect to Claude:\n{msg}")
        self._ask_btn.setEnabled(True)
        self._stop_btn.setVisible(False)

    def _clear_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


# ── Top-level dialog ──────────────────────────────────────────────────────────

class SearchDialog(QDialog):
    navigate_to = pyqtSignal(str, int, int)

    def __init__(self, edition_getter, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Search")
        self.setMinimumSize(520, 560)
        self.setStyleSheet(
            f"QDialog {{ background: {_DARK}; }}"
            f"QTabWidget::pane {{ background: {_DARK}; border: none; border-top: 1px solid {_OVERLAY}; }}"
            f"QTabBar::tab {{ background: {_SURFACE}; color: {_MUTED}; padding: 6px 18px; "
            f"border: none; font-size: 12px; }}"
            f"QTabBar::tab:selected {{ background: {_DARK}; color: {_TEXT}; border-top: 2px solid {_ACCENT}; }}"
            f"QTabBar::tab:hover {{ background: #252536; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        self._standard = _StandardTab(edition_getter)
        self._standard.navigate_to.connect(self.navigate_to)
        tabs.addTab(self._standard, "Standard")

        self._ai = _AITab(edition_getter)
        self._ai.navigate_to.connect(self.navigate_to)
        tabs.addTab(self._ai, "AI Search")

        lay.addWidget(tabs)

        self._tabs = tabs

        # Esc hides, doesn't close
        QShortcut(QKeySequence("Escape"), self).activated.connect(self.hide)

    def show_standard(self):
        self._tabs.setCurrentIndex(0)
        self.show()
        self.raise_()
        self._standard.focus_input()

    def show_ai(self):
        self._tabs.setCurrentIndex(1)
        self.show()
        self.raise_()
        self._ai.focus_input()

    def closeEvent(self, event):
        """Override close to hide instead of destroy so state is preserved."""
        event.ignore()
        self.hide()
