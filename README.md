# Scripture Journal

A local desktop study journal for the Book of Mormon built with **PyQt6** and **SQLite**.
All data lives on your machine — no cloud, no account, no internet required (except for AI Search and link previews).

---

## Features

| Feature | Description |
|---------|-------------|
| **8 Editions** | Display any of the 1830, 1837, 1840, 1841, 1879, 1920, 1981, or 2013 editions |
| **Edition Compare** | Token-level diff between any two editions, shown inline below the selected verse |
| **Word Highlights** | Right-click any word or selection to highlight it in one of six colours; highlights are edition-aware |
| **Commentary** | Write, edit, and delete personal notes attached to individual verses; real-time spell checking with Book of Mormon vocabulary support |
| **Cross-links** | Link any verse to another and navigate outbound and inbound links |
| **Media** | Attach images (stored as SQLite BLOBs) or paste URLs for Open Graph preview cards |
| **Search bar** | Persistent search bar in the reading pane; results link directly to verses |
| **Standard Search** | Full-text search across verse text, notes, and media metadata; results colour-coded by source |
| **AI Search** | Ask a natural-language question; Claude suggests relevant verses and incorporates your personal notes as context |
| **TODO Tracker** | Tag any note with `TODO:` and track all open items in a navigable tree (View → TODO List) |
| **LaTeX Export** | Export any range of verses with commentary to `.tex`; compile and preview PDF in-app |
| **CSV Import** | Import highlights and notes from the Church of Jesus Christ study app export |
| **Themes** | Four colour themes: Catppuccin Mocha, Catppuccin Latte, Nord, Solarized Dark |

---

## Setup

### Requirements

- macOS (primary target; Darwin 25+)
- Python 3.11+ with a virtual environment (conda or venv)
- `pdflatex` for PDF export — install [MacTeX](https://www.tug.org/mactex/)

### Install

```bash
# 1. Create and activate a virtual environment (conda example)
conda env create -f environment.yml
conda activate scripture_journal

# 2. Install Python dependencies
pip install PyQt6 PyQt6-WebEngine jinja2 requests beautifulsoup4 anthropic pyspellchecker
```

Or with a standard venv:

```bash
python3 -m venv venv
source venv/bin/activate
pip install PyQt6 PyQt6-WebEngine jinja2 requests beautifulsoup4 anthropic pyspellchecker
```

### Run

```bash
python app.py
```

On first launch the app creates `db/journal.db` and imports all scripture TSV files automatically (one-time, ~30 seconds).

---

## Configuration

User preferences are stored in `config.ini` (created automatically, gitignored):

```ini
[app]
theme = Catppuccin Mocha
```

Change the theme via **View → Theme** in the menu bar and restart the app.

---

## AI Search

AI Search uses the [Anthropic API](https://www.anthropic.com/). Set your API key before launching:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python app.py
```

Or enter it when prompted on first use — it will be saved to preferences automatically.

When you run an AI search, the app first searches your personal notes and media for relevant content and passes it to Claude as context, so Claude can reference your own study insights in its answer.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+F` | Standard search |
| `Cmd+T` | TODO list |
| `Cmd+D` | Webster's 1828 dictionary |
| `Cmd+E` | Export to PDF |
| `Cmd+I` | Import notes from CSV |
| `Ctrl+1/2/3` | Switch detail tab (Commentary / Cross-links / Media) |
| `Esc` | Close floating panels |

---

## TODO Tracker

Tag any line in a note with `TODO:` to add it to your study to-do list:

```
This verse parallels Alma 32. TODO: look up cross-references and compare the metaphors.
```

Open **View → TODO List** (or `Cmd+T`) to see all open items grouped by book and chapter. Double-click any item to navigate directly to that verse. The list refreshes automatically when notes are saved.

---

## Project Structure

```
scripture_journal/
├── app.py                       # Entry point — init DB, launch window
├── version.py                   # __version__ constant
├── config.py                    # config.ini read/write
├── config.ini                   # User preferences (gitignored)
├── environment.yml              # Conda environment spec
├── backend/
│   ├── database.py              # SQLite schema init and connection helpers
│   ├── db_api.py                # All DB read/write functions
│   └── services/
│       ├── tsv_importer.py      # One-time TSV → SQLite scripture import
│       ├── verse_reconstructor.py
│       ├── og_fetcher.py        # Open Graph metadata fetch for link previews
│       ├── latex_generator.py   # Jinja2 LaTeX template rendering
│       └── notes_importer.py    # CSV import from church study app
├── ui/
│   ├── themes.py                # Colour palettes
│   ├── main_window.py           # Top-level window, menus, splitter layout
│   ├── sidebar.py               # Book/chapter navigation tree
│   ├── reading_pane.py          # Verse display, inline search, edition controls
│   ├── verse_widget.py          # Individual verse row with word highlighting
│   ├── commentary_widget.py     # Notes CRUD panel
│   ├── crosslink_widget.py      # Cross-link CRUD panel
│   ├── media_widget.py          # Image and link preview panel
│   ├── export_widget.py         # LaTeX/PDF export dialog
│   ├── search_widget.py         # Standard and AI search dialog
│   ├── spell_checker.py         # Spell-check highlighter (pyspellchecker)
│   ├── todo_widget.py           # TODO tracker tree dialog
│   ├── dictionary_widget.py     # Webster's 1828 dictionary lookup
│   └── import_dialog.py         # CSV import progress dialog
├── data/
│   └── book-of-mormon/          # 15 word-level TSV files (git subtree)
├── db/
│   └── journal.db               # SQLite database — personal data (gitignored)
├── templates/
│   └── scripture_export.tex.j2  # Jinja2 LaTeX export template
└── output/                      # Generated .tex and .pdf files (gitignored)
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `verses` | Reconstructed verse text, one row per verse per edition |
| `verse_tokens` | Raw word-level tokens used for edition diff computation |
| `commentary` | Personal notes (book, chapter, verse, body, timestamps) |
| `cross_links` | Verse-to-verse links with optional note |
| `media` | Images (BLOB) and link previews (OG metadata + thumbnail BLOB) |
| `word_highlights` | Character-range highlights, edition-aware |
| `dictionary_cache` | Cached Webster's 1828 HTML entries |
| `import_log` | Tracks which TSV files have been imported (prevents re-import) |
| `preferences` | Key-value store (last position, edition, API key, etc.) |

> `db/journal.db` is gitignored. If it is absent when the app launches, a clean database is created automatically and the scripture text is re-imported from the TSV files.

---

## Version History

| Version | Changes |
|---------|---------|
| 1.0.0 | Initial release — all core features |
