from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QComboBox, QPushButton, QFrame, QSizePolicy, QLineEdit,
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer

from backend.db_api import (
    EDITIONS, get_chapter_verses, get_verse_badge_counts, get_diff,
    get_chapter_word_highlights, add_word_highlight, remove_word_highlight,
    get_pref, set_pref, search_all,
)
from ui.verse_widget import VerseWidget
from ui.themes import DARK, SURFACE, ELEVATED, OVERLAY, OVERLAY1, SUBTEXT, TEXT, ACCENT, RED, GREEN


class DiffOverlay(QWidget):
    """Inline diff view replacing the verse text area."""

    def __init__(self, diff: dict, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        for label, color in [
            (f"  {diff['edition_a']}  ", RED),
            (f"  {diff['edition_b']}  ", GREEN),
            ("  unchanged  ", OVERLAY1),
        ]:
            l = QLabel(label)
            l.setStyleSheet(
                f"background:{color}; color: white; border-radius:4px;"
                f" font-size:11px; padding:2px 4px;"
            )
            header.addWidget(l)
        header.addStretch()
        layout.addLayout(header)

        html_parts = []
        for tok in diff["diff_tokens"]:
            t = tok["token"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if tok["status"] == "removed":
                html_parts.append(
                    f'<span style="background:{RED};color:{DARK};border-radius:2px;">{t}</span>'
                )
            elif tok["status"] == "added":
                html_parts.append(
                    f'<span style="background:{GREEN};color:{DARK};border-radius:2px;">{t}</span>'
                )
            else:
                html_parts.append(f'<span style="color:{TEXT};">{t}</span>')

        diff_label = QLabel("".join(html_parts))
        diff_label.setWordWrap(True)
        diff_label.setTextFormat(Qt.TextFormat.RichText)
        diff_label.setStyleSheet("font-size:13px; line-height:1.6;")
        layout.addWidget(diff_label)

        self.setStyleSheet(f"DiffOverlay {{ background: {ELEVATED}; border-radius: 6px; }}")


class ReadingPane(QWidget):
    verse_activated = pyqtSignal(str, int, int)   # book, chapter, verse
    chapter_loaded = pyqtSignal(str, int)          # book, chapter
    lookup_word = pyqtSignal(str)                  # forwarded from VerseWidget
    navigate_requested = pyqtSignal(str, int, int) # book, chapter, verse (from search results)
    badge_activated = pyqtSignal(str)              # badge_type: commentary|crosslinks|media

    def __init__(self, parent=None):
        super().__init__(parent)
        self._book: str | None = None
        self._chapter: int | None = None
        self._selected_verse: int | None = None
        self._verse_widgets: dict[int, VerseWidget] = {}
        self._diff_mode = False
        self._diff_edition_b = "1830"

        # Navigation history
        self._nav_history: list[tuple[str, int, int]] = []
        self._nav_pos: int = -1
        self._nav_jumping: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setStyleSheet(f"QFrame {{ background: {SURFACE}; border-bottom: 1px solid {OVERLAY}; }}")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 6, 12, 6)
        tb_layout.setSpacing(10)

        _nav_btn_style = f"""
            QPushButton {{
                background: transparent; color: {SUBTEXT}; border: none;
                border-radius: 4px; padding: 2px 6px; font-size: 16px;
            }}
            QPushButton:hover:enabled {{ background: {OVERLAY}; color: {TEXT}; }}
            QPushButton:disabled {{ color: {OVERLAY1}; }}
        """
        self._back_btn = QPushButton("←")
        self._back_btn.setFixedWidth(30)
        self._back_btn.setToolTip("Back")
        self._back_btn.setEnabled(False)
        self._back_btn.setStyleSheet(_nav_btn_style)
        self._back_btn.clicked.connect(self._nav_back)
        tb_layout.addWidget(self._back_btn)

        self._fwd_btn = QPushButton("→")
        self._fwd_btn.setFixedWidth(30)
        self._fwd_btn.setToolTip("Forward")
        self._fwd_btn.setEnabled(False)
        self._fwd_btn.setStyleSheet(_nav_btn_style)
        self._fwd_btn.clicked.connect(self._nav_forward)
        tb_layout.addWidget(self._fwd_btn)

        self._title_label = QLabel("Select a chapter")
        self._title_label.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: bold;")
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedWidth(200)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {OVERLAY}; color: {TEXT}; border: 1px solid {OVERLAY1};
                border-radius: 4px; padding: 3px 8px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
        """)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        tb_layout.addWidget(self._search_input)

        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._run_inline_search)

        ed_label = QLabel("Edition:")
        ed_label.setStyleSheet(f"color: {SUBTEXT}; font-size: 12px;")
        tb_layout.addWidget(ed_label)

        self._edition_combo = QComboBox()
        self._edition_combo.addItems(EDITIONS)
        saved_edition = get_pref("last_edition", "2013")
        self._edition_combo.setCurrentText(
            saved_edition if saved_edition in EDITIONS else "2013"
        )
        self._edition_combo.setStyleSheet(f"""
            QComboBox {{
                background: {OVERLAY}; color: {TEXT}; border: 1px solid {OVERLAY1};
                border-radius: 4px; padding: 3px 8px; font-size: 12px; min-width: 60px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {OVERLAY}; color: {TEXT}; selection-background-color: {ACCENT};
            }}
        """)
        self._edition_combo.currentTextChanged.connect(self._on_edition_changed)
        tb_layout.addWidget(self._edition_combo)

        self._diff_btn = QPushButton("Compare...")
        self._diff_btn.setCheckable(True)
        self._diff_btn.setStyleSheet(f"""
            QPushButton {{
                background: {OVERLAY}; color: {SUBTEXT}; border: 1px solid {OVERLAY1};
                border-radius: 4px; padding: 3px 10px; font-size: 12px;
            }}
            QPushButton:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
            QPushButton:hover {{ background: {OVERLAY1}; }}
        """)
        self._diff_btn.toggled.connect(self._on_diff_toggled)
        tb_layout.addWidget(self._diff_btn)

        self._diff_ed_combo = QComboBox()
        self._diff_ed_combo.addItems(EDITIONS)
        self._diff_ed_combo.setCurrentText("1830")
        self._diff_ed_combo.setVisible(False)
        self._diff_ed_combo.setStyleSheet(self._edition_combo.styleSheet())
        self._diff_ed_combo.currentTextChanged.connect(self._on_diff_edition_changed)
        tb_layout.addWidget(self._diff_ed_combo)

        layout.addWidget(toolbar)

        # ── Scroll area with verses ───────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {DARK}; border: none; }}
            QScrollBar:vertical {{
                background: {SURFACE}; width: 8px; margin: 0;
            }}
            QScrollBar::handle:vertical {{ background: {OVERLAY1}; border-radius: 4px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._verses_container = QWidget()
        self._verses_container.setStyleSheet(f"background: {DARK};")
        self._verses_layout = QVBoxLayout(self._verses_container)
        self._verses_layout.setContentsMargins(0, 0, 0, 40)
        self._verses_layout.setSpacing(0)
        self._verses_layout.addStretch()

        self._scroll.setWidget(self._verses_container)
        layout.addWidget(self._scroll)

        # ── Search results panel (hidden until search is active) ──────────────
        self._results_scroll = QScrollArea()
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setVisible(False)
        self._results_scroll.setStyleSheet(self._scroll.styleSheet())

        self._results_container = QWidget()
        self._results_container.setStyleSheet(f"background: {DARK};")
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 8, 0, 40)
        self._results_layout.setSpacing(0)
        self._results_layout.addStretch()

        self._results_scroll.setWidget(self._results_container)
        layout.addWidget(self._results_scroll)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_chapter(self, book: str, chapter: int):
        self._book = book
        self._chapter = chapter
        self._selected_verse = None
        self._title_label.setText(f"{book} — Chapter {chapter}")
        self._refresh_verses()
        self.chapter_loaded.emit(book, chapter)

    def select_verse(self, verse: int):
        if self._book is None:
            return
        self._select(verse)

    def current_edition(self) -> str:
        return self._edition_combo.currentText()

    def refresh_badges(self):
        if self._book is None or self._chapter is None:
            return
        self._refresh_verses(keep_selection=True)

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh_verses(self, keep_selection: bool = False):
        while self._verses_layout.count() > 1:
            item = self._verses_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._verse_widgets.clear()

        if not self._book or not self._chapter:
            return

        edition = self._edition_combo.currentText()
        verses = get_chapter_verses(self._book, self._chapter, edition)
        badge_counts = get_verse_badge_counts(self._book, self._chapter)
        word_hls = get_chapter_word_highlights(self._book, self._chapter, edition)

        for vrow in verses:
            v_num = vrow["verse"]
            text = vrow["text"]
            badges = badge_counts.get(v_num, {})
            whl = word_hls.get(v_num, [])
            w = VerseWidget(self._book, self._chapter, v_num, text, badges, word_highlights=whl)
            w.clicked.connect(self._select)
            w.lookup_word.connect(self.lookup_word)
            w.word_hl_requested.connect(self._on_word_hl_add)
            w.word_hl_remove_requested.connect(self._on_word_hl_remove)
            w.badge_clicked.connect(self._on_badge_clicked)
            self._verses_layout.insertWidget(self._verses_layout.count() - 1, w)
            self._verse_widgets[v_num] = w

        if keep_selection and self._selected_verse in self._verse_widgets:
            self._verse_widgets[self._selected_verse].set_selected(True)
            if self._diff_mode:
                self._show_diff_for(self._selected_verse)

    def _select(self, verse: int):
        if self._selected_verse is not None and self._selected_verse in self._verse_widgets:
            self._verse_widgets[self._selected_verse].set_selected(False)
        self._selected_verse = verse
        if verse in self._verse_widgets:
            self._verse_widgets[verse].set_selected(True)
            self._scroll_to(verse)
        if self._diff_mode:
            self._show_diff_for(verse)
        if self._book:
            self._push_nav(self._book, self._chapter, verse)
            self.verse_activated.emit(self._book, self._chapter, verse)

    def _push_nav(self, book: str, chapter: int, verse: int):
        if self._nav_jumping:
            return
        entry = (book, chapter, verse)
        if self._nav_pos >= 0 and self._nav_history[self._nav_pos] == entry:
            return
        # Discard any forward history
        self._nav_history = self._nav_history[:self._nav_pos + 1]
        self._nav_history.append(entry)
        self._nav_pos = len(self._nav_history) - 1
        self._update_nav_buttons()

    def _nav_back(self):
        if self._nav_pos <= 0:
            return
        self._nav_jumping = True
        self._nav_pos -= 1
        book, chapter, verse = self._nav_history[self._nav_pos]
        if (book, chapter) != (self._book, self._chapter):
            self.navigate_requested.emit(book, chapter, verse)
        else:
            self._select(verse)
        self._nav_jumping = False
        self._update_nav_buttons()

    def _nav_forward(self):
        if self._nav_pos >= len(self._nav_history) - 1:
            return
        self._nav_jumping = True
        self._nav_pos += 1
        book, chapter, verse = self._nav_history[self._nav_pos]
        if (book, chapter) != (self._book, self._chapter):
            self.navigate_requested.emit(book, chapter, verse)
        else:
            self._select(verse)
        self._nav_jumping = False
        self._update_nav_buttons()

    def _update_nav_buttons(self):
        self._back_btn.setEnabled(self._nav_pos > 0)
        self._fwd_btn.setEnabled(self._nav_pos < len(self._nav_history) - 1)

    def _scroll_to(self, verse: int):
        w = self._verse_widgets.get(verse)
        if w:
            QTimer.singleShot(50, lambda: self._scroll.ensureWidgetVisible(w, 0, 80))

    def _on_badge_clicked(self, verse: int, badge_type: str):
        self._select(verse)
        self.badge_activated.emit(badge_type)

    def _on_word_hl_add(self, verse: int, start: int, end: int, color: str):
        if not self._book:
            return
        edition = self._edition_combo.currentText()
        add_word_highlight(self._book, self._chapter, verse, start, end, color, edition)
        # Refresh only this widget's word highlights
        w = self._verse_widgets.get(verse)
        if w:
            from backend.db_api import get_word_highlights
            w.set_word_highlights(get_word_highlights(self._book, self._chapter, verse, edition))

    def _on_word_hl_remove(self, highlight_id: int):
        remove_word_highlight(highlight_id)
        if self._book and self._chapter:
            edition = self._edition_combo.currentText()
            word_hls = get_chapter_word_highlights(self._book, self._chapter, edition)
            for verse, w in self._verse_widgets.items():
                w.set_word_highlights(word_hls.get(verse, []))

    def _on_search_text_changed(self, text: str):
        self._search_timer.stop()
        if not text.strip():
            self._clear_search()
            return
        self._search_timer.start()

    def _run_inline_search(self):
        query = self._search_input.text().strip()
        if not query:
            return
        edition = self._edition_combo.currentText()
        try:
            rows = search_all(query, edition, limit_each=30)
        except ValueError:
            rows = []

        # Clear old results (leave stretch at end)
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            empty = QLabel("No results found.")
            empty.setStyleSheet(f"color: {SUBTEXT}; font-size: 13px; padding: 20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._results_layout.insertWidget(0, empty)
        else:
            for i, row in enumerate(rows):
                self._results_layout.insertWidget(i, self._make_result_row(row, query))

        self._scroll.setVisible(False)
        self._results_scroll.setVisible(True)

    def _make_result_row(self, row: dict, query: str) -> QFrame:
        """Build one clickable result row."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{ background: {SURFACE}; border-bottom: 1px solid {OVERLAY}; }}
            QFrame:hover {{ background: {OVERLAY}; }}
        """)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(12, 8, 12, 8)
        inner.setSpacing(2)

        book = row["book"]
        chapter = row["chapter"]
        verse = row["verse"]
        source = row.get("source", "verse")
        snippet = row.get("snippet", "")

        ref_text = f"{book} {chapter}:{verse}"
        if source == "note":
            ref_text += "  [note]"
        elif source == "media":
            ref_text += "  [media]"

        ref_label = QLabel(ref_text)
        ref_label.setStyleSheet(f"color: {ACCENT}; font-size: 12px; font-weight: bold; background: transparent;")
        inner.addWidget(ref_label)

        # Highlight query in snippet
        if snippet:
            short = snippet[:120] + ("…" if len(snippet) > 120 else "")
            import html as _html
            escaped = _html.escape(short)
            q_esc = _html.escape(query)
            highlighted = escaped.replace(
                q_esc,
                f'<span style="background:{ACCENT};color:#1e1e2e;border-radius:2px;">{q_esc}</span>',
            )
            snip_label = QLabel(highlighted)
            snip_label.setWordWrap(True)
            snip_label.setTextFormat(Qt.TextFormat.RichText)
            snip_label.setStyleSheet(f"color: {SUBTEXT}; font-size: 12px; background: transparent;")
            inner.addWidget(snip_label)

        # Make the whole frame clickable
        def _navigate(b=book, c=chapter, v=verse):
            self._search_input.clear()  # clears search, restores chapter view
            self.navigate_requested.emit(b, c, v)

        frame.mousePressEvent = lambda _e, fn=_navigate: fn()
        return frame

    def _clear_search(self):
        self._results_scroll.setVisible(False)
        self._scroll.setVisible(True)

    def _on_edition_changed(self, edition: str):
        set_pref("last_edition", edition)
        self._refresh_verses(keep_selection=True)

    def _on_diff_toggled(self, checked: bool):
        self._diff_mode = checked
        self._diff_ed_combo.setVisible(checked)
        if not checked and self._selected_verse in self._verse_widgets:
            self._refresh_verses(keep_selection=True)

    def _on_diff_edition_changed(self, edition: str):
        self._diff_edition_b = edition
        if self._diff_mode and self._selected_verse:
            self._show_diff_for(self._selected_verse)

    def _show_diff_for(self, verse: int):
        if not self._book or verse not in self._verse_widgets:
            return
        edition_a = self._edition_combo.currentText()
        edition_b = self._diff_ed_combo.currentText()
        if edition_a == edition_b:
            return
        diff = get_diff(self._book, self._chapter, verse, edition_a, edition_b)
        w = self._verse_widgets[verse]
        idx = self._verses_layout.indexOf(w)
        next_item = self._verses_layout.itemAt(idx + 1)
        if next_item and isinstance(next_item.widget(), DiffOverlay):
            next_item.widget().deleteLater()
            self._verses_layout.removeItem(next_item)
        overlay = DiffOverlay(diff)
        self._verses_layout.insertWidget(idx + 1, overlay)
