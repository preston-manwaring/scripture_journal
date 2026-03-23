"""
Local dictionary lookup from db/dict.db (populated by dict_importer).

Supported sources: "1828", "1844", "1913"
"""
from __future__ import annotations

import re
import sqlite3

from backend.services.dict_importer import DICT_DB

# Shared dark-theme colours injected into every HTML response
_BODY_STYLE = (
    "font-family: Georgia, serif;"
    " font-size: 13px;"
    " color: #cdd6f4;"
    " background: #1e1e2e;"
    " margin: 8px;"
    " line-height: 1.6;"
)


def lookup(word: str, source: str = "1828") -> dict | None:
    """
    Return ``{"word": word, "html": html_str}`` or ``None`` if not found.

    Parameters
    ----------
    word   : the word to look up (case-insensitive)
    source : "1828", "1844", or "1913"
    """
    word_key = word.strip().lower()
    if not word_key or not DICT_DB.exists():
        return None

    try:
        conn = sqlite3.connect(f"file:{DICT_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            if source == "1828":
                return _lookup_1828(conn, word_key)
            elif source == "1844":
                return _lookup_1844(conn, word_key)
            elif source == "1913":
                return _lookup_1913(conn, word_key)
            return None
        finally:
            conn.close()
    except Exception:
        return None


# ── Per-source lookup ─────────────────────────────────────────────────────────

def _lookup_1828(conn: sqlite3.Connection, word_key: str) -> dict | None:
    rows = conn.execute(
        "SELECT word, html FROM w1828 WHERE word = ? LIMIT 1", (word_key,)
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    html = _wrap(row["html"])
    return {"word": row["word"], "html": html, "source": "1828"}


def _lookup_1844(conn: sqlite3.Connection, word_key: str) -> dict | None:
    rows = conn.execute(
        "SELECT word, definition FROM w1844 WHERE word = ? ORDER BY rowid", (word_key,)
    ).fetchall()
    if not rows:
        return None
    # There may be multiple pos entries for the same word; combine them
    parts = [r["definition"] for r in rows]
    inner = "<hr/>".join(parts)
    html = _wrap(inner)
    return {"word": rows[0]["word"], "html": html, "source": "1844"}


def _lookup_1913(conn: sqlite3.Connection, word_key: str) -> dict | None:
    rows = conn.execute(
        "SELECT word, pos, definition FROM w1913 WHERE word = ? ORDER BY rowid",
        (word_key,),
    ).fetchall()
    if not rows:
        return None

    parts: list[str] = []
    for r in rows:
        pos = r["pos"] or ""
        defn = r["definition"] or ""
        if pos:
            parts.append(f"<p><i>{pos}</i></p>{defn}")
        else:
            parts.append(defn)

    inner = "<hr/>".join(parts)
    html = _wrap(inner)
    return {"word": rows[0]["word"], "html": html, "source": "1913"}


# ── HTML wrapper ──────────────────────────────────────────────────────────────

def _wrap(inner: str) -> str:
    return (
        f"<html><body style='{_BODY_STYLE}'>"
        f"{inner}"
        f"</body></html>"
    )
