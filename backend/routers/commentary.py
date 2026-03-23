from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_connection

router = APIRouter(prefix="/commentary", tags=["commentary"])


class CommentaryCreate(BaseModel):
    book: str
    chapter: int
    verse: int
    edition: str | None = None
    body: str


class CommentaryUpdate(BaseModel):
    body: str
    edition: str | None = None


@router.get("")
def get_commentary(
    book: str = Query(...),
    chapter: int = Query(...),
    verse: int = Query(...),
):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, book, chapter, verse, edition, body, created_at, updated_at
               FROM commentary WHERE book=? AND chapter=? AND verse=?
               ORDER BY created_at""",
            (book, chapter, verse)
        ).fetchall()
        return {"commentary": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("", status_code=201)
def create_commentary(data: CommentaryCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO commentary (book, chapter, verse, edition, body, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (data.book, data.chapter, data.verse, data.edition, data.body, now, now)
            )
        return {"id": cur.lastrowid, "created_at": now}
    finally:
        conn.close()


@router.put("/{commentary_id}")
def update_commentary(commentary_id: int, data: CommentaryUpdate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM commentary WHERE id=?", (commentary_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Commentary not found")
        with conn:
            conn.execute(
                "UPDATE commentary SET body=?, edition=?, updated_at=? WHERE id=?",
                (data.body, data.edition, now, commentary_id)
            )
        return {"id": commentary_id, "updated_at": now}
    finally:
        conn.close()


@router.delete("/{commentary_id}", status_code=204)
def delete_commentary(commentary_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM commentary WHERE id=?", (commentary_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Commentary not found")
        with conn:
            conn.execute("DELETE FROM commentary WHERE id=?", (commentary_id,))
    finally:
        conn.close()
