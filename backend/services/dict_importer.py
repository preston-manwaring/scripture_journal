"""
Import Webster's dictionary SQL dumps into a local SQLite database (db/dict.db).

Supported sources
-----------------
  1828 — Webster's American Dictionary (1st ed.)
  1844 — Webster's American Dictionary (expanded ed.)
  1913 — Webster's Revised Unabridged Dictionary

SQL source files: dict/v2015/SQL/02-database-insert/
Output database:  db/dict.db
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

_REPO_ROOT = Path(__file__).parents[2]
_DICT_SQL_DIR = _REPO_ROOT / "dict" / "v2015" / "SQL" / "02-database-insert"
DICT_DB = _REPO_ROOT / "db" / "dict.db"

_SQL_1828       = _DICT_SQL_DIR / "dictionary_webster1828.sql"
_SQL_1844       = _DICT_SQL_DIR / "dictionary_webster1844.sql"
_SQL_1913_WORDS = _DICT_SQL_DIR / "dictionary_webster1913_words.sql"
_SQL_1913_DEFS  = _DICT_SQL_DIR / "dictionary_webster1913_definitions.sql"


# ── Public API ────────────────────────────────────────────────────────────────

def needs_import() -> bool:
    """Return True if dict.db is absent or is missing one or more dictionaries."""
    if not DICT_DB.exists():
        return True
    try:
        conn = sqlite3.connect(str(DICT_DB))
        try:
            row = conn.execute("SELECT COUNT(*) FROM dict_import_log").fetchone()
            return row[0] < 3
        except Exception:
            return True
        finally:
            conn.close()
    except Exception:
        return True


def import_all(progress_cb: Callable[[str], None] | None = None) -> None:
    """Import all three dictionaries.  Skips any already imported (idempotent)."""

    def _p(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)
        else:
            print(msg)

    DICT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DICT_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        _init_dict_db(conn)
        already = {
            r[0] for r in conn.execute("SELECT source FROM dict_import_log").fetchall()
        }

        if "1828" not in already:
            _p("Importing Webster's 1828 dictionary…")
            n = _import_1828(conn)
            _record(conn, "1828", n)
            _p(f"  → {n:,} entries")

        if "1844" not in already:
            _p("Importing Webster's 1844 dictionary…")
            n = _import_1844(conn)
            _record(conn, "1844", n)
            _p(f"  → {n:,} entries")

        if "1913" not in already:
            _p("Importing Webster's 1913 dictionary…")
            n = _import_1913(conn)
            _record(conn, "1913", n)
            _p(f"  → {n:,} entries")

    finally:
        conn.close()


# ── DB schema ─────────────────────────────────────────────────────────────────

def _init_dict_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS w1828 (
            word TEXT NOT NULL,
            html TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_w1828 ON w1828(word);

        CREATE TABLE IF NOT EXISTS w1844 (
            word       TEXT NOT NULL,
            definition TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_w1844 ON w1844(word);

        CREATE TABLE IF NOT EXISTS w1913 (
            word       TEXT NOT NULL,
            pos        TEXT,
            definition TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_w1913 ON w1913(word);

        CREATE TABLE IF NOT EXISTS dict_import_log (
            source      TEXT PRIMARY KEY,
            imported_at TEXT NOT NULL,
            row_count   INTEGER NOT NULL
        );
    """)
    conn.commit()


def _record(conn: sqlite3.Connection, source: str, count: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO dict_import_log (source, imported_at, row_count)"
        " VALUES (?, ?, ?)",
        (source, now, count),
    )
    conn.commit()


# ── Per-dictionary importers ──────────────────────────────────────────────────

def _import_1828(conn: sqlite3.Connection) -> int:
    text = _SQL_1828.read_bytes().decode("latin-1")
    batch: list[tuple[str, str]] = []
    for fields in _parse_rows(text):
        # (id, word, length, string, _word, heading, content)
        if len(fields) < 7:
            continue
        word_key = str(fields[4]).strip().lower()
        html = str(fields[6])
        if word_key and html:
            batch.append((word_key, html))
    conn.executemany("INSERT INTO w1828 (word, html) VALUES (?, ?)", batch)
    conn.commit()
    return len(batch)


_BYUID_RE = re.compile(r'\{byuid\}')


def _import_1844(conn: sqlite3.Connection) -> int:
    text = _SQL_1844.read_bytes().decode("utf-8", errors="replace")
    batch: list[tuple[str, str]] = []
    for fields in _parse_rows(text):
        # (id, byuid, _word, pronounce, letter, page, order, definition)
        if len(fields) < 8:
            continue
        byuid = str(fields[1])
        word_key = str(fields[2]).strip().lower()
        definition = str(fields[7])
        definition = _BYUID_RE.sub(byuid, definition)
        if word_key and definition:
            batch.append((word_key, definition))
    conn.executemany("INSERT INTO w1844 (word, definition) VALUES (?, ?)", batch)
    conn.commit()
    return len(batch)


_XCODE_RE = re.compile(r'\[xCode:x([0-9A-Fa-f]+)\]')
_UCODE_RE = re.compile(r'\[uCode:[^\]]+\]')


def _decode_codes(s: str) -> str:
    """Expand [xCode:x????] → unicode char; replace [uCode:...] with middle-dot."""
    def _sub(m: re.Match) -> str:
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return ""

    s = _XCODE_RE.sub(_sub, s)
    s = _UCODE_RE.sub("\u00b7", s)
    return s


def _import_1913(conn: sqlite3.Connection) -> int:
    # Pass 1: words
    words_text = _SQL_1913_WORDS.read_bytes().decode("latin-1")
    words: dict[int, tuple[str, str]] = {}   # word_id → (word_key, pos)
    for fields in _parse_rows(words_text):
        # (word_id, word, _word, _word_, pos, phonetic, pronounce, root, page, alt)
        if len(fields) < 5:
            continue
        wid = int(fields[0])
        word_key = str(fields[3]).strip().lower()   # _word_ column
        pos = _decode_codes(str(fields[4])) if fields[4] is not None else ""
        words[wid] = (word_key, pos)

    # Pass 2: definitions
    defs_text = _SQL_1913_DEFS.read_bytes().decode("latin-1")
    defs: dict[int, list[tuple[int, str]]] = {}   # word_id → [(rank, html), ...]
    for fields in _parse_rows(defs_text):
        # (definition_id, word_id, rank, definition, extra)
        if len(fields) < 4:
            continue
        wid = int(fields[1])
        rank = int(fields[2]) if fields[2] is not None else 0
        defn = _decode_codes(str(fields[3])) if fields[3] is not None else ""
        if defn:
            defs.setdefault(wid, []).append((rank, defn))

    # Combine
    batch: list[tuple[str, str | None, str]] = []
    for wid, (word_key, pos) in words.items():
        if not word_key:
            continue
        word_defs = sorted(defs.get(wid, []), key=lambda t: t[0])
        combined = "".join(d for _, d in word_defs)
        batch.append((word_key, pos or None, combined))
    conn.executemany("INSERT INTO w1913 (word, pos, definition) VALUES (?, ?, ?)", batch)
    conn.commit()
    return len(batch)


# ── MySQL INSERT row parser ───────────────────────────────────────────────────

def _parse_rows(sql_text: str) -> Iterator[tuple]:
    """
    Parse all row tuples from every MySQL ``INSERT … VALUES …`` block in the text.

    Handles:
    - Multiple INSERT statements (MySQL dumps split large tables into batches)
    - Quoted string values with backslash escapes (\\', \\\\, \\n, \\r, \\t)
    - Integer and NULL values
    - Rows that span multiple lines (literal newlines inside quoted strings)
    """
    # Find the start position of each VALUES block
    value_starts = [
        m.end() for m in re.finditer(r'\bVALUES\b\s*\n', sql_text, re.IGNORECASE)
    ]
    if not value_starts:
        value_starts = [
            m.end() for m in re.finditer(r'\bVALUES\b\s*\r\n', sql_text, re.IGNORECASE)
        ]
    if not value_starts:
        return

    n = len(sql_text)
    for start in value_starts:
        yield from _parse_values_block(sql_text, start, n)


def _parse_values_block(sql_text: str, start: int, n: int) -> Iterator[tuple]:
    """Parse one VALUES (...),(...) block starting at *start*."""
    pos = start

    while pos < n:
        # Skip inter-row whitespace and commas
        while pos < n and sql_text[pos] in ' \t\r\n,':
            pos += 1
        if pos >= n or sql_text[pos] != '(':
            break

        pos += 1  # consume '('
        fields: list = []

        while pos < n:
            # Skip intra-field whitespace
            while pos < n and sql_text[pos] in ' \t\r\n':
                pos += 1
            if pos >= n:
                break

            ch = sql_text[pos]

            if ch == ')':
                pos += 1
                break

            if ch == ',':
                pos += 1
                continue

            if ch == "'":
                # Quoted string
                pos += 1
                chars: list[str] = []
                while pos < n:
                    c = sql_text[pos]
                    if c == '\\':
                        pos += 1
                        if pos < n:
                            nc = sql_text[pos]
                            pos += 1
                            if   nc == "'":  chars.append("'")
                            elif nc == '\\': chars.append('\\')
                            elif nc == 'n':  chars.append('\n')
                            elif nc == 'r':  chars.append('\r')
                            elif nc == 't':  chars.append('\t')
                            else:            chars.append(nc)
                    elif c == "'":
                        pos += 1
                        break
                    else:
                        chars.append(c)
                        pos += 1
                fields.append(''.join(chars))

            elif sql_text[pos:pos+4] == 'NULL':
                fields.append(None)
                pos += 4

            else:
                # Integer (optionally negative)
                end = pos
                if end < n and sql_text[end] == '-':
                    end += 1
                while end < n and sql_text[end].isdigit():
                    end += 1
                if end > pos:
                    try:
                        fields.append(int(sql_text[pos:end]))
                    except ValueError:
                        fields.append(sql_text[pos:end])
                    pos = end
                else:
                    pos += 1  # skip unexpected character

        yield tuple(fields)
