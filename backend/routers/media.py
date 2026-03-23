from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel

from backend.database import get_connection
from backend.services.og_fetcher import fetch_og

router = APIRouter(prefix="/media", tags=["media"])


@router.get("")
def get_media(
    book: str = Query(...),
    chapter: int = Query(...),
    verse: int = Query(...),
):
    """Return media metadata for a verse (no BLOB data)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, type, filename, mime_type, url,
                      og_title, og_description, og_image_mime, caption, created_at
               FROM media WHERE book=? AND chapter=? AND verse=?
               ORDER BY created_at""",
            (book, chapter, verse)
        ).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            # Add a flag indicating whether a displayable image is available
            if r["type"] == "image":
                item["has_image"] = True
            elif r["type"] == "link":
                item["has_image"] = r["og_image_mime"] is not None
            items.append(item)
        return {"media": items}
    finally:
        conn.close()


@router.post("/image", status_code=201)
async def attach_image(
    book: str = Form(...),
    chapter: int = Form(...),
    verse: int = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
):
    data = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO media
                   (book, chapter, verse, type, filename, mime_type, data, caption, created_at)
                   VALUES (?, ?, ?, 'image', ?, ?, ?, ?, ?)""",
                (book, chapter, verse, file.filename, mime_type, data,
                 caption or None, now)
            )
        return {
            "id": cur.lastrowid,
            "type": "image",
            "filename": file.filename,
            "mime_type": mime_type,
            "caption": caption or None,
            "created_at": now,
            "has_image": True,
        }
    finally:
        conn.close()


class LinkAttach(BaseModel):
    book: str
    chapter: int
    verse: int
    url: str
    caption: str | None = None


@router.post("/link", status_code=201)
def attach_link(data: LinkAttach):
    now = datetime.now(timezone.utc).isoformat()
    try:
        og = fetch_og(data.url)
    except Exception as e:
        # Still save the link even if OG fetch fails
        og = {"og_title": None, "og_description": None, "og_image": None, "og_image_mime": None}

    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO media
                   (book, chapter, verse, type, url,
                    og_title, og_description, og_image, og_image_mime, caption, created_at)
                   VALUES (?, ?, ?, 'link', ?, ?, ?, ?, ?, ?, ?)""",
                (data.book, data.chapter, data.verse, data.url,
                 og["og_title"], og["og_description"],
                 og["og_image"], og["og_image_mime"],
                 data.caption, now)
            )
        return {
            "id": cur.lastrowid,
            "type": "link",
            "url": data.url,
            "og_title": og["og_title"],
            "og_description": og["og_description"],
            "og_image_mime": og["og_image_mime"],
            "has_image": og["og_image"] is not None,
            "caption": data.caption,
            "created_at": now,
        }
    finally:
        conn.close()


@router.get("/{media_id}/image")
def get_image(media_id: int):
    """Stream image bytes for an image or link-preview thumbnail."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT type, data, mime_type, og_image, og_image_mime FROM media WHERE id=?",
            (media_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Media not found")

        if row["type"] == "image":
            blob, mime = row["data"], row["mime_type"]
        else:
            blob, mime = row["og_image"], row["og_image_mime"]

        if not blob:
            raise HTTPException(status_code=404, detail="No image data for this media item")

        return Response(content=bytes(blob), media_type=mime or "image/jpeg")
    finally:
        conn.close()


@router.delete("/{media_id}", status_code=204)
def delete_media(media_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM media WHERE id=?", (media_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Media not found")
        with conn:
            conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    finally:
        conn.close()
