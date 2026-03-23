import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "journal.db")


def get_connection() -> sqlite3.Connection:
    """Open journal.db for reading and writing."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_readonly_connection() -> sqlite3.Connection:
    """Open journal.db in read-only mode. Any write attempt raises OperationalError."""
    path = os.path.abspath(DB_PATH)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS verses (
                id      INTEGER PRIMARY KEY,
                book    TEXT NOT NULL,
                chapter INTEGER NOT NULL,
                verse   INTEGER NOT NULL,
                edition TEXT NOT NULL,
                text    TEXT NOT NULL,
                UNIQUE(book, chapter, verse, edition)
            );

            CREATE TABLE IF NOT EXISTS verse_tokens (
                id       INTEGER PRIMARY KEY,
                book     TEXT NOT NULL,
                chapter  INTEGER NOT NULL,
                verse    INTEGER NOT NULL,
                wid      TEXT NOT NULL,
                edition  TEXT NOT NULL,
                token    TEXT,
                is_space INTEGER DEFAULT 0,
                UNIQUE(book, chapter, verse, wid, edition)
            );

            CREATE TABLE IF NOT EXISTS commentary (
                id         INTEGER PRIMARY KEY,
                book       TEXT NOT NULL,
                chapter    INTEGER NOT NULL,
                verse      INTEGER NOT NULL,
                edition    TEXT,
                body       TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_commentary_verse
                ON commentary(book, chapter, verse);

            CREATE TABLE IF NOT EXISTS cross_links (
                id             INTEGER PRIMARY KEY,
                source_book    TEXT NOT NULL,
                source_chapter INTEGER NOT NULL,
                source_verse   INTEGER NOT NULL,
                target_book    TEXT NOT NULL,
                target_chapter INTEGER NOT NULL,
                target_verse   INTEGER NOT NULL,
                note           TEXT,
                created_at     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_crosslinks_source
                ON cross_links(source_book, source_chapter, source_verse);

            CREATE TABLE IF NOT EXISTS media (
                id             INTEGER PRIMARY KEY,
                book           TEXT NOT NULL,
                chapter        INTEGER NOT NULL,
                verse          INTEGER NOT NULL,
                type           TEXT NOT NULL,
                filename       TEXT,
                mime_type      TEXT,
                data           BLOB,
                url            TEXT,
                og_title       TEXT,
                og_description TEXT,
                og_image       BLOB,
                og_image_mime  TEXT,
                caption        TEXT,
                created_at     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_media_verse
                ON media(book, chapter, verse);

            CREATE TABLE IF NOT EXISTS import_log (
                id          INTEGER PRIMARY KEY,
                filename    TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                row_count   INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS highlights (
                id         INTEGER PRIMARY KEY,
                book       TEXT NOT NULL,
                chapter    INTEGER NOT NULL,
                verse      INTEGER NOT NULL,
                color      TEXT NOT NULL DEFAULT '#f9e2af',
                created_at TEXT NOT NULL,
                UNIQUE(book, chapter, verse)
            );
            CREATE INDEX IF NOT EXISTS idx_highlights_verse
                ON highlights(book, chapter, verse);

            CREATE TABLE IF NOT EXISTS dictionary_cache (
                word       TEXT PRIMARY KEY,
                html       TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS word_highlights (
                id         INTEGER PRIMARY KEY,
                book       TEXT NOT NULL,
                chapter    INTEGER NOT NULL,
                verse      INTEGER NOT NULL,
                edition    TEXT NOT NULL,
                start_char INTEGER NOT NULL,
                end_char   INTEGER NOT NULL,
                color      TEXT NOT NULL DEFAULT '#f9e2af',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_word_highlights
                ON word_highlights(book, chapter, verse, edition);
        """)
    conn.close()
