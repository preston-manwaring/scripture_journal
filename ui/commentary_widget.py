from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QTextEdit, QPushButton, QLabel, QSizePolicy, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt
from backend.db_api import get_commentary, create_commentary, update_commentary, delete_commentary
from ui.themes import DARK, SURFACE, ELEVATED, OVERLAY, OVERLAY1, DIM, SUBTEXT, TEXT, ACCENT, RED
from ui.spell_checker import SpellCheckHighlighter, apply_spell_context_menu


def _item_style() -> str:
    return f"""
        QListWidget {{
            background: {DARK}; border: 1px solid {OVERLAY}; border-radius: 6px;
            color: {TEXT}; font-size: 12px;
        }}
        QListWidget::item {{ padding: 5px 8px; border-bottom: 1px solid {OVERLAY}; }}
        QListWidget::item:selected {{ background: {OVERLAY}; color: {TEXT}; }}
    """


def _btn_style(bg: str, fg: str) -> str:
    return (
        f"QPushButton {{ background:{bg}; color:{fg}; border:none;"
        f" border-radius:4px; padding:4px 12px; font-size:12px; }}"
        f"QPushButton:disabled {{ opacity:0.4; }}"
    )


class CommentaryWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._book: str | None = None
        self._chapter: int | None = None
        self._verse: int | None = None
        self._edit_id: int | None = None
        self._selected_note: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # ── Verse label ───────────────────────────────────────────────────────
        self._verse_label = QLabel("No verse selected")
        self._verse_label.setStyleSheet(f"color: {DIM}; font-size: 12px; font-style: italic;")
        layout.addWidget(self._verse_label)

        # ── Notes list (short previews for navigation) ────────────────────────
        self._list = QListWidget()
        self._list.setStyleSheet(_item_style())
        self._list.setAlternatingRowColors(False)
        self._list.setMaximumHeight(110)
        self._list.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setEnabled(False)
        self._edit_btn.setStyleSheet(_btn_style(bg=OVERLAY1, fg=TEXT))
        self._edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self._edit_btn)

        self._del_btn = QPushButton("Delete")
        self._del_btn.setEnabled(False)
        self._del_btn.setStyleSheet(_btn_style(bg=RED, fg=DARK))
        self._del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Full-text viewer ──────────────────────────────────────────────────
        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setPlaceholderText("Select a note above to read it…")
        self._viewer.setStyleSheet(f"""
            QTextEdit {{
                background: {SURFACE}; color: {TEXT};
                border: 1px solid {OVERLAY}; border-radius: 6px;
                padding: 6px; font-size: 13px;
            }}
        """)
        layout.addWidget(self._viewer, 1)   # stretch so it fills available space

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {OVERLAY};")
        layout.addWidget(sep)

        # ── Editor (new / edit) ───────────────────────────────────────────────
        self._editor_label = QLabel("New note:")
        self._editor_label.setStyleSheet(f"color: {SUBTEXT}; font-size: 12px;")
        layout.addWidget(self._editor_label)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText("Write your commentary here…")
        self._editor.setMaximumHeight(110)
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: {ELEVATED}; color: {TEXT};
                border: 1px solid {OVERLAY1}; border-radius: 6px;
                padding: 6px; font-size: 13px;
            }}
        """)
        layout.addWidget(self._editor)

        save_row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(_btn_style(bg=ACCENT, fg="white"))
        self._save_btn.clicked.connect(self._on_save)
        save_row.addWidget(self._save_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.setStyleSheet(_btn_style(bg=OVERLAY1, fg=TEXT))
        self._cancel_btn.clicked.connect(self._on_cancel)
        save_row.addWidget(self._cancel_btn)
        save_row.addStretch()
        layout.addLayout(save_row)

        self._editor.textChanged.connect(self._on_text_changed)

        self._spell_highlighter = SpellCheckHighlighter(self._editor.document())
        apply_spell_context_menu(self._editor)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_verse(self, book: str, chapter: int, verse: int):
        self._book = book
        self._chapter = chapter
        self._verse = verse
        self._edit_id = None
        self._verse_label.setText(f"{book} {chapter}:{verse}")
        self._refresh()

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh(self):
        self._list.blockSignals(True)
        self._list.clear()
        self._list.blockSignals(False)

        self._selected_note = None
        self._edit_btn.setEnabled(False)
        self._del_btn.setEnabled(False)
        self._viewer.clear()

        if self._book is None:
            return

        notes = get_commentary(self._book, self._chapter, self._verse)
        for note in notes:
            date_str = ""
            if note.get("created_at"):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(note["created_at"])
                    date_str = dt.astimezone().strftime("%b %-d, %Y") + "  "
                except Exception:
                    pass
            # Show first line (or up to 80 chars) as the list preview
            first_line = note["body"].split("\n")[0][:80]
            if len(note["body"]) > len(first_line):
                first_line += "…"
            item = QListWidgetItem(f"{date_str}{first_line}")
            item.setData(Qt.ItemDataRole.UserRole, note)
            self._list.addItem(item)

        # Auto-select the first note so Edit/Delete are immediately usable
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_item_changed(self, current: QListWidgetItem, previous):
        if current is None:
            self._selected_note = None
            self._edit_btn.setEnabled(False)
            self._del_btn.setEnabled(False)
            self._viewer.clear()
            return
        note = current.data(Qt.ItemDataRole.UserRole)
        self._selected_note = note
        self._edit_btn.setEnabled(True)
        self._del_btn.setEnabled(True)
        # Show full text in viewer
        self._viewer.setPlainText(note["body"])

    def _on_edit(self):
        if not self._selected_note:
            return
        note = self._selected_note
        self._edit_id = note["id"]
        self._editor.setPlainText(note["body"])
        self._editor_label.setText("Editing note:")
        self._cancel_btn.setVisible(True)
        self._save_btn.setEnabled(True)
        self._editor.setFocus()

    def _on_delete(self):
        if not self._selected_note:
            return
        delete_commentary(self._selected_note["id"])
        self._selected_note = None
        self._edit_id = None
        self._editor.clear()
        self._editor_label.setText("New note:")
        self._cancel_btn.setVisible(False)
        self._refresh()
        self.changed.emit()

    def _on_save(self):
        body = self._editor.toPlainText().strip()
        if not body or self._book is None:
            return
        if self._edit_id is not None:
            update_commentary(self._edit_id, body)
        else:
            create_commentary(self._book, self._chapter, self._verse, body)
        self._editor.clear()
        self._edit_id = None
        self._editor_label.setText("New note:")
        self._cancel_btn.setVisible(False)
        self._save_btn.setEnabled(False)
        self._refresh()
        self.changed.emit()

    def _on_cancel(self):
        self._editor.clear()
        self._edit_id = None
        self._editor_label.setText("New note:")
        self._cancel_btn.setVisible(False)
        self._save_btn.setEnabled(False)

    def _on_text_changed(self):
        self._save_btn.setEnabled(
            bool(self._editor.toPlainText().strip()) and self._book is not None
        )
