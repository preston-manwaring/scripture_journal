from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import pyqtSignal, Qt
from backend.database import get_connection
from ui.themes import DARK, TEXT, ACCENT, OVERLAY

BOOK_ORDER = [
    "1 Nephi","2 Nephi","Jacob","Enos","Jarom","Omni",
    "Words of Mormon","Mosiah","Alma","Helaman",
    "3 Nephi","4 Nephi","Mormon","Ether","Moroni",
]

# A slightly lighter tint of the base colour for hover (derived inline)
_HOVER = OVERLAY


class Sidebar(QTreeWidget):
    verse_selected = pyqtSignal(str, int, int)    # book, chapter, verse
    chapter_selected = pyqtSignal(str, int)       # book, chapter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setStyleSheet(f"""
            QTreeWidget {{
                background: {DARK};
                color: {TEXT};
                border: none;
                font-size: 13px;
            }}
            QTreeWidget::item {{ padding: 3px 4px; }}
            QTreeWidget::item:selected {{
                background: {ACCENT};
                color: white;
            }}
            QTreeWidget::item:hover {{ background: {_HOVER}; }}
        """)
        self._load_books()
        self.itemExpanded.connect(self._on_expanded)
        self.itemClicked.connect(self._on_clicked)

    def _load_books(self):
        conn = get_connection()
        try:
            rows = conn.execute("SELECT DISTINCT book FROM verses").fetchall()
            books = sorted([r["book"] for r in rows],
                           key=lambda b: BOOK_ORDER.index(b) if b in BOOK_ORDER else 99)
        finally:
            conn.close()

        for book in books:
            item = QTreeWidgetItem([book])
            item.setData(0, Qt.ItemDataRole.UserRole, ("book", book))
            # Placeholder child so the expand arrow shows
            item.addChild(QTreeWidgetItem(["Loading..."]))
            self.addTopLevelItem(item)

    def _on_expanded(self, item):
        role, value = item.data(0, Qt.ItemDataRole.UserRole)
        if role == "book" and item.child(0) and item.child(0).text(0) == "Loading...":
            item.takeChildren()
            self._load_chapters(item, value)
        elif role == "chapter":
            book, ch = value
            if item.child(0) and item.child(0).text(0) == "Loading...":
                item.takeChildren()
                self._load_verses(item, book, ch)

    def _load_chapters(self, parent_item, book):
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT DISTINCT chapter FROM verses WHERE book=? ORDER BY chapter", (book,)
            ).fetchall()
        finally:
            conn.close()
        for r in rows:
            ch = r["chapter"]
            ch_item = QTreeWidgetItem([f"Chapter {ch}"])
            ch_item.setData(0, Qt.ItemDataRole.UserRole, ("chapter", (book, ch)))
            ch_item.addChild(QTreeWidgetItem(["Loading..."]))
            parent_item.addChild(ch_item)

    def _load_verses(self, parent_item, book, chapter):
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT DISTINCT verse FROM verses WHERE book=? AND chapter=? ORDER BY verse",
                (book, chapter)
            ).fetchall()
        finally:
            conn.close()
        for r in rows:
            v = r["verse"]
            v_item = QTreeWidgetItem([f"Verse {v}"])
            v_item.setData(0, Qt.ItemDataRole.UserRole, ("verse", (book, chapter, v)))
            parent_item.addChild(v_item)

    def _on_clicked(self, item, _col):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        if data[0] == "verse":
            _, (book, ch, verse) = data
            self.verse_selected.emit(book, ch, verse)
        elif data[0] == "chapter":
            _, (book, ch) = data
            self.chapter_selected.emit(book, ch)

    def navigate_to(self, book: str, chapter: int, verse: int):
        """Programmatically select a verse (e.g., from cross-link navigation)."""
        for i in range(self.topLevelItemCount()):
            b_item = self.topLevelItem(i)
            b_role, b_val = b_item.data(0, Qt.ItemDataRole.UserRole)
            if b_val != book:
                continue
            b_item.setExpanded(True)
            for j in range(b_item.childCount()):
                c_item = b_item.child(j)
                c_role, c_val = c_item.data(0, Qt.ItemDataRole.UserRole)
                if c_val == (book, chapter):
                    c_item.setExpanded(True)
                    for k in range(c_item.childCount()):
                        v_item = c_item.child(k)
                        v_role, v_val = v_item.data(0, Qt.ItemDataRole.UserRole)
                        if v_val == (book, chapter, verse):
                            self.setCurrentItem(v_item)
                            self.verse_selected.emit(book, chapter, verse)
                            return
