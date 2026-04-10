from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QMenu, QToolTip, QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QEvent, QPointF, QRect
from PyQt6.QtGui import QCursor, QAction, QTextDocument, QTextCursor, QPainter, QColor

from backend.db_api import HIGHLIGHT_COLORS
from ui.themes import DIM, TEXT, ACCENT

BADGE_STYLE = (
    "background: {color}; color: white; border-radius: 8px; "
    "padding: 1px 6px; font-size: 10px; font-weight: bold;"
)

_MENU_STYLE = """
    QMenu { background:#1e1e2e; color:#cdd6f4; border:1px solid #45475a; }
    QMenu::item { padding:5px 20px; }
    QMenu::item:selected { background:#313244; }
    QMenu::separator { height:1px; background:#45475a; margin:4px 0; }
"""

# Punctuation to strip from the edges of a detected word
_STRIP_CHARS = ".,;:!?\"'\u2019\u2018\u201c\u201d\u2014\u2013()-[]"


def _he(text: str) -> str:
    """Minimal HTML escape for verse text (does NOT escape quotes)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_dark(hex_color: str) -> bool:
    """Return True if the hex color is dark enough to need white text."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 128


def _make_word_hl_html(plain_text: str, word_highlights: list[dict]) -> str:
    """
    Build an HTML fragment with colored <span> tags for each word highlight.

    *word_highlights* is a list of {start_char, end_char, color} dicts
    sorted (or unsorted — we sort internally) by start_char.
    Returns plain text (HTML-escaped) when there are no highlights.
    """
    if not word_highlights:
        return _he(plain_text)

    spans = sorted(word_highlights, key=lambda h: h["start_char"])
    n = len(plain_text)
    parts: list[str] = []
    pos = 0

    for hl in spans:
        s = max(pos, hl["start_char"])
        e = min(n, hl["end_char"])
        if e <= s:
            continue
        if s > pos:
            parts.append(_he(plain_text[pos:s]))
        color = hl["color"]
        fg = "#1e1e2e" if not _is_dark(color) else "#ffffff"
        parts.append(
            f'<span style="background:{color};color:{fg};border-radius:2px;">'
            f'{_he(plain_text[s:e])}</span>'
        )
        pos = e

    if pos < n:
        parts.append(_he(plain_text[pos:]))

    return "".join(parts)


_BAR_W = 3     # width of each bar in pixels
_BAR_GAP = 3   # gap between bars and between gutter edge and first bar
_BAR_RADIUS = 2

# Colours cycling per distinct range (dark-theme friendly)
BAR_COLORS = [
    "#89b4fa",  # blue
    "#a6e3a1",  # green
    "#fab387",  # peach
    "#cba6f7",  # mauve
    "#f38ba8",  # red
    "#89dceb",  # sky
    "#f9e2af",  # yellow
]


class _RangeGutter(QWidget):
    """
    Narrow column drawn to the left of each verse showing coloured vertical
    bars for every cross-link range that covers that verse.

    *bars*   — list of {color, slot, position}
               position: "top" | "middle" | "bottom"
    *slots*  — total number of slots used in this chapter (sets fixed width)
    """

    def __init__(self, bars: list[dict], slots: int, parent=None):
        super().__init__(parent)
        w = slots * (_BAR_W + _BAR_GAP) + _BAR_GAP if slots > 0 else 0
        self.setFixedWidth(w)
        self._bars = bars

    def paintEvent(self, event):
        if not self._bars:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        h = self.height()

        for bar in self._bars:
            x = _BAR_GAP + bar["slot"] * (_BAR_W + _BAR_GAP)
            pos = bar["position"]
            color = QColor(bar["color"])
            painter.setBrush(color)

            if pos == "top":
                # Rounded cap at top, extends to bottom edge (connects downward)
                mid = h // 3
                painter.drawRoundedRect(x, mid, _BAR_W, _BAR_RADIUS * 4,
                                        _BAR_RADIUS, _BAR_RADIUS)  # cap
                painter.drawRect(x, mid + _BAR_RADIUS * 2, _BAR_W, h - mid - _BAR_RADIUS * 2)
            elif pos == "bottom":
                # Extends from top edge, rounded cap at bottom
                mid = h - h // 3
                painter.drawRect(x, 0, _BAR_W, mid - _BAR_RADIUS * 2)
                painter.drawRoundedRect(x, mid - _BAR_RADIUS * 2, _BAR_W, _BAR_RADIUS * 4,
                                        _BAR_RADIUS, _BAR_RADIUS)  # cap
            else:  # "middle" — full height, connects both ways
                painter.drawRect(x, 0, _BAR_W, h)

        painter.end()


class _BadgeLabel(QLabel):
    """Clickable badge that shows a lazy-fetched preview tooltip on hover."""

    clicked = pyqtSignal(str)   # badge_type: "commentary" | "crosslinks" | "media"

    def __init__(self, badge_type: str, label: str, color: str,
                 book: str, chapter: int, verse: int, parent=None):
        super().__init__(label, parent)
        self._badge_type = badge_type
        self._book = book
        self._chapter = chapter
        self._verse = verse
        self._preview: str | None = None
        self.setStyleSheet(BADGE_STYLE.format(color=color))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._badge_type)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if self._preview is None:
            self._preview = self._fetch_preview()
        if self._preview:
            QToolTip.showText(QCursor.pos(), self._preview, self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def _fetch_preview(self) -> str:
        from backend.db_api import get_commentary, get_crosslinks, get_media
        try:
            if self._badge_type == "commentary":
                notes = get_commentary(self._book, self._chapter, self._verse)
                if not notes:
                    return ""
                lines = []
                for n in notes[:3]:
                    snippet = n["body"][:120].replace("\n", " ")
                    if len(n["body"]) > 120:
                        snippet += "…"
                    lines.append(snippet)
                return "\n\n".join(lines)

            elif self._badge_type == "crosslinks":
                links = get_crosslinks(self._book, self._chapter, self._verse)
                parts = []
                for lk in links["outbound"][:5]:
                    ve = lk.get("target_verse_end")
                    ref = f"{lk['target_book']} {lk['target_chapter']}:{lk['target_verse']}"
                    if ve and ve > lk["target_verse"]:
                        ref += f"–{ve}"
                    if lk.get("note"):
                        ref += f"  — {lk['note']}"
                    parts.append(f"→ {ref}")
                for lk in links["inbound"][:3]:
                    ref = f"{lk['source_book']} {lk['source_chapter']}:{lk['source_verse']}"
                    parts.append(f"← {ref}")
                return "\n".join(parts)

            elif self._badge_type == "media":
                items = get_media(self._book, self._chapter, self._verse)
                parts = []
                for m in items[:4]:
                    if m.get("og_title"):
                        parts.append(m["og_title"])
                    elif m.get("caption"):
                        parts.append(m["caption"])
                    elif m.get("filename"):
                        parts.append(m["filename"])
                    else:
                        parts.append("(media attachment)")
                return "\n".join(parts)
        except Exception:
            pass
        return ""


class VerseWidget(QFrame):
    clicked = pyqtSignal(int)                        # verse number
    lookup_word = pyqtSignal(str)                    # word to look up in dictionary
    word_hl_requested = pyqtSignal(int, int, int, str)   # verse, start, end, color
    word_hl_remove_requested = pyqtSignal(int)           # word_highlight id
    badge_clicked = pyqtSignal(int, str)                 # verse, badge_type

    def __init__(self, book: str, chapter: int, verse: int, text: str, badges: dict,
                 word_highlights: list[dict] | None = None,
                 range_bars: list[dict] | None = None,
                 gutter_slots: int = 0,
                 parent=None):
        super().__init__(parent)
        self._book = book
        self._chapter = chapter
        self._verse = verse
        self._plain_text = text           # always the raw verse text
        self._selected = False
        self._word_highlights: list[dict] = list(word_highlights or [])

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("VerseWidget { background: transparent; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # Range gutter (zero width when no ranges in chapter)
        gutter = _RangeGutter(range_bars or [], gutter_slots)
        layout.addWidget(gutter)

        self._num = QLabel(str(verse))
        self._num.setFixedWidth(28)
        self._num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self._num.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._num.setStyleSheet(
            f"color: {DIM}; font-size: 12px; font-weight: bold; padding-top: 2px;"
        )
        layout.addWidget(self._num)

        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._text_label.setStyleSheet(f"color: {TEXT}; font-size: 14px; line-height: 1.5;")
        self._text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._text_label.setTextFormat(Qt.TextFormat.RichText)
        self._text_label.installEventFilter(self)
        self._rebuild_display()
        layout.addWidget(self._text_label)

        badge_col = QFrame()
        badge_col.setFixedWidth(60)
        bcol_layout = QHBoxLayout(badge_col)
        bcol_layout.setContentsMargins(0, 0, 0, 0)
        bcol_layout.setSpacing(3)
        bcol_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        if badges.get("commentary"):
            b = _BadgeLabel("commentary", f"\u270f {badges['commentary']}",
                            ACCENT, book, chapter, verse)
            b.clicked.connect(lambda t, v=verse: self.badge_clicked.emit(v, t))
            bcol_layout.addWidget(b)
        if badges.get("crosslinks"):
            b = _BadgeLabel("crosslinks", f"\u2194 {badges['crosslinks']}",
                            "#a6e3a1", book, chapter, verse)
            b.clicked.connect(lambda t, v=verse: self.badge_clicked.emit(v, t))
            bcol_layout.addWidget(b)
        if badges.get("media"):
            b = _BadgeLabel("media", f"\U0001f5bc {badges['media']}",
                            "#f38ba8", book, chapter, verse)
            b.clicked.connect(lambda t, v=verse: self.badge_clicked.emit(v, t))
            bcol_layout.addWidget(b)

        layout.addWidget(badge_col)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_word_highlights(self, word_highlights: list[dict]) -> None:
        """Replace all word highlights and redraw."""
        self._word_highlights = list(word_highlights)
        self._rebuild_display()

    def update_text(self, text: str):
        self._plain_text = text
        self._rebuild_display()

    def set_selected(self, selected: bool):
        """Track selection state (no visual indicator)."""
        self._selected = selected

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _rebuild_display(self) -> None:
        """Regenerate rich text HTML from plain text + word highlights."""
        html = _make_word_hl_html(self._plain_text, self._word_highlights)
        self._text_label.setText(html)

    # ── Word detection ────────────────────────────────────────────────────────

    def _char_pos_at_label_pos(self, label_pos: QPointF) -> int:
        """Return character index in _plain_text nearest to label_pos, or -1."""
        doc = QTextDocument()
        doc.setDefaultFont(self._text_label.font())
        doc.setPlainText(self._plain_text)
        doc.setTextWidth(self._text_label.width())
        return doc.documentLayout().hitTest(label_pos, Qt.HitTestAccuracy.FuzzyHit)

    def _word_at_char_pos(self, char_pos: int) -> str:
        """Return the word in _plain_text at char_pos."""
        if char_pos < 0:
            return ""
        doc = QTextDocument()
        doc.setDefaultFont(self._text_label.font())
        doc.setPlainText(self._plain_text)
        cursor = QTextCursor(doc)
        cursor.setPosition(char_pos)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor.selectedText().strip(_STRIP_CHARS)

    def _highlight_at_char_pos(self, char_pos: int) -> dict | None:
        """Return the word_highlight dict that contains char_pos, or None."""
        for hl in self._word_highlights:
            if hl["start_char"] <= char_pos < hl["end_char"]:
                return hl
        return None

    def _selection_char_range(self) -> tuple[int, int] | None:
        """
        Return (start, end) character offsets in _plain_text for the current
        text-label selection, or None if nothing is selected.
        """
        sel = self._text_label.selectedText()
        if not sel:
            return None
        idx = self._plain_text.find(sel)
        if idx < 0:
            return None
        return idx, idx + len(sel)

    # ── Events ────────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Intercept right-clicks on the text label."""
        if obj is self._text_label and event.type() == QEvent.Type.ContextMenu:
            char_pos = self._char_pos_at_label_pos(QPointF(event.pos()))
            word = self._word_at_char_pos(char_pos)
            existing_hl = self._highlight_at_char_pos(char_pos)
            sel_range = self._selection_char_range()
            self._show_context_menu(event.globalPos(), word, existing_hl, sel_range)
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._verse)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Right-click on the frame outside the text label."""
        self._show_context_menu(event.globalPos(), "", None, None)

    def _show_context_menu(
        self,
        global_pos,
        word_under_cursor: str = "",
        existing_hl: dict | None = None,
        sel_range: tuple[int, int] | None = None,
    ):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)

        # ── Dictionary lookup ─────────────────────────────────────────────────
        word = word_under_cursor
        if not word:
            sel = self._text_label.selectedText().strip()
            if sel:
                word = sel.split()[0].strip(_STRIP_CHARS)
        if word:
            dict_action = QAction(
                f'Look up \u201c{word}\u201d in Webster\u2019s', self
            )
            dict_action.triggered.connect(
                lambda checked=False, w=word: self.lookup_word.emit(w)
            )
            menu.addAction(dict_action)
            menu.addSeparator()

        # ── Highlight selected text ───────────────────────────────────────────
        if sel_range:
            hl_sel_menu = menu.addMenu("Highlight selection")
            hl_sel_menu.setStyleSheet(_MENU_STYLE)
            for name, hex_color in HIGHLIGHT_COLORS.items():
                act = QAction(f"  {name}", self)
                act.setData(("word_add", sel_range[0], sel_range[1], hex_color))
                hl_sel_menu.addAction(act)

        # ── Remove word highlight under cursor ────────────────────────────────
        if existing_hl:
            rm_act = QAction("Remove highlight", self)
            rm_act.setData(("word_remove", existing_hl["id"]))
            menu.addAction(rm_act)

        chosen = menu.exec(global_pos)
        if not chosen or not chosen.data():
            return

        data = chosen.data()
        if data[0] == "word_add":
            _, s, e, color = data
            self.word_hl_requested.emit(self._verse, s, e, color)
        elif data[0] == "word_remove":
            _, hl_id = data
            self.word_hl_remove_requested.emit(hl_id)
