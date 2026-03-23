from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTabWidget, QLabel, QStatusBar,
    QMenuBar, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout as QVL, QTextEdit, QPushButton, QProgressBar,
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QAction

from ui.sidebar import Sidebar
from ui.reading_pane import ReadingPane
from ui.commentary_widget import CommentaryWidget
from ui.crosslink_widget import CrossLinkWidget
from ui.media_widget import MediaWidget
from ui.export_widget import ExportDialog
from ui.search_widget import SearchDialog
from ui.dictionary_widget import DictionaryDialog
from ui.todo_widget import TodoDialog
from ui.themes import DARK, SURFACE, OVERLAY, OVERLAY1, SUBTEXT, TEXT, ACCENT, THEME_NAMES
from backend.db_api import get_pref, set_pref
from version import __version__, APP_NAME
import config as _cfg


_TAB_STYLE = f"""
    QTabWidget::pane {{
        background: {DARK}; border: none; border-top: 1px solid {OVERLAY};
    }}
    QTabBar::tab {{
        background: {SURFACE}; color: {SUBTEXT}; padding: 6px 16px;
        border: none; font-size: 12px;
    }}
    QTabBar::tab:selected {{ background: {DARK}; color: {TEXT}; border-top: 2px solid {ACCENT}; }}
    QTabBar::tab:hover {{ background: {OVERLAY}; }}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{__version__}")
        self.setMinimumSize(QSize(1100, 700))
        self._current = (None, None, None)  # book, chapter, verse

        self.setStyleSheet(f"""
            QMainWindow {{ background: {DARK}; }}
            QSplitter::handle {{ background: {OVERLAY}; }}
            QSplitter::handle:horizontal {{ width: 2px; }}
            QSplitter::handle:vertical {{ height: 2px; }}
        """)

        # ── Central layout ────────────────────────────────────────────────────
        central = QWidget()
        central.setStyleSheet(f"background: {DARK};")
        self.setCentralWidget(central)
        h_layout = QHBoxLayout(central)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        # ── Horizontal splitter (sidebar | content) ───────────────────────────
        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.setHandleWidth(2)

        # Sidebar
        self._sidebar = Sidebar()
        self._sidebar.setMinimumWidth(180)
        self._sidebar.setMaximumWidth(320)
        self._sidebar.verse_selected.connect(self._on_sidebar_verse)
        self._sidebar.chapter_selected.connect(
            lambda b, c: self._reading.load_chapter(b, c)
        )
        h_split.addWidget(self._sidebar)

        # Right panel: vertical splitter (reading pane | detail tabs)
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setHandleWidth(2)

        # Reading pane (top)
        self._reading = ReadingPane()
        self._reading.verse_activated.connect(self._on_verse_activated)
        self._reading.chapter_loaded.connect(self._on_chapter_loaded)
        self._reading.navigate_requested.connect(self._navigate_to)
        v_split.addWidget(self._reading)

        # Detail tabs (bottom)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.setMinimumHeight(180)

        self._commentary = CommentaryWidget()
        self._commentary.changed.connect(self._reading.refresh_badges)
        self._commentary.changed.connect(self._on_notes_changed)
        self._tabs.addTab(self._commentary, "Commentary")

        self._crosslinks = CrossLinkWidget()
        self._crosslinks.navigate_to.connect(self._navigate_to)
        self._crosslinks.changed.connect(self._reading.refresh_badges)
        self._tabs.addTab(self._crosslinks, "Cross-links")

        self._media = MediaWidget()
        self._media.changed.connect(self._reading.refresh_badges)
        self._tabs.addTab(self._media, "Media")

        v_split.addWidget(self._tabs)
        v_split.setSizes([450, 250])

        h_split.addWidget(v_split)
        h_split.setSizes([220, 880])
        h_layout.addWidget(h_split)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = QStatusBar()
        sb.setStyleSheet(f"QStatusBar {{ background: {SURFACE}; color: {SUBTEXT}; font-size: 11px; }}")
        self.setStatusBar(sb)
        self._status_label = QLabel("")
        sb.addWidget(self._status_label)

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(lambda: self._tabs.setCurrentIndex(0))
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(lambda: self._tabs.setCurrentIndex(1))
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(lambda: self._tabs.setCurrentIndex(2))

        # ── Export dialog ─────────────────────────────────────────────────────
        self._export_dlg = ExportDialog(self)

        # ── Dictionary dialog ─────────────────────────────────────────────────
        self._dict_dlg = DictionaryDialog(self)
        self._reading.lookup_word.connect(self._dict_dlg.lookup)

        # ── TODO dialog ───────────────────────────────────────────────────────
        self._todo_dlg = TodoDialog(self)
        self._todo_dlg.navigate_to.connect(self._navigate_to)

        # ── Search dialog (Cmd+F) ─────────────────────────────────────────────
        self._search_dlg = SearchDialog(
            edition_getter=self._reading.current_edition,
            parent=self,
        )
        self._search_dlg.navigate_to.connect(self._navigate_to)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._search_dlg.show_standard)

        # ── Menu bar ──────────────────────────────────────────────────────────
        menu = self.menuBar()
        menu.setStyleSheet(f"""
            QMenuBar {{ background: {SURFACE}; color: {TEXT}; font-size: 13px; }}
            QMenuBar::item:selected {{ background: {OVERLAY}; }}
            QMenu {{ background: {DARK}; color: {TEXT}; border: 1px solid {OVERLAY1}; }}
            QMenu::item:selected {{ background: {ACCENT}; color: white; }}
        """)

        # File menu
        file_menu = menu.addMenu("File")
        import_action = QAction("Import Notes from CSV...", self)
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(self._on_import_csv)
        file_menu.addAction(import_action)

        export_action = QAction("Export to PDF...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._export_dlg.show)
        file_menu.addAction(export_action)

        # Edit menu
        edit_menu = menu.addMenu("Edit")

        search_action = QAction("Search...", self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self._search_dlg.show_standard)
        edit_menu.addAction(search_action)

        ai_search_action = QAction("AI Search...", self)
        ai_search_action.triggered.connect(self._search_dlg.show_ai)
        edit_menu.addAction(ai_search_action)

        # View menu
        view_menu = menu.addMenu("View")

        todo_action = QAction("TODO List", self)
        todo_action.setShortcut(QKeySequence("Ctrl+T"))
        todo_action.triggered.connect(self._show_todo)
        view_menu.addAction(todo_action)

        view_menu.addSeparator()

        dict_action = QAction("Dictionary (1828 Webster's)...", self)
        dict_action.setShortcut(QKeySequence("Ctrl+D"))
        dict_action.triggered.connect(self._dict_dlg.show)
        view_menu.addAction(dict_action)

        view_menu.addSeparator()

        # Theme submenu
        theme_menu = view_menu.addMenu("Theme")
        current_theme = _cfg.get_theme()
        for name in THEME_NAMES:
            act = QAction(name, self)
            act.setCheckable(True)
            act.setChecked(name == current_theme)
            act.triggered.connect(lambda checked, n=name: self._on_set_theme(n))
            theme_menu.addAction(act)

        # Help menu
        help_menu = menu.addMenu("Help")
        about_action = QAction(f"About {APP_NAME}", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

        # ── Restore last position ─────────────────────────────────────────────
        self._restore_position()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_sidebar_verse(self, book: str, chapter: int, verse: int):
        if (book, chapter) != (self._current[0], self._current[1]):
            self._reading.load_chapter(book, chapter)
        self._reading.select_verse(verse)

    def _on_chapter_loaded(self, book: str, chapter: int):
        pass  # sidebar already reflects state; could sync here if needed

    def _on_verse_activated(self, book: str, chapter: int, verse: int):
        self._current = (book, chapter, verse)
        self._status_label.setText(f"{book}  {chapter}:{verse}")
        self._commentary.load_verse(book, chapter, verse)
        self._crosslinks.load_verse(book, chapter, verse)
        self._media.load_verse(book, chapter, verse)
        set_pref("last_book", book)
        set_pref("last_chapter", str(chapter))
        set_pref("last_verse", str(verse))

    def _navigate_to(self, book: str, chapter: int, verse: int):
        """Called by cross-link widget to jump to a different verse."""
        self._sidebar.navigate_to(book, chapter, verse)
        if (book, chapter) != (self._current[0], self._current[1]):
            self._reading.load_chapter(book, chapter)
        self._reading.select_verse(verse)

    def _restore_position(self):
        book = get_pref("last_book")
        chapter = get_pref("last_chapter")
        verse = get_pref("last_verse")
        if book and chapter and verse:
            try:
                self._navigate_to(book, int(chapter), int(verse))
            except Exception:
                pass

    def _show_todo(self):
        self._todo_dlg.refresh()
        self._todo_dlg.show()
        self._todo_dlg.raise_()

    def _on_notes_changed(self):
        if self._todo_dlg.isVisible():
            self._todo_dlg.refresh()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _on_set_theme(self, name: str):
        _cfg.set_theme(name)
        QMessageBox.information(
            self,
            "Theme Changed",
            f"Theme set to \"{name}\".\n\nRestart the app for the new theme to take full effect.",
        )

    # ── About ─────────────────────────────────────────────────────────────────

    def _on_about(self):
        from ui.themes import _p
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>"
            f"Version {__version__}<br><br>"
            f"A local desktop study journal for the Book of Mormon.<br>"
            f"All data stored in SQLite — no internet required.<br><br>"
            f"Theme: {_cfg.get_theme()}",
        )

    # ── CSV import ────────────────────────────────────────────────────────────

    def _on_import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Notes CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        dlg = _ImportNotesDialog(path, self)
        dlg.exec()
        # Refresh commentary panel if current verse is set
        book, chapter, verse = self._current
        if book:
            self._commentary.load_verse(book, chapter, verse)
            self._reading.refresh_badges()


class _ImportNotesWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, csv_path: str):
        super().__init__()
        self._path = csv_path

    def run(self):
        from backend.services.notes_importer import import_notes
        summary = import_notes(self._path, progress_cb=self.progress.emit)
        self.finished.emit(summary)


class _ImportNotesDialog(QDialog):
    def __init__(self, csv_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Notes")
        self.setMinimumWidth(500)
        self.setMinimumHeight(320)
        self.setStyleSheet(f"QDialog {{ background: {DARK}; color: {TEXT}; }}")

        layout = QVL(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            f"QTextEdit {{ background:{SURFACE}; color:{SUBTEXT}; border:1px solid {OVERLAY};"
            f" border-radius:6px; font-size:12px; font-family: monospace; }}"
        )
        layout.addWidget(self._log)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background:{OVERLAY}; border-radius:4px; height:6px; }}
            QProgressBar::chunk {{ background:{ACCENT}; border-radius:4px; }}
        """)
        layout.addWidget(self._bar)

        self._close_btn = QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.setStyleSheet(
            f"QPushButton {{ background:{OVERLAY1}; color:{TEXT}; border:none;"
            f" border-radius:4px; padding:5px 16px; font-size:12px; }}"
        )
        self._close_btn.clicked.connect(self.accept)
        layout.addWidget(self._close_btn)

        self._worker = _ImportNotesWorker(csv_path)
        self._worker.progress.connect(self._log.append)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, summary: dict):
        self._bar.setRange(0, 1)
        self._bar.setValue(1)
        self._log.append("")
        self._log.append(
            f"<b>Notes imported:</b> {summary['imported_notes']}  |  "
            f"<b>Highlights imported:</b> {summary['imported_highlights']}  |  "
            f"Non-BoM URL: {summary['skipped_bad_url']}  |  "
            f"Duplicates: {summary['skipped_duplicate']}"
        )
        if summary["errors"]:
            self._log.append(f"<b>Errors ({len(summary['errors'])}):</b>")
            for e in summary["errors"]:
                self._log.append(f"  {e}")
        self._close_btn.setEnabled(True)
