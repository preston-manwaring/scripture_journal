"""
TODO tracker — scans all commentary notes for TODO: tags and displays
them in a collapsible tree grouped by book → chapter → verse.

Clicking any item navigates to the associated verse.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QKeySequence, QShortcut, QFont, QColor, QBrush

from backend.db_api import get_todos
from ui.themes import (
    DARK, SURFACE, ELEVATED, OVERLAY, OVERLAY1,
    SUBTEXT, TEXT, ACCENT, GREEN,
)

_TAG_COLOR   = "#f9e2af"   # warm yellow for TODO: label
_DONE_COLOR  = "#a6e3a1"   # green for completed items


class TodoDialog(QDialog):
    navigate_to = pyqtSignal(str, int, int)   # book, chapter, verse

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("TODO List")
        self.setMinimumSize(QSize(480, 520))
        self.setStyleSheet(f"QDialog {{ background: {DARK}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Header row ────────────────────────────────────────────────────────
        header = QHBoxLayout()

        self._count_label = QLabel()
        self._count_label.setStyleSheet(f"color: {SUBTEXT}; font-size: 12px;")
        header.addWidget(self._count_label)
        header.addStretch()

        expand_btn = QPushButton("Expand All")
        expand_btn.setFixedHeight(24)
        expand_btn.setStyleSheet(self._btn_style())
        expand_btn.clicked.connect(self._tree.expandAll if hasattr(self, "_tree") else lambda: None)

        collapse_btn = QPushButton("Collapse All")
        collapse_btn.setFixedHeight(24)
        collapse_btn.setStyleSheet(self._btn_style())

        refresh_btn = QPushButton("↺ Refresh")
        refresh_btn.setFixedHeight(24)
        refresh_btn.setStyleSheet(self._btn_style(accent=True))
        refresh_btn.clicked.connect(self.refresh)

        header.addWidget(expand_btn)
        header.addWidget(collapse_btn)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # ── Tree ──────────────────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(1)
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(20)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {DARK}; color: {TEXT};
                border: 1px solid {OVERLAY}; border-radius: 6px;
                font-size: 13px;
            }}
            QTreeWidget::item {{
                padding: 4px 6px;
                border-bottom: 1px solid {OVERLAY};
            }}
            QTreeWidget::item:selected {{
                background: {OVERLAY}; color: {TEXT};
            }}
            QTreeWidget::item:hover {{
                background: {SURFACE};
            }}
            QTreeWidget::branch {{
                background: {DARK};
            }}
        """)
        self._tree.itemActivated.connect(self._on_activated)
        layout.addWidget(self._tree)

        # Hint
        hint = QLabel("Double-click or press Enter to navigate to a verse.")
        hint.setStyleSheet(f"color: {SUBTEXT}; font-size: 11px; font-style: italic;")
        layout.addWidget(hint)

        # Wire up expand/collapse now that tree exists
        expand_btn.clicked.disconnect()
        expand_btn.clicked.connect(self._tree.expandAll)
        collapse_btn.clicked.connect(self._tree.collapseAll)

        QShortcut(QKeySequence("Escape"), self).activated.connect(self.hide)

        self.refresh()

    # ── Public ────────────────────────────────────────────────────────────────

    def refresh(self):
        self._tree.clear()
        items = get_todos()
        if not items:
            placeholder = QTreeWidgetItem(["No TODO items found in your notes."])
            placeholder.setForeground(0, QBrush(QColor(SUBTEXT)))
            self._tree.addTopLevelItem(placeholder)
            self._count_label.setText("0 TODO items")
            return

        self._count_label.setText(
            f"{len(items)} TODO item{'s' if len(items) != 1 else ''}"
        )

        # Build tree: book → chapter → todo items
        book_nodes:    dict[str, QTreeWidgetItem] = {}
        chapter_nodes: dict[tuple, QTreeWidgetItem] = {}

        for item in items:
            book    = item["book"]
            chapter = item["chapter"]
            verse   = item["verse"]
            text    = item["todo_text"]

            # Book node
            if book not in book_nodes:
                bn = QTreeWidgetItem([book])
                bold = QFont()
                bold.setBold(True)
                bn.setFont(0, bold)
                bn.setForeground(0, QBrush(QColor(ACCENT)))
                self._tree.addTopLevelItem(bn)
                book_nodes[book] = bn

            # Chapter node
            ch_key = (book, chapter)
            if ch_key not in chapter_nodes:
                cn = QTreeWidgetItem([f"Chapter {chapter}"])
                cn.setForeground(0, QBrush(QColor(TEXT)))
                book_nodes[book].addChild(cn)
                chapter_nodes[ch_key] = cn

            # TODO item node
            todo_node = QTreeWidgetItem()
            todo_node.setData(0, Qt.ItemDataRole.UserRole, (book, chapter, verse))

            # Format: "v.N  TODO: text…"
            display = f"v.{verse}  {text}"
            if len(display) > 100:
                display = display[:97] + "…"
            todo_node.setText(0, display)
            todo_node.setToolTip(0, text)

            # Colour the TODO: portion
            todo_node.setForeground(0, QBrush(QColor(_TAG_COLOR)))
            chapter_nodes[ch_key].addChild(todo_node)

        self._tree.expandAll()

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_activated(self, item: QTreeWidgetItem, _column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            book, chapter, verse = data
            self.navigate_to.emit(book, chapter, verse)

    def _btn_style(self, accent: bool = False) -> str:
        bg = ACCENT if accent else OVERLAY
        fg = "white" if accent else TEXT
        return (
            f"QPushButton {{ background: {bg}; color: {fg}; border: none; "
            f"border-radius: 4px; padding: 2px 10px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {OVERLAY1 if not accent else '#6b72d0'}; }}"
        )

    def closeEvent(self, event):
        event.ignore()
        self.hide()
