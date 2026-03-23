"""
Import all Book of Mormon TSV files into SQLite.

Run automatically at FastAPI startup if import_log is empty.
Can also be run as a standalone script:
    python -m backend.services.tsv_importer
"""

import csv
import os
import sys
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from backend.database import get_connection
from backend.services.verse_reconstructor import (
    ABSENT_CHAR,
    SPACE_CHAR,  # noqa: F401 (imported for is_space detection below)
    reconstruct,
    wid_sort_key,  # noqa: F401
)

csv.field_size_limit(sys.maxsize)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "book-of-mormon")

EDITIONS = ["1830", "1837", "1840", "1841", "1879", "1920", "1981", "2013"]

# Canonical book order
BOOK_ORDER = [
    "1 Nephi", "2 Nephi", "Jacob", "Enos", "Jarom", "Omni",
    "Words of Mormon", "Mosiah", "Alma", "Helaman",
    "3 Nephi", "4 Nephi", "Mormon", "Ether", "Moroni",
]

CITATION_RE = re.compile(r"^(.+?)\s+(\d+):(\d+)$")


def parse_citation(citation: str) -> tuple[str, int, int]:
    m = CITATION_RE.match(citation.strip())
    if not m:
        raise ValueError(f"Cannot parse citation: {citation!r}")
    return m.group(1), int(m.group(2)), int(m.group(3))


def import_file(conn: sqlite3.Connection, tsv_path: str) -> int:
    filename = os.path.basename(tsv_path)

    # Group rows by citation → { citation: [(wid, [token_per_edition, ...]), ...] }
    # Use a dict of lists: citation → list of (wid, tokens_dict)
    verse_rows: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)

    with open(tsv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        row_count = 0
        for row in reader:
            citation = row["Citation"]
            wid = row["wID"]
            tokens = {ed: row[ed] for ed in EDITIONS}
            verse_rows[citation].append((wid, tokens))
            row_count += 1

    verses_batch = []
    tokens_batch = []

    for citation, rows in verse_rows.items():
        book, chapter, verse = parse_citation(citation)

        # Build per-edition token lists for reconstruction
        edition_token_lists: dict[str, list[tuple[str, str]]] = {ed: [] for ed in EDITIONS}
        for wid, tokens in rows:
            for ed in EDITIONS:
                edition_token_lists[ed].append((wid, tokens[ed]))

        for ed in EDITIONS:
            text = reconstruct(edition_token_lists[ed])
            verses_batch.append((book, chapter, verse, ed, text))

        # Build token rows for verse_tokens table
        for wid, tokens in rows:
            for ed in EDITIONS:
                token_val = tokens[ed]
                is_absent = token_val == ABSENT_CHAR
                is_space = token_val == SPACE_CHAR
                # Store None for absent tokens
                stored_token = None if is_absent else token_val
                tokens_batch.append((
                    book, chapter, verse, wid, ed,
                    stored_token, 1 if is_space else 0
                ))

    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO verses (book, chapter, verse, edition, text) "
            "VALUES (?, ?, ?, ?, ?)",
            verses_batch,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO verse_tokens "
            "(book, chapter, verse, wid, edition, token, is_space) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            tokens_batch,
        )
        conn.execute(
            "INSERT INTO import_log (filename, imported_at, row_count) VALUES (?, ?, ?)",
            (filename, datetime.now(timezone.utc).isoformat(), row_count),
        )

    return row_count


def needs_import(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM import_log").fetchone()
    return row[0] == 0


def import_all(conn: sqlite3.Connection | None = None):
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        tsv_files = sorted(
            [f for f in os.listdir(DATA_DIR) if f.endswith(".tsv")],
            key=lambda f: BOOK_ORDER.index(f[:-4]) if f[:-4] in BOOK_ORDER else 99,
        )
        total = 0
        for filename in tsv_files:
            path = os.path.join(DATA_DIR, filename)
            print(f"  Importing {filename}...", flush=True)
            count = import_file(conn, path)
            total += count
            print(f"    → {count:,} rows", flush=True)
        print(f"Import complete. Total rows: {total:,}", flush=True)
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    from backend.database import init_db
    init_db()
    conn = get_connection()
    import_all(conn)
    conn.close()
