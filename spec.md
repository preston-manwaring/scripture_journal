# Scripture Journal — Specification

## Overview
A local desktop study journal for the Book of Mormon. All data is stored locally in SQLite. The app is a single Python process (no separate server) with a native PyQt6 desktop UI.

## Data Source
- 15 TSV files in `data/book-of-mormon/` (git subtree)
- 8 editions: 1830, 1837, 1840, 1841, 1879, 1920, 1981, 2013
- Word-level tokenization; token `⌴` (U+2334) = space, `∅` (U+2205) = absent in edition
- 47,248 reconstructed verse rows across all editions

## Features

### F1 — Navigation
- Sidebar: lazy-loading book → chapter → verse tree (`QTreeWidget`)
- Clicking a chapter loads the full chapter in the reading pane
- Clicking a verse selects and scrolls to it

### F2 — Edition Display
- Dropdown with all 8 editions; switching reloads verse text
- Default: 2013 edition

### F3 — Full-Chapter View
- All verses for the selected chapter rendered as a scrollable list of `VerseWidget` rows

### F4 — Edition Diff (Compare)
- "Compare…" toggle button reveals a second edition picker
- Token-level diff shown as a colored inline overlay below the selected verse
  - Removed tokens: red background
  - Added tokens: green background
  - Unchanged: normal text color

### F5 — Highlights
- Click the verse number (left gutter) to toggle a default yellow highlight
- Right-click anywhere on a verse to pick from 6 preset colors: Yellow, Green, Blue, Pink, Peach, Lavender
- Highlights stored in `highlights` table; persist across restarts
- Highlighted verses show a colored left border and tinted background

### F6 — Commentary
- Per-verse, edition-agnostic notes
- Add, edit, delete notes in the Commentary tab
- Timestamps (created/updated) stored and displayed
- Badge on verse row shows note count

### F7 — Cross-links
- Link any verse to another with an optional note
- Shows outbound (this verse → target) and inbound (other verse → this) lists
- Double-click a link to navigate to the linked verse
- Badge on verse row shows link count

### F8 — Media Attachments
- **Images**: attach local files; stored as BLOBs in SQLite; displayed as thumbnails
- **Link previews**: paste a URL; app fetches Open Graph metadata (title, description, thumbnail image) and stores all as BLOB/text in SQLite; displayed as preview cards with a "click to open" link
- Optional caption field on each attachment
- Badge on verse row shows attachment count

### F9 — LaTeX Export
- Select book, chapter range, edition, and options (include commentary, include media)
- Generates a `.tex` file using a Jinja2 template (`templates/scripture_export.tex.j2`)
- Compiles to PDF with `pdflatex` (run as a background `QThread`)
- Compiled PDF displayed in an embedded `QWebEngineView`
- "Open in Finder" button reveals the file in macOS Finder

### F10 — Search
- **Standard**: LIKE search across verse text, commentary notes, and media metadata
  - Results grouped by source with color-coded badges (Verse / Note / Media)
  - Updates as you type (300 ms debounce)
- **AI Search**: natural-language question answered by `claude-opus-4-6` (Anthropic API)
  - Streaming response with adaptive thinking
  - Verse citations parsed from the response; matched against DB; shown as clickable cards
  - API key read from `ANTHROPIC_API_KEY` env var or stored in preferences

### F11 — CSV Import
- Import highlights and notes from the Church of Jesus Christ study app export
- Parses Church website URLs to extract book, chapter, and verse
- Rows with text → `commentary` table; bare highlights → `highlights` table (yellow default)
- Handles verse ranges (e.g., `?id=p16-p17` → verses 16 and 17)
- Duplicate detection to prevent re-importing the same notes

### F12 — Themes
- Four built-in color themes: Catppuccin Mocha (dark), Catppuccin Latte (light), Nord, Solarized Dark
- Theme selection stored in `config.ini`
- Apply via **View → Theme**; takes effect on next launch

### F13 — Preferences
- Last-viewed book, chapter, and verse restored on relaunch
- Stored in the SQLite `preferences` table

## Non-Functional Requirements
- Pure Python desktop app (PyQt6)
- Single process — no separate server or HTTP layer
- All user data in `db/journal.db` (SQLite)
- Config (theme, etc.) in `config.ini` at project root
- Works fully offline (AI Search requires internet)
- macOS primary target (Darwin 25+)
- Version number exposed in title bar and About dialog
