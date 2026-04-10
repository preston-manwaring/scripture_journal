from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QComboBox, QSpinBox, QLineEdit, QFrame, QToolTip,
)
from PyQt6.QtCore import pyqtSignal, Qt, QPoint
from PyQt6.QtGui import QCursor

from backend.db_api import (
    BOOK_ORDER, get_books, get_crosslinks, create_crosslink, delete_crosslink,
    get_verse_range_text,
)
from ui.themes import DARK, ELEVATED, OVERLAY, OVERLAY1, DIM, SUBTEXT, TEXT, ACCENT, RED

_BTN = "QPushButton {{ background:{bg}; color:{fg}; border:none; border-radius:4px; padding:4px 10px; font-size:12px; }}"


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
        f" border-radius:4px; padding:3px 4px; font-size:12px; }}"
    )


def _ref_label(link: dict, direction: str) -> str:
    """Format a human-readable verse reference for a link."""
    if direction == "outbound":
        book, ch, vs = link["target_book"], link["target_chapter"], link["target_verse"]
        ve = link.get("target_verse_end")
    else:
        book, ch, vs = link["source_book"], link["source_chapter"], link["source_verse"]
        ve = link.get("source_verse_end")
    if ve and ve > vs:
        return f"{book} {ch}:{vs}–{ve}"
    return f"{book} {ch}:{vs}"


class _LinkRow(QFrame):
    """Single clickable cross-link row with hover verse preview."""

    navigate = pyqtSignal(str, int, int)   # book, chapter, verse
    delete_requested = pyqtSignal(int)     # link id

    def __init__(self, link: dict, direction: str, edition_getter, parent=None):
        super().__init__(parent)
        self._link = link
        self._direction = direction
        self._get_edition = edition_getter
        self._tooltip_text: str | None = None

        self.setStyleSheet(f"""
            _LinkRow, QFrame {{
                background: {ELEVATED}; border-radius: 5px;
                border: 1px solid {OVERLAY};
            }}
            _LinkRow:hover, QFrame:hover {{ border-color: {ACCENT}; }}
        """)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)

        arrow = QLabel("→" if direction == "outbound" else "←")
        arrow.setStyleSheet(f"color: {ACCENT}; font-size: 13px; background: transparent; border: none;")
        row.addWidget(arrow)

        ref = _ref_label(link, direction)
        ref_lbl = QLabel(ref)
        ref_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; text-decoration: underline; "
            f"background: transparent; border: none;"
        )
        row.addWidget(ref_lbl)

        note = link.get("note") or ""
        if note:
            note_lbl = QLabel(f"— {note}")
            note_lbl.setStyleSheet(f"color: {SUBTEXT}; font-size: 11px; background: transparent; border: none;")
            note_lbl.setWordWrap(True)
            row.addWidget(note_lbl, 1)
        else:
            row.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(20, 20)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {SUBTEXT}; border: none; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {RED}; }}"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(link["id"]))
        row.addWidget(del_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            link = self._link
            if self._direction == "outbound":
                self.navigate.emit(link["target_book"], link["target_chapter"], link["target_verse"])
            else:
                self.navigate.emit(link["source_book"], link["source_chapter"], link["source_verse"])
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if self._tooltip_text is None:
            self._tooltip_text = self._fetch_verse_text()
        if self._tooltip_text:
            QToolTip.showText(QCursor.pos(), self._tooltip_text, self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def _fetch_verse_text(self) -> str:
        link = self._link
        edition = self._get_edition()
        if self._direction == "outbound":
            return get_verse_range_text(
                link["target_book"], link["target_chapter"],
                link["target_verse"], link.get("target_verse_end"),
                edition,
            )
        else:
            return get_verse_range_text(
                link["source_book"], link["source_chapter"],
                link["source_verse"], link.get("source_verse_end"),
                edition,
            )


class CrossLinkWidget(QWidget):
    navigate_to = pyqtSignal(str, int, int)
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._book: str | None = None
        self._chapter: int | None = None
        self._verse: int | None = None
        self._edition_getter = lambda: "2013"  # overridden by main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._verse_label = QLabel("No verse selected")
        self._verse_label.setStyleSheet(f"color:{DIM}; font-size:12px; font-style:italic;")
        layout.addWidget(self._verse_label)

        # ── Outbound links ────────────────────────────────────────────────────
        out_label = QLabel("This verse links to:")
        out_label.setStyleSheet(f"color:{SUBTEXT}; font-size:12px; font-weight:bold;")
        layout.addWidget(out_label)

        self._out_scroll = QScrollArea()
        self._out_scroll.setWidgetResizable(True)
        self._out_scroll.setMaximumHeight(130)
        self._out_scroll.setStyleSheet(
            f"QScrollArea {{ background: {DARK}; border: none; }}"
            f"QScrollBar:vertical {{ background:{DARK}; width:6px; }}"
            f"QScrollBar::handle:vertical {{ background:{OVERLAY}; border-radius:3px; }}"
        )
        self._out_container = QWidget()
        self._out_container.setStyleSheet(f"background: {DARK};")
        self._out_layout = QVBoxLayout(self._out_container)
        self._out_layout.setContentsMargins(0, 0, 0, 0)
        self._out_layout.setSpacing(3)
        self._out_layout.addStretch()
        self._out_scroll.setWidget(self._out_container)
        layout.addWidget(self._out_scroll)

        # ── Inbound links ─────────────────────────────────────────────────────
        in_label = QLabel("Linked from:")
        in_label.setStyleSheet(f"color:{SUBTEXT}; font-size:12px; font-weight:bold;")
        layout.addWidget(in_label)

        self._in_scroll = QScrollArea()
        self._in_scroll.setWidgetResizable(True)
        self._in_scroll.setMaximumHeight(100)
        self._in_scroll.setStyleSheet(self._out_scroll.styleSheet())
        self._in_container = QWidget()
        self._in_container.setStyleSheet(f"background: {DARK};")
        self._in_layout = QVBoxLayout(self._in_container)
        self._in_layout.setContentsMargins(0, 0, 0, 0)
        self._in_layout.setSpacing(3)
        self._in_layout.addStretch()
        self._in_scroll.setWidget(self._in_container)
        layout.addWidget(self._in_scroll)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{OVERLAY};")
        layout.addWidget(sep)

        # ── Add new link ──────────────────────────────────────────────────────
        add_label = QLabel("Add cross-link:")
        add_label.setStyleSheet(f"color:{SUBTEXT}; font-size:12px; font-weight:bold;")
        layout.addWidget(add_label)

        # Source range row
        src_row = QHBoxLayout()
        src_row.setSpacing(4)
        from_lbl = QLabel("From:")
        from_lbl.setStyleSheet(f"color:{SUBTEXT}; font-size:11px;")
        src_row.addWidget(from_lbl)
        self._src_label = QLabel("—")
        self._src_label.setStyleSheet(f"color:{TEXT}; font-size:11px;")
        src_row.addWidget(self._src_label)
        dash_src = QLabel("–")
        dash_src.setStyleSheet(f"color:{SUBTEXT}; font-size:12px;")
        src_row.addWidget(dash_src)
        self._sv_end_spin = QSpinBox()
        self._sv_end_spin.setRange(1, 999)
        self._sv_end_spin.setPrefix("v.")
        self._sv_end_spin.setStyleSheet(_spin_style())
        self._sv_end_spin.setToolTip("Extend source to a range (leave same as start for single verse)")
        src_row.addWidget(self._sv_end_spin)
        src_row.addStretch()
        layout.addLayout(src_row)

        to_lbl = QLabel("To:")
        to_lbl.setStyleSheet(f"color:{SUBTEXT}; font-size:11px;")
        layout.addWidget(to_lbl)

        form = QHBoxLayout()
        form.setSpacing(4)

        self._book_combo = QComboBox()
        self._book_combo.setStyleSheet(_combo_style())
        form.addWidget(self._book_combo)

        self._ch_spin = QSpinBox()
        self._ch_spin.setRange(1, 99)
        self._ch_spin.setPrefix("Ch ")
        self._ch_spin.setStyleSheet(_spin_style())
        form.addWidget(self._ch_spin)

        self._v_spin = QSpinBox()
        self._v_spin.setRange(1, 999)
        self._v_spin.setPrefix("v.")
        self._v_spin.setStyleSheet(_spin_style())
        self._v_spin.valueChanged.connect(self._on_verse_start_changed)
        form.addWidget(self._v_spin)

        dash = QLabel("–")
        dash.setStyleSheet(f"color:{SUBTEXT}; font-size:12px;")
        form.addWidget(dash)

        self._v_end_spin = QSpinBox()
        self._v_end_spin.setRange(1, 999)
        self._v_end_spin.setPrefix("v.")
        self._v_end_spin.setStyleSheet(_spin_style())
        self._v_end_spin.setToolTip("End verse (for a range — leave same as start for single verse)")
        form.addWidget(self._v_end_spin)

        layout.addLayout(form)

        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("Optional note…")
        self._note_edit.setStyleSheet(
            f"QLineEdit {{ background:{ELEVATED}; color:{TEXT}; border:1px solid {OVERLAY1};"
            f" border-radius:4px; padding:4px 8px; font-size:12px; }}"
        )
        layout.addWidget(self._note_edit)

        add_btn = QPushButton("Add Cross-link")
        add_btn.setStyleSheet(_BTN.format(bg=ACCENT, fg="white"))
        add_btn.clicked.connect(self._on_add)
        layout.addWidget(add_btn)
        layout.addStretch()

        books = get_books()
        self._book_combo.addItems(books)

    def set_edition_getter(self, getter):
        self._edition_getter = getter

    # ── Public API ────────────────────────────────────────────────────────────

    def load_verse(self, book: str, chapter: int, verse: int):
        self._book = book
        self._chapter = chapter
        self._verse = verse
        self._verse_label.setText(f"{book} {chapter}:{verse}")
        self._src_label.setText(f"{book} {chapter}:{verse}")
        self._sv_end_spin.setValue(verse)
        self._refresh()

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh(self):
        # Clear outbound
        while self._out_layout.count() > 1:
            item = self._out_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Clear inbound
        while self._in_layout.count() > 1:
            item = self._in_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._book is None:
            return

        links = get_crosslinks(self._book, self._chapter, self._verse)

        for link in links["outbound"]:
            row = _LinkRow(link, "outbound", self._edition_getter)
            row.navigate.connect(self.navigate_to)
            row.delete_requested.connect(self._on_delete)
            self._out_layout.insertWidget(self._out_layout.count() - 1, row)

        for link in links["inbound"]:
            row = _LinkRow(link, "inbound", self._edition_getter)
            row.navigate.connect(self.navigate_to)
            row.delete_requested.connect(self._on_delete)
            self._in_layout.insertWidget(self._in_layout.count() - 1, row)

    def _on_delete(self, link_id: int):
        delete_crosslink(link_id)
        self._refresh()
        self.changed.emit()

    def _on_verse_start_changed(self, value: int):
        if self._v_end_spin.value() < value:
            self._v_end_spin.setValue(value)

    def _on_add(self):
        if self._book is None:
            return
        target_book = self._book_combo.currentText()
        target_ch = self._ch_spin.value()
        target_v = self._v_spin.value()
        target_v_end = self._v_end_spin.value()
        src_v_end = self._sv_end_spin.value()
        note = self._note_edit.text().strip() or None
        create_crosslink(
            self._book, self._chapter, self._verse,
            target_book, target_ch, target_v,
            note=note,
            target_verse_end=target_v_end if target_v_end > target_v else None,
            source_verse_end=src_v_end if src_v_end > self._verse else None,
        )
        self._note_edit.clear()
        self._refresh()
        self.changed.emit()
