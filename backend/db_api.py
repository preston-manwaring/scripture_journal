"""
Pure-Python DB API for the PyQt6 UI.
No FastAPI/pydantic dependency — just sqlite3 via backend.database.
"""
from __future__ import annotations
import re as _re
from datetime import datetime, timezone
from backend.database import get_connection, get_readonly_connection

_TAG_RE = _re.compile(r'#([A-Za-z0-9_-]+)')
from backend.services.verse_reconstructor import ABSENT_CHAR, wid_sort_key
import difflib

EDITIONS = ["1830", "1837", "1840", "1841", "1879", "1920", "1981", "2013"]

BOOK_ORDER = [
    "1 Nephi", "2 Nephi", "Jacob", "Enos", "Jarom", "Omni",
    "Words of Mormon", "Mosiah", "Alma", "Helaman",
    "3 Nephi", "4 Nephi", "Mormon", "Ether", "Moroni",
]


# ── Scripture ─────────────────────────────────────────────────────────────────

def get_books() -> list[str]:
    conn = get_readonly_connection()
    try:
        rows = conn.execute("SELECT DISTINCT book FROM verses").fetchall()
        books = [r["book"] for r in rows]
        books.sort(key=lambda b: BOOK_ORDER.index(b) if b in BOOK_ORDER else 99)
        return books
    finally:
        conn.close()


def get_chapters(book: str) -> list[int]:
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT chapter FROM verses WHERE book=? ORDER BY chapter", (book,)
        ).fetchall()
        return [r["chapter"] for r in rows]
    finally:
        conn.close()


def get_chapter_verses(book: str, chapter: int, edition: str) -> list[dict]:
    """Return list of {verse, text} dicts for an entire chapter."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT verse, text FROM verses
               WHERE book=? AND chapter=? AND edition=?
               ORDER BY verse""",
            (book, chapter, edition),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_verse_text(book: str, chapter: int, verse: int, edition: str) -> str | None:
    conn = get_readonly_connection()
    try:
        row = conn.execute(
            "SELECT text FROM verses WHERE book=? AND chapter=? AND verse=? AND edition=?",
            (book, chapter, verse, edition),
        ).fetchone()
        return row["text"] if row else None
    finally:
        conn.close()


def get_diff(
    book: str, chapter: int, verse: int, edition_a: str, edition_b: str
) -> dict:
    """Returns {edition_a, edition_b, diff_tokens: [{token, status}]}."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT wid, edition, token FROM verse_tokens
               WHERE book=? AND chapter=? AND verse=? AND edition IN (?, ?)""",
            (book, chapter, verse, edition_a, edition_b),
        ).fetchall()

        def tokens_for(ed: str) -> list[str]:
            ed_rows = [(r["wid"], r["token"]) for r in rows if r["edition"] == ed]
            ed_rows.sort(key=lambda t: wid_sort_key(t[0]))
            return [tok for _, tok in ed_rows if tok is not None and tok != ABSENT_CHAR]

        ta = tokens_for(edition_a)
        tb = tokens_for(edition_b)

        text_a = get_verse_text(book, chapter, verse, edition_a) or ""
        text_b = get_verse_text(book, chapter, verse, edition_b) or ""

        matcher = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
        diff_tokens = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for tok in ta[i1:i2]:
                    diff_tokens.append({"token": tok, "status": "same"})
            elif tag == "replace":
                for tok in ta[i1:i2]:
                    diff_tokens.append({"token": tok, "status": "removed"})
                for tok in tb[j1:j2]:
                    diff_tokens.append({"token": tok, "status": "added"})
            elif tag == "delete":
                for tok in ta[i1:i2]:
                    diff_tokens.append({"token": tok, "status": "removed"})
            elif tag == "insert":
                for tok in tb[j1:j2]:
                    diff_tokens.append({"token": tok, "status": "added"})

        return {
            "edition_a": edition_a, "text_a": text_a,
            "edition_b": edition_b, "text_b": text_b,
            "diff_tokens": diff_tokens,
        }
    finally:
        conn.close()


# ── Commentary ─────────────────────────────────────────────────────────────────

def get_commentary(book: str, chapter: int, verse: int) -> list[dict]:
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT id, edition, body, created_at, updated_at
               FROM commentary WHERE book=? AND chapter=? AND verse=?
               ORDER BY created_at""",
            (book, chapter, verse),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_commentary(
    book: str, chapter: int, verse: int, body: str, edition: str | None = None
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO commentary (book, chapter, verse, edition, body, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (book, chapter, verse, edition, body, now, now),
            )
            note_id = cur.lastrowid
            _sync_note_tags(conn, note_id, body)
        return note_id
    finally:
        conn.close()


def update_commentary(commentary_id: int, body: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE commentary SET body=?, updated_at=? WHERE id=?",
                (body, now, commentary_id),
            )
            _sync_note_tags(conn, commentary_id, body)
    finally:
        conn.close()


def delete_commentary(commentary_id: int) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM note_tags WHERE note_id=?", (commentary_id,))
            conn.execute("DELETE FROM commentary WHERE id=?", (commentary_id,))
            _prune_orphan_tags(conn)
    finally:
        conn.close()


# ── Tag helpers ────────────────────────────────────────────────────────────────

def _sync_note_tags(conn, note_id: int, body: str) -> None:
    """Rebuild tag index for a single note. Must be called inside an open transaction."""
    names = {m.group(1).lower() for m in _TAG_RE.finditer(body)}
    conn.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
    for name in names:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        conn.execute(
            "INSERT OR IGNORE INTO note_tags (note_id, tag_id) "
            "SELECT ?, id FROM tags WHERE name=? COLLATE NOCASE",
            (note_id, name),
        )


def _prune_orphan_tags(conn) -> None:
    """Remove tags no longer referenced by any note."""
    conn.execute(
        "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM note_tags)"
    )


def get_all_tags() -> list[str]:
    """Return all tag names sorted case-insensitively."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM tags ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


def get_notes_for_tag(tag: str) -> list[dict]:
    """Return all notes that contain the given tag, ordered by book/chapter/verse."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT c.id, c.book, c.chapter, c.verse, c.body
               FROM commentary c
               JOIN note_tags nt ON nt.note_id = c.id
               JOIN tags t ON t.id = nt.tag_id
               WHERE t.name = ? COLLATE NOCASE
               ORDER BY c.book, c.chapter, c.verse""",
            (tag,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── TODO items ────────────────────────────────────────────────────────────────

def get_todos() -> list[dict]:
    """
    Return all TODO items extracted from commentary notes.

    Each dict has: book, chapter, verse, note_id, todo_text (the full TODO line),
    line_index (0-based line number within the note body).
    Results are sorted in canonical book order, then chapter, then verse.
    """
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT id, book, chapter, verse, body
               FROM commentary WHERE body LIKE '%TODO:%'
               ORDER BY book, chapter, verse""",
        ).fetchall()
    finally:
        conn.close()

    book_rank = {b: i for i, b in enumerate(BOOK_ORDER)}
    items = []
    for row in rows:
        for line_idx, line in enumerate(row["body"].split("\n")):
            if "TODO:" in line:
                items.append({
                    "book": row["book"],
                    "chapter": row["chapter"],
                    "verse": row["verse"],
                    "note_id": row["id"],
                    "todo_text": line.strip(),
                    "line_index": line_idx,
                })
    items.sort(key=lambda x: (book_rank.get(x["book"], 99), x["chapter"], x["verse"]))
    return items


# ── Cross-links ────────────────────────────────────────────────────────────────

def get_crosslinks(book: str, chapter: int, verse: int) -> dict:
    conn = get_readonly_connection()
    try:
        outbound = conn.execute(
            """SELECT id, source_verse, source_verse_end,
                      target_book, target_chapter, target_verse, target_verse_end,
                      note, created_at, group_id
               FROM cross_links
               WHERE source_book=? AND source_chapter=?
                 AND ? BETWEEN source_verse AND COALESCE(source_verse_end, source_verse)
               ORDER BY created_at""",
            (book, chapter, verse),
        ).fetchall()
        inbound = conn.execute(
            """SELECT id, source_book, source_chapter, source_verse, source_verse_end,
                      target_verse, target_verse_end, note, created_at, group_id
               FROM cross_links
               WHERE target_book=? AND target_chapter=?
                 AND ? BETWEEN target_verse AND COALESCE(target_verse_end, target_verse)
               ORDER BY created_at""",
            (book, chapter, verse),
        ).fetchall()
        return {
            "outbound": [dict(r) for r in outbound],
            "inbound": [dict(r) for r in inbound],
        }
    finally:
        conn.close()


def get_chapter_range_bars(book: str, chapter: int) -> list[dict]:
    """
    Return all multi-verse cross-link ranges touching this chapter (source or target side).
    Used to draw gutter bars in the reading pane.
    Deduplicates bidirectional pairs via group_id so each logical link yields one bar.
    """
    conn = get_readonly_connection()
    try:
        src = conn.execute(
            """SELECT source_verse AS verse_start, source_verse_end AS verse_end,
                      COALESCE(group_id, id) AS dedup_key
               FROM cross_links
               WHERE source_book=? AND source_chapter=?
                 AND source_verse_end IS NOT NULL AND source_verse_end > source_verse""",
            (book, chapter),
        ).fetchall()
        tgt = conn.execute(
            """SELECT target_verse AS verse_start, target_verse_end AS verse_end,
                      COALESCE(group_id, id) AS dedup_key
               FROM cross_links
               WHERE target_book=? AND target_chapter=?
                 AND target_verse_end IS NOT NULL AND target_verse_end > target_verse""",
            (book, chapter),
        ).fetchall()
    finally:
        conn.close()

    seen: set[int] = set()
    result: list[dict] = []
    for row in list(src) + list(tgt):
        if row["dedup_key"] not in seen:
            seen.add(row["dedup_key"])
            result.append({"verse_start": row["verse_start"], "verse_end": row["verse_end"]})
    return sorted(result, key=lambda r: (r["verse_start"], r["verse_end"]))


def get_verse_range_text(
    book: str, chapter: int, verse_start: int, verse_end: int | None, edition: str
) -> str:
    """Return concatenated verse text for a single verse or range."""
    end = verse_end if (verse_end and verse_end > verse_start) else verse_start
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT verse, text FROM verses
               WHERE book=? AND chapter=? AND edition=?
                 AND verse BETWEEN ? AND ?
               ORDER BY verse""",
            (book, chapter, edition, verse_start, end),
        ).fetchall()
    finally:
        conn.close()
    return "\n".join(f"{r['verse']}  {r['text']}" for r in rows)


def create_crosslink(
    source_book: str, source_chapter: int, source_verse: int,
    target_book: str, target_chapter: int, target_verse: int,
    note: str | None = None,
    target_verse_end: int | None = None,
    source_verse_end: int | None = None,
    bidirectional: bool = True,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    src_end = source_verse_end if (source_verse_end and source_verse_end > source_verse) else None
    tgt_end = target_verse_end if (target_verse_end and target_verse_end > target_verse) else None
    conn = get_connection()
    try:
        with conn:
            # Forward row (A → B)
            cur = conn.execute(
                """INSERT INTO cross_links
                   (source_book, source_chapter, source_verse, source_verse_end,
                    target_book, target_chapter, target_verse, target_verse_end,
                    note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_book, source_chapter, source_verse, src_end,
                 target_book, target_chapter, target_verse, tgt_end, note, now),
            )
            fwd_id = cur.lastrowid
            conn.execute("UPDATE cross_links SET group_id=? WHERE id=?", (fwd_id, fwd_id))

            if bidirectional:
                # Reverse row (B → A) — source/target swapped
                conn.execute(
                    """INSERT INTO cross_links
                       (source_book, source_chapter, source_verse, source_verse_end,
                        target_book, target_chapter, target_verse, target_verse_end,
                        note, created_at, group_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (target_book, target_chapter, target_verse, tgt_end,
                     source_book, source_chapter, source_verse, src_end,
                     note, now, fwd_id),
                )
        return fwd_id
    finally:
        conn.close()


def delete_crosslink(link_id: int) -> None:
    conn = get_connection()
    try:
        with conn:
            row = conn.execute(
                "SELECT group_id FROM cross_links WHERE id=?", (link_id,)
            ).fetchone()
            if row and row["group_id"] is not None:
                conn.execute("DELETE FROM cross_links WHERE group_id=?", (row["group_id"],))
            else:
                conn.execute("DELETE FROM cross_links WHERE id=?", (link_id,))
    finally:
        conn.close()


# ── Media ──────────────────────────────────────────────────────────────────────

def get_media(book: str, chapter: int, verse: int) -> list[dict]:
    """Metadata only — no BLOB bytes."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT id, type, filename, mime_type, url,
                      og_title, og_description, og_image_mime, caption, created_at
               FROM media WHERE book=? AND chapter=? AND verse=?
               ORDER BY created_at""",
            (book, chapter, verse),
        ).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            item["has_image"] = (
                r["type"] == "image" or r["og_image_mime"] is not None
            )
            items.append(item)
        return items
    finally:
        conn.close()


def attach_image(
    book: str, chapter: int, verse: int,
    file_path: str, caption: str | None = None,
) -> int:
    import mimetypes
    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        data = f.read()
    import os
    filename = os.path.basename(file_path)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO media
                   (book, chapter, verse, type, filename, mime_type, data, caption, created_at)
                   VALUES (?, ?, ?, 'image', ?, ?, ?, ?, ?)""",
                (book, chapter, verse, filename, mime_type, data, caption, now),
            )
        return cur.lastrowid
    finally:
        conn.close()


def attach_link(
    book: str, chapter: int, verse: int,
    url: str, og: dict, caption: str | None = None,
) -> int:
    """og must have keys: og_title, og_description, og_image, og_image_mime."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO media
                   (book, chapter, verse, type, url,
                    og_title, og_description, og_image, og_image_mime, caption, created_at)
                   VALUES (?, ?, ?, 'link', ?, ?, ?, ?, ?, ?, ?)""",
                (book, chapter, verse, url,
                 og.get("og_title"), og.get("og_description"),
                 og.get("og_image"), og.get("og_image_mime"),
                 caption, now),
            )
        return cur.lastrowid
    finally:
        conn.close()


def get_image_bytes(media_id: int) -> tuple[bytes | None, str | None]:
    """Returns (blob_bytes, mime_type) for an image or link thumbnail."""
    conn = get_readonly_connection()
    try:
        row = conn.execute(
            "SELECT type, data, mime_type, og_image, og_image_mime FROM media WHERE id=?",
            (media_id,),
        ).fetchone()
        if not row:
            return None, None
        if row["type"] == "image":
            blob = row["data"]
            mime = row["mime_type"]
        else:
            blob = row["og_image"]
            mime = row["og_image_mime"]
        return (bytes(blob) if blob else None), mime
    finally:
        conn.close()


def delete_media(media_id: int) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    finally:
        conn.close()


# ── Verse annotation counts (for badges) ──────────────────────────────────────

def get_verse_badge_counts(book: str, chapter: int) -> dict[int, dict]:
    """Returns {verse: {commentary, crosslinks, media}} for all verses in chapter."""
    conn = get_readonly_connection()
    try:
        c_rows = conn.execute(
            "SELECT verse, COUNT(*) as n FROM commentary WHERE book=? AND chapter=? GROUP BY verse",
            (book, chapter),
        ).fetchall()
        cl_rows = conn.execute(
            """SELECT source_verse as verse, COUNT(*) as n FROM cross_links
               WHERE source_book=? AND source_chapter=? GROUP BY source_verse""",
            (book, chapter),
        ).fetchall()
        m_rows = conn.execute(
            "SELECT verse, COUNT(*) as n FROM media WHERE book=? AND chapter=? GROUP BY verse",
            (book, chapter),
        ).fetchall()
    finally:
        conn.close()

    counts: dict[int, dict] = {}
    for r in c_rows:
        counts.setdefault(r["verse"], {})["commentary"] = r["n"]
    for r in cl_rows:
        counts.setdefault(r["verse"], {})["crosslinks"] = r["n"]
    for r in m_rows:
        counts.setdefault(r["verse"], {})["media"] = r["n"]
    return counts


# ── Word highlights (span-level) ─────────────────────────────────────────────

def get_word_highlights(book: str, chapter: int, verse: int, edition: str) -> list[dict]:
    """Return [{id, start_char, end_char, color}] sorted by start_char for the given edition."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT id, start_char, end_char, color
               FROM word_highlights
               WHERE book=? AND chapter=? AND verse=? AND edition=?
               ORDER BY start_char""",
            (book, chapter, verse, edition),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_chapter_word_highlights(book: str, chapter: int, edition: str) -> dict[int, list[dict]]:
    """Return {verse: [{id, start_char, end_char, color}]} for the whole chapter in the given edition."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT verse, id, start_char, end_char, color
               FROM word_highlights
               WHERE book=? AND chapter=? AND edition=?
               ORDER BY verse, start_char""",
            (book, chapter, edition),
        ).fetchall()
    finally:
        conn.close()
    result: dict[int, list[dict]] = {}
    for r in rows:
        result.setdefault(r["verse"], []).append(
            {"id": r["id"], "start_char": r["start_char"],
             "end_char": r["end_char"], "color": r["color"]}
        )
    return result


def add_word_highlight(
    book: str, chapter: int, verse: int,
    start_char: int, end_char: int, color: str,
    edition: str = "",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO word_highlights
                   (book, chapter, verse, edition, start_char, end_char, color, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (book, chapter, verse, edition, start_char, end_char, color, now),
            )
        return cur.lastrowid
    finally:
        conn.close()


def remove_word_highlight(highlight_id: int) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM word_highlights WHERE id=?", (highlight_id,))
    finally:
        conn.close()


# ── Highlights (verse-level) ──────────────────────────────────────────────────

DEFAULT_HIGHLIGHT = "#f9e2af"  # warm yellow

HIGHLIGHT_COLORS = {
    "Yellow":  "#f9e2af",
    "Green":   "#a6e3a1",
    "Blue":    "#89b4fa",
    "Pink":    "#f38ba8",
    "Peach":   "#fab387",
    "Lavender":"#cba6f7",
}


def get_highlights(book: str, chapter: int) -> dict[int, str]:
    """Returns {verse: color} for all highlighted verses in a chapter."""
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            "SELECT verse, color FROM highlights WHERE book=? AND chapter=?",
            (book, chapter),
        ).fetchall()
        return {r["verse"]: r["color"] for r in rows}
    finally:
        conn.close()


def set_highlight(book: str, chapter: int, verse: int, color: str = DEFAULT_HIGHLIGHT) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """INSERT INTO highlights (book, chapter, verse, color, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(book, chapter, verse) DO UPDATE SET color=excluded.color""",
                (book, chapter, verse, color, now),
            )
    finally:
        conn.close()


def remove_highlight(book: str, chapter: int, verse: int) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM highlights WHERE book=? AND chapter=? AND verse=?",
                (book, chapter, verse),
            )
    finally:
        conn.close()


def toggle_highlight(book: str, chapter: int, verse: int, color: str = DEFAULT_HIGHLIGHT) -> bool:
    """Toggle highlight on/off. Returns True if now highlighted, False if removed."""
    conn = get_readonly_connection()
    try:
        row = conn.execute(
            "SELECT color FROM highlights WHERE book=? AND chapter=? AND verse=?",
            (book, chapter, verse),
        ).fetchone()
    finally:
        conn.close()

    if row:
        remove_highlight(book, chapter, verse)
        return False
    else:
        set_highlight(book, chapter, verse, color)
        return True


# ── Search ────────────────────────────────────────────────────────────────────

_MAX_SEARCH_LEN = 200   # reject suspiciously long search strings


def _validate_search_query(query: str) -> str:
    """
    Return the query stripped of leading/trailing whitespace, or raise ValueError
    if it is empty or exceeds the maximum allowed length.

    All actual DB queries use parameterised placeholders (?) so SQL injection is
    structurally impossible regardless of the query content, but limiting length
    prevents denial-of-service via very large LIKE patterns.
    """
    q = query.strip()
    if not q:
        raise ValueError("Search query must not be empty.")
    if len(q) > _MAX_SEARCH_LEN:
        raise ValueError(
            f"Search query is too long ({len(q)} chars; max {_MAX_SEARCH_LEN})."
        )
    return q


def search_verses(query: str, edition: str, limit: int = 100) -> list[dict]:
    """Full-text LIKE search across verse text. Returns [{book, chapter, verse, text}]."""
    query = _validate_search_query(query)
    limit = min(max(1, int(limit)), 500)   # clamp to [1, 500]
    conn = get_readonly_connection()
    try:
        rows = conn.execute(
            """SELECT book, chapter, verse, text FROM verses
               WHERE edition=? AND text LIKE ?
               ORDER BY book, chapter, verse
               LIMIT ?""",
            (edition, f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_all(query: str, edition: str, limit_each: int = 50) -> list[dict]:
    """
    Search verse text, commentary notes, and media metadata.

    Returns a list of dicts, each with:
        source  : "verse" | "note" | "media"
        book, chapter, verse : location
        snippet : text to display as preview
        label   : short human-readable label (e.g. og_title, filename)
    Results are sorted book/chapter/verse within each source group,
    then interleaved: verses first, then notes, then media.
    """
    query = _validate_search_query(query)
    limit_each = min(max(1, int(limit_each)), 200)   # clamp to [1, 200]
    pat = f"%{query}%"
    conn = get_readonly_connection()
    try:
        v_rows = conn.execute(
            """SELECT book, chapter, verse, text AS snippet
               FROM verses WHERE edition=? AND text LIKE ?
               ORDER BY book, chapter, verse LIMIT ?""",
            (edition, pat, limit_each),
        ).fetchall()

        n_rows = conn.execute(
            """SELECT book, chapter, verse, body AS snippet
               FROM commentary WHERE body LIKE ?
               ORDER BY book, chapter, verse LIMIT ?""",
            (pat, limit_each),
        ).fetchall()

        m_rows = conn.execute(
            """SELECT book, chapter, verse, type,
                      COALESCE(og_title, filename, url, '') AS label,
                      COALESCE(og_description, caption, url, '') AS snippet
               FROM media
               WHERE og_title LIKE ? OR og_description LIKE ?
                  OR caption   LIKE ? OR filename      LIKE ?
                  OR url       LIKE ?
               ORDER BY book, chapter, verse LIMIT ?""",
            (pat, pat, pat, pat, pat, limit_each),
        ).fetchall()

    finally:
        conn.close()

    results: list[dict] = []
    for r in v_rows:
        results.append({"source": "verse", "book": r["book"], "chapter": r["chapter"],
                        "verse": r["verse"], "snippet": r["snippet"], "label": ""})
    for r in n_rows:
        results.append({"source": "note", "book": r["book"], "chapter": r["chapter"],
                        "verse": r["verse"], "snippet": r["snippet"], "label": ""})
    for r in m_rows:
        results.append({"source": "media", "book": r["book"], "chapter": r["chapter"],
                        "verse": r["verse"], "snippet": r["snippet"], "label": r["label"]})
    return results


# ── Preferences ───────────────────────────────────────────────────────────────

def get_pref(key: str, default: str | None = None) -> str | None:
    conn = get_readonly_connection()
    try:
        row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_pref(key: str, value: str) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO preferences (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
    finally:
        conn.close()

