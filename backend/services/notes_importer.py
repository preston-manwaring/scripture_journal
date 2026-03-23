"""
Import highlights and notes from a Church of Jesus Christ study app CSV export.

URL format parsed:
  .../study/scriptures/bofm/{book-abbrev}/{chapter}?lang=eng&id=p{verse}
  .../study/scriptures/bofm/{book-abbrev}/{chapter}?lang=eng&id=p{v1}-p{v2}  (range)

Row types handled:
  highlight  → verse-level highlight; also commentary if note text present
  reference  → commentary if note text present (no highlight inserted)
  journal    → source location is "undefined"; skipped (no verse URL)

Non-Book-of-Mormon URLs are skipped.

Note: The CSV export from churchofjesuschrist.org records only which verse was
highlighted (id=pN), not which words within the verse. Word-level highlights
cannot be reconstructed from this data; all highlights are imported as
verse-level highlights.

Duplicate detection:
  - highlights:  skipped if same (book, chapter, verse) already exists
  - commentary:  skipped if same (book, chapter, verse, body, created_at) exists
"""

from __future__ import annotations
import csv
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

from backend.database import get_connection

# Church website abbreviation → canonical book name
BOOK_ABBREV = {
    "1-ne":  "1 Nephi",
    "2-ne":  "2 Nephi",
    "jacob": "Jacob",
    "enos":  "Enos",
    "jarom": "Jarom",
    "omni":  "Omni",
    "w-of-m": "Words of Mormon",
    "mosiah": "Mosiah",
    "alma":  "Alma",
    "hel":   "Helaman",
    "3-ne":  "3 Nephi",
    "4-ne":  "4 Nephi",
    "morm":  "Mormon",
    "ether": "Ether",
    "moro":  "Moroni",
}

# Matches  .../scriptures/bofm/{abbrev}/{chapter}
_URL_PATH_RE = re.compile(
    r"/study/scriptures/bofm/([^/]+)/(\d+)",
    re.IGNORECASE,
)

# Matches id=p5 or id=p5-p7
_VERSE_RE = re.compile(r"p(\d+)(?:-p(\d+))?")


def _parse_url(url: str) -> list[tuple[str, int, int]] | None:
    """
    Return a list of (book, chapter, verse) tuples for the URL,
    or None if the URL is not a recognised BoM verse link.
    Handles single verses and ranges.
    """
    parsed = urlparse(url)
    m = _URL_PATH_RE.search(parsed.path)
    if not m:
        return None

    abbrev = m.group(1).lower()
    book = BOOK_ABBREV.get(abbrev)
    if not book:
        return None

    chapter = int(m.group(2))

    qs = parse_qs(parsed.query)
    id_vals = qs.get("id", [])
    if not id_vals:
        return None

    verse_m = _VERSE_RE.search(id_vals[0])
    if not verse_m:
        return None

    v_start = int(verse_m.group(1))
    v_end   = int(verse_m.group(2)) if verse_m.group(2) else v_start
    return [(book, chapter, v) for v in range(v_start, v_end + 1)]


def _normalize_ts(ts: str) -> str:
    """Convert an ISO-8601 string (possibly with Z) to a UTC isoformat string."""
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def import_notes(
    csv_path: str,
    conn=None,
    progress_cb=None,  # optional callable(message: str)
) -> dict:
    """
    Import notes and highlights from *csv_path*.

    Returns a summary dict:
        {imported_notes: int, imported_highlights: int,
         skipped_bad_url: int, skipped_duplicate: int, errors: list[str]}
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    summary = {
        "imported_notes": 0,
        "imported_highlights": 0,
        "skipped_bad_url": 0,
        "skipped_duplicate": 0,
        "errors": [],
    }

    def _log(msg):
        if progress_cb:
            progress_cb(msg)
        else:
            print(msg, flush=True)

    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        _log(f"Read {len(rows)} rows from {os.path.basename(csv_path)}")

        for i, row in enumerate(rows):
            try:
                row_type  = (row.get("type") or "").strip().lower()
                note_text = (row.get("note text") or "").strip()
                title     = (row.get("title") or "").strip()
                url       = (row.get("source location") or "").strip()
                created   = _normalize_ts(row.get("created", ""))
                updated   = _normalize_ts(row.get("last updated", ""))

                # Build commentary body from title + note text
                meaningful_title = title if title and title.lower() != "undefined" else ""
                if meaningful_title and note_text:
                    body = f"{meaningful_title}\n\n{note_text}"
                elif meaningful_title:
                    body = meaningful_title
                else:
                    body = note_text

                verses = _parse_url(url)
                if not verses:
                    summary["skipped_bad_url"] += 1
                    continue

                for (book, chapter, verse) in verses:
                    # ── Verse-level highlight (highlight rows only) ───────────
                    if row_type == "highlight":
                        existing_hl = conn.execute(
                            "SELECT id FROM highlights WHERE book=? AND chapter=? AND verse=?",
                            (book, chapter, verse),
                        ).fetchone()
                        if existing_hl:
                            summary["skipped_duplicate"] += 1
                        else:
                            with conn:
                                conn.execute(
                                    """INSERT INTO highlights (book, chapter, verse, color, created_at)
                                       VALUES (?, ?, ?, '#f9e2af', ?)""",
                                    (book, chapter, verse, created),
                                )
                            summary["imported_highlights"] += 1

                    # ── Commentary (any row with note/title text) ─────────────
                    if body:
                        existing_note = conn.execute(
                            """SELECT id FROM commentary
                               WHERE book=? AND chapter=? AND verse=? AND body=? AND created_at=?""",
                            (book, chapter, verse, body, created),
                        ).fetchone()
                        if existing_note:
                            summary["skipped_duplicate"] += 1
                        else:
                            with conn:
                                conn.execute(
                                    """INSERT INTO commentary
                                       (book, chapter, verse, edition, body, created_at, updated_at)
                                       VALUES (?, ?, ?, NULL, ?, ?, ?)""",
                                    (book, chapter, verse, body, created, updated),
                                )
                            summary["imported_notes"] += 1

            except Exception as e:
                msg = f"  Row {i+2}: error — {e}"
                summary["errors"].append(msg)
                _log(msg)

        _log(
            f"Done. Notes: {summary['imported_notes']}, "
            f"Highlights: {summary['imported_highlights']}, "
            f"Non-BoM URLs: {summary['skipped_bad_url']}, "
            f"Duplicates: {summary['skipped_duplicate']}, "
            f"Errors: {len(summary['errors'])}"
        )

    finally:
        if own_conn:
            conn.close()

    return summary


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "NotesDownload.csv"
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        sys.exit(1)
    from backend.database import init_db
    init_db()
    import_notes(csv_path)
