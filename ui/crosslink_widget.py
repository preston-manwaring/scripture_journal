from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QComboBox, QSpinBox, QLineEdit, QGroupBox, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt
from backend.db_api import (
    BOOK_ORDER, get_books, get_crosslinks, create_crosslink, delete_crosslink
)
from ui.themes import DARK, ELEVATED, OVERLAY, OVERLAY1, DIM, SUBTEXT, TEXT, ACCENT, RED

_BTN = "QPushButton {{ background:{bg}; color:{fg}; border:none; border-radius:4px; padding:4px 10px; font-size:12px; }}"


def _list_style() -> str:
    return f"""
        QListWidget {{
            background:{ELEVATED}; border:1px solid {OVERLAY}; border-radius:6px;
            color:{TEXT}; font-size:12px;
        }}
        QListWidget::item {{ padding:5px 8px; border-bottom:1px solid {OVERLAY}; }}
        QListWidget::item:selected {{ background:{OVERLAY}; }}
    """


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


class CrossLinkWidget(QWidget):
    navigate_to = pyqtSignal(str, int, int)  # book, chapter, verse
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._book: str | None = None
        self._chapter: int | None = None
        self._verse: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._verse_label = QLabel("No verse selected")
        self._verse_label.setStyleSheet(f"color:{DIM}; font-size:12px; font-style:italic;")
        layout.addWidget(self._verse_label)

        # ── Outbound links ────────────────────────────────────────────────────
        out_label = QLabel("This verse links to:")
        out_label.setStyleSheet(f"color:{SUBTEXT}; font-size:12px; font-weight:bold;")
        layout.addWidget(out_label)

        self._out_list = QListWidget()
        self._out_list.setStyleSheet(_list_style())
        self._out_list.setMaximumHeight(120)
        self._out_list.itemDoubleClicked.connect(lambda item: self._navigate(item, "outbound"))
        layout.addWidget(self._out_list)

        out_btn_row = QHBoxLayout()
        self._out_del_btn = QPushButton("Delete selected")
        self._out_del_btn.setEnabled(False)
        self._out_del_btn.setStyleSheet(_BTN.format(bg=RED, fg=DARK))
        self._out_del_btn.clicked.connect(lambda: self._delete_selected(self._out_list))
        out_btn_row.addWidget(self._out_del_btn)
        out_btn_row.addStretch()
        layout.addLayout(out_btn_row)
        self._out_list.itemSelectionChanged.connect(
            lambda: self._out_del_btn.setEnabled(bool(self._out_list.selectedItems()))
        )

        # ── Inbound links ─────────────────────────────────────────────────────
        in_label = QLabel("Linked from:")
        in_label.setStyleSheet(f"color:{SUBTEXT}; font-size:12px; font-weight:bold;")
        layout.addWidget(in_label)

        self._in_list = QListWidget()
        self._in_list.setStyleSheet(_list_style())
        self._in_list.setMaximumHeight(100)
        self._in_list.itemDoubleClicked.connect(lambda item: self._navigate(item, "inbound"))
        layout.addWidget(self._in_list)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{OVERLAY};")
        layout.addWidget(sep)

        # ── Add new link ──────────────────────────────────────────────────────
        add_label = QLabel("Add cross-link to:")
        add_label.setStyleSheet(f"color:{SUBTEXT}; font-size:12px; font-weight:bold;")
        layout.addWidget(add_label)

        form = QHBoxLayout()
        form.setSpacing(6)

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
        form.addWidget(self._v_spin)

        layout.addLayout(form)

        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("Optional note...")
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

        # Populate book combo
        books = get_books()
        self._book_combo.addItems(books)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_verse(self, book: str, chapter: int, verse: int):
        self._book = book
        self._chapter = chapter
        self._verse = verse
        self._verse_label.setText(f"{book} {chapter}:{verse}")
        self._refresh()

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh(self):
        self._out_list.clear()
        self._in_list.clear()
        if self._book is None:
            return
        links = get_crosslinks(self._book, self._chapter, self._verse)

        for link in links["outbound"]:
            target = f"{link['target_book']} {link['target_chapter']}:{link['target_verse']}"
            note = f"  — {link['note']}" if link["note"] else ""
            item = QListWidgetItem(f"-> {target}{note}")
            item.setData(Qt.ItemDataRole.UserRole, ("outbound", link))
            self._out_list.addItem(item)

        for link in links["inbound"]:
            source = f"{link['source_book']} {link['source_chapter']}:{link['source_verse']}"
            note = f"  — {link['note']}" if link["note"] else ""
            item = QListWidgetItem(f"<- {source}{note}")
            item.setData(Qt.ItemDataRole.UserRole, ("inbound", link))
            self._in_list.addItem(item)

    def _navigate(self, item: QListWidgetItem, direction: str):
        data = item.data(Qt.ItemDataRole.UserRole)
        _, link = data
        if direction == "outbound":
            self.navigate_to.emit(link["target_book"], link["target_chapter"], link["target_verse"])
        else:
            self.navigate_to.emit(link["source_book"], link["source_chapter"], link["source_verse"])

    def _delete_selected(self, lst: QListWidget):
        item = lst.currentItem()
        if not item:
            return
        _, link = item.data(Qt.ItemDataRole.UserRole)
        delete_crosslink(link["id"])
        self._refresh()
        self.changed.emit()

    def _on_add(self):
        if self._book is None:
            return
        target_book = self._book_combo.currentText()
        target_ch = self._ch_spin.value()
        target_v = self._v_spin.value()
        note = self._note_edit.text().strip() or None
        create_crosslink(
            self._book, self._chapter, self._verse,
            target_book, target_ch, target_v, note,
        )
        self._note_edit.clear()
        self._refresh()
        self.changed.emit()
