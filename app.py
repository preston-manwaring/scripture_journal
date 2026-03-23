#!/usr/bin/env python3
"""Scripture Journal — entry point."""
import sys
import os

# Ensure project root is on the path regardless of cwd
sys.path.insert(0, os.path.dirname(__file__))

# WebEngine must be imported before QApplication is instantiated
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401 (side-effect import)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from version import __version__, APP_NAME
from ui.themes import build_app_stylesheet
from backend.database import init_db, get_connection
from backend.services.tsv_importer import needs_import
from backend.services.dict_importer import needs_import as dict_needs_import


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ScriptureJournal")

    app.setStyleSheet(build_app_stylesheet())

    # ── Init DB ───────────────────────────────────────────────────────────────
    init_db()

    conn = get_connection()
    import_needed = needs_import(conn)
    conn.close()

    if import_needed:
        from ui.import_dialog import ImportDialog
        dlg = ImportDialog()
        dlg.exec()

    if dict_needs_import():
        from ui.dict_import_dialog import DictImportDialog
        dlg = DictImportDialog()
        dlg.exec()

    # ── Main window ───────────────────────────────────────────────────────────
    from ui.main_window import MainWindow
    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
