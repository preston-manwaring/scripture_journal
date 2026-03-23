from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_connection

router = APIRouter(prefix="/crosslinks", tags=["crosslinks"])


class CrossLinkCreate(BaseModel):
    source_book: str
    source_chapter: int
    source_verse: int
    target_book: str
    target_chapter: int
    target_verse: int
    note: str | None = None


@router.get("")
def get_crosslinks(
    source_book: str = Query(...),
    source_chapter: int = Query(...),
    source_verse: int = Query(...),
):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, source_book, source_chapter, source_verse,
                      target_book, target_chapter, target_verse, note, created_at
               FROM cross_links
               WHERE source_book=? AND source_chapter=? AND source_verse=?
               ORDER BY created_at""",
            (source_book, source_chapter, source_verse)
        ).fetchall()
        # Also fetch reverse links (this verse is the target)
        rev_rows = conn.execute(
            """SELECT id, source_book, source_chapter, source_verse,
                      target_book, target_chapter, target_verse, note, created_at
               FROM cross_links
               WHERE target_book=? AND target_chapter=? AND target_verse=?
               ORDER BY created_at""",
            (source_book, source_chapter, source_verse)
        ).fetchall()
        return {
            "outbound": [dict(r) for r in rows],
            "inbound": [dict(r) for r in rev_rows],
        }
    finally:
        conn.close()


@router.post("", status_code=201)
def create_crosslink(data: CrossLinkCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO cross_links
                   (source_book, source_chapter, source_verse,
                    target_book, target_chapter, target_verse, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (data.source_book, data.source_chapter, data.source_verse,
                 data.target_book, data.target_chapter, data.target_verse,
                 data.note, now)
            )
        return {"id": cur.lastrowid, "created_at": now}
    finally:
        conn.close()


@router.delete("/{link_id}", status_code=204)
def delete_crosslink(link_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM cross_links WHERE id=?", (link_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cross-link not found")
        with conn:
            conn.execute("DELETE FROM cross_links WHERE id=?", (link_id,))
    finally:
        conn.close()
