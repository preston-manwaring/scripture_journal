# Scripture Journal — Implementation Plan

## Current Status: v1.0.0 (complete)

All planned phases are implemented and running. This document reflects the
as-built architecture and serves as a reference for future work.

---

## Architecture

Single Python process. PyQt6 provides the UI; all DB access goes through
`backend/db_api.py` (pure Python, no HTTP). There is no FastAPI server at
runtime — the router files under `backend/routers/` are kept for reference
only.

```
scripture_journal/
├── app.py                        # Entry point
├── version.py                    # __version__ = "1.0.0"
├── config.py                     # config.ini read/write (theme, etc.)
├── config.ini                    # Runtime preferences (gitignored)
├── backend/
│   ├── database.py               # SQLite schema + get_connection()
│   ├── db_api.py                 # All read/write functions used by UI
│   └── services/
│       ├── tsv_importer.py       # One-time TSV → SQLite import
│       ├── verse_reconstructor.py# Token assembly → verse text
│       ├── og_fetcher.py         # Open Graph metadata + thumbnail fetch
│       ├── latex_generator.py    # Jinja2 → export.tex
│       └── notes_importer.py     # Church CSV → commentary/highlights
├── ui/
│   ├── themes.py                 # Color palettes; module-level constants
│   ├── main_window.py            # QMainWindow — layout, menus, shortcuts
│   ├── sidebar.py                # Lazy QTreeWidget: book→chapter→verse
│   ├── reading_pane.py           # Chapter scroll area + toolbar
│   ├── verse_widget.py           # Per-verse row: text, badge, highlight
│   ├── commentary_widget.py      # Note CRUD tab
│   ├── crosslink_widget.py       # Cross-link add/view/navigate tab
│   ├── media_widget.py           # Image + link preview card tab
│   ├── export_widget.py          # LaTeX + pdflatex + PDF viewer tab
│   ├── search_widget.py          # Standard + AI search dialog
│   └── import_dialog.py          # First-run TSV progress dialog
├── data/book-of-mormon/          # 15 TSV source files (git subtree)
├── db/journal.db                 # SQLite database (gitignored)
├── templates/
│   └── scripture_export.tex.j2   # Jinja2 LaTeX template
└── output/                       # Generated .tex / .pdf (gitignored)
```

---

## Key Design Decisions

### Direct DB access (no HTTP)
`backend/db_api.py` is imported directly by UI widgets. Queries run on the
main thread for reads (fast) and use SQLite WAL mode for writes.

### Theme system
`ui/themes.py` exports module-level color constants (`DARK`, `ACCENT`, …)
resolved at import time from `config.ini`. All widget stylesheets read from
these constants, so a theme change takes effect on the next launch without
any widget rebuilding at runtime.

### Thread model
Three operations run on `QThread` to keep the UI responsive:
- TSV import (`_ImportWorker` in `import_dialog.py`)
- Open Graph fetch (`_OGFetchWorker` in `media_widget.py`)
- pdflatex compilation (`_PdfWorker` in `export_widget.py`)
- Claude API streaming (`_ClaudeWorker` in `search_widget.py`)

### PDF viewing
`QWebEngineView` loads the compiled PDF via a `file://` URL. The WebEngine
import must appear before `QApplication` is instantiated (handled in
`app.py`).

### Diff rendering
`DiffOverlay` is a plain `QWidget` inserted directly after the selected
`VerseWidget` in the scroll layout. It is removed and recreated whenever the
user changes verse or edition.

---

## SQLite Schema

```sql
-- Reconstructed verse text
CREATE TABLE verses (
    id INTEGER PRIMARY KEY,
    book TEXT, chapter INTEGER, verse INTEGER, edition TEXT, text TEXT,
    UNIQUE(book, chapter, verse, edition)
);

-- Raw tokens (for diff)
CREATE TABLE verse_tokens (
    id INTEGER PRIMARY KEY,
    book TEXT, chapter INTEGER, verse INTEGER,
    wid TEXT, edition TEXT, token TEXT, is_space INTEGER DEFAULT 0,
    UNIQUE(book, chapter, verse, wid, edition)
);

CREATE TABLE commentary (
    id INTEGER PRIMARY KEY,
    book TEXT, chapter INTEGER, verse INTEGER,
    edition TEXT,           -- NULL = edition-agnostic
    body TEXT,
    created_at TEXT, updated_at TEXT
);

CREATE TABLE cross_links (
    id INTEGER PRIMARY KEY,
    source_book TEXT, source_chapter INTEGER, source_verse INTEGER,
    target_book TEXT, target_chapter INTEGER, target_verse INTEGER,
    note TEXT, created_at TEXT
);

CREATE TABLE media (
    id INTEGER PRIMARY KEY,
    book TEXT, chapter INTEGER, verse INTEGER,
    type TEXT,              -- "image" | "link"
    filename TEXT, mime_type TEXT, data BLOB,   -- images
    url TEXT, og_title TEXT, og_description TEXT,
    og_image BLOB, og_image_mime TEXT,          -- link previews
    caption TEXT, created_at TEXT
);

CREATE TABLE highlights (
    id INTEGER PRIMARY KEY,
    book TEXT, chapter INTEGER, verse INTEGER,
    color TEXT DEFAULT '#f9e2af',
    created_at TEXT,
    UNIQUE(book, chapter, verse)
);

CREATE TABLE import_log (
    id INTEGER PRIMARY KEY,
    filename TEXT, imported_at TEXT, row_count INTEGER
);

CREATE TABLE preferences (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## Implemented Phases

### Phase 1 — Backend & import ✓
- `database.py` schema, `tsv_importer.py`, `verse_reconstructor.py`
- `db_api.py` scripture read functions

### Phase 2 — Core reading UI ✓
- `sidebar.py`, `reading_pane.py`, `verse_widget.py`
- Edition selector; chapter-level loading

### Phase 3 — Diff ✓
- `DiffOverlay` in `reading_pane.py`
- Token-level colored inline diff

### Phase 4 — Commentary & Cross-links ✓
- `commentary_widget.py`, `crosslink_widget.py`
- Full CRUD; outbound + inbound navigation

### Phase 5 — Highlights ✓
- Click verse number to toggle; right-click for color picker
- 6 preset colors; `highlights` table; badge counts

### Phase 6 — Media ✓
- `media_widget.py`, `og_fetcher.py`
- Image BLOB storage; OG preview cards; thumbnail display

### Phase 7 — LaTeX export & PDF ✓
- `latex_generator.py`, `export_widget.py`
- Jinja2 template with `<<`/`>>` delimiters; pdflatex QThread; QWebEngineView

### Phase 8 — CSV import ✓
- `notes_importer.py`: Church website URL parsing → book/chapter/verse
- Notes → `commentary`; bare highlights → `highlights`; duplicate detection

### Phase 9 — Search ✓
- Standard: LIKE search across verses, commentary, and media metadata
- AI: streaming `claude-opus-4-6` with adaptive thinking; citation parsing

### Phase 10 — Themes & config ✓
- `ui/themes.py`: 4 palettes (Catppuccin Mocha, Catppuccin Latte, Nord, Solarized Dark)
- `config.py` + `config.ini`; theme menu in View menu

### Phase 11 — Version & docs ✓
- `version.py`; version in title bar and About dialog
- `.gitignore`, `README.md`, `spec.md`, `plan.md` updated

---

## Potential Future Work

- **Full-text search index**: add SQLite FTS5 virtual table for faster search
- **Verse bookmarks**: lightweight bookmark list separate from commentary
- **Export templates**: multiple LaTeX styles (academic, devotional, minimal)
- **Dark/light auto-switch**: follow macOS appearance setting
- **Keyboard navigation**: `←`/`→` for prev/next chapter; `↑`/`↓` for prev/next verse
- **Tag system**: tag commentary notes by topic for filtering
- **Sync**: optional encrypted export/import for backup
