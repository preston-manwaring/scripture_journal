import difflib
from fastapi import APIRouter, HTTPException, Query

from backend.database import get_connection
from backend.services.verse_reconstructor import ABSENT_CHAR, wid_sort_key

router = APIRouter(prefix="/scripture", tags=["scripture"])

EDITIONS = ["1830", "1837", "1840", "1841", "1879", "1920", "1981", "2013"]

BOOK_ORDER = [
    "1 Nephi", "2 Nephi", "Jacob", "Enos", "Jarom", "Omni",
    "Words of Mormon", "Mosiah", "Alma", "Helaman",
    "3 Nephi", "4 Nephi", "Mormon", "Ether", "Moroni",
]


@router.get("/books")
def list_books():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT book FROM verses").fetchall()
        books = [r["book"] for r in rows]
        books.sort(key=lambda b: BOOK_ORDER.index(b) if b in BOOK_ORDER else 99)
        return {"books": books}
    finally:
        conn.close()


@router.get("/books/{book}/chapters")
def list_chapters(book: str):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT chapter FROM verses WHERE book=? ORDER BY chapter",
            (book,)
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"Book not found: {book}")
        return {"book": book, "chapters": [r["chapter"] for r in rows]}
    finally:
        conn.close()


@router.get("/books/{book}/chapters/{chapter}/verses")
def list_verses(book: str, chapter: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT verse FROM verses WHERE book=? AND chapter=? ORDER BY verse",
            (book, chapter)
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"Chapter not found: {book} {chapter}")
        return {"book": book, "chapter": chapter, "verses": [r["verse"] for r in rows]}
    finally:
        conn.close()


@router.get("/verse")
def get_verse(
    book: str = Query(...),
    chapter: int = Query(...),
    verse: int = Query(...),
    edition: str = Query("2013"),
):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT text FROM verses WHERE book=? AND chapter=? AND verse=? AND edition=?",
            (book, chapter, verse, edition)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Verse not found")
        return {"book": book, "chapter": chapter, "verse": verse, "edition": edition, "text": row["text"]}
    finally:
        conn.close()


@router.get("/passage")
def get_passage(
    book: str = Query(...),
    chapter: int = Query(...),
    verse_start: int = Query(1),
    verse_end: int = Query(999),
    edition: str = Query("2013"),
):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT verse, text FROM verses
               WHERE book=? AND chapter=? AND edition=?
                 AND verse BETWEEN ? AND ?
               ORDER BY verse""",
            (book, chapter, edition, verse_start, verse_end)
        ).fetchall()
        return {
            "book": book, "chapter": chapter, "edition": edition,
            "verses": [{"verse": r["verse"], "text": r["text"]} for r in rows]
        }
    finally:
        conn.close()


@router.get("/editions")
def list_editions():
    return {"editions": EDITIONS}


@router.get("/diff")
def get_diff(
    book: str = Query(...),
    chapter: int = Query(...),
    verse: int = Query(...),
    edition_a: str = Query("1830"),
    edition_b: str = Query("2013"),
):
    conn = get_connection()
    try:
        # Fetch tokens for both editions
        rows = conn.execute(
            """SELECT wid, edition, token FROM verse_tokens
               WHERE book=? AND chapter=? AND verse=? AND edition IN (?, ?)
               ORDER BY edition""",
            (book, chapter, verse, edition_a, edition_b)
        ).fetchall()

        def build_token_list(edition: str) -> list[str]:
            edition_rows = [(r["wid"], r["token"]) for r in rows if r["edition"] == edition]
            edition_rows.sort(key=lambda t: wid_sort_key(t[0]))
            result = []
            for _wid, token in edition_rows:
                if token is None or token == ABSENT_CHAR:
                    continue
                result.append(token)
            return result

        tokens_a = build_token_list(edition_a)
        tokens_b = build_token_list(edition_b)

        # Get reconstructed texts
        text_a_row = conn.execute(
            "SELECT text FROM verses WHERE book=? AND chapter=? AND verse=? AND edition=?",
            (book, chapter, verse, edition_a)
        ).fetchone()
        text_b_row = conn.execute(
            "SELECT text FROM verses WHERE book=? AND chapter=? AND verse=? AND edition=?",
            (book, chapter, verse, edition_b)
        ).fetchone()

        if not text_a_row or not text_b_row:
            raise HTTPException(status_code=404, detail="Verse not found in one or both editions")

        # Compute token-level diff
        matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
        diff_tokens = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for tok in tokens_a[i1:i2]:
                    diff_tokens.append({"token": tok, "status": "same"})
            elif tag == "replace":
                for tok in tokens_a[i1:i2]:
                    diff_tokens.append({"token": tok, "status": "removed"})
                for tok in tokens_b[j1:j2]:
                    diff_tokens.append({"token": tok, "status": "added"})
            elif tag == "delete":
                for tok in tokens_a[i1:i2]:
                    diff_tokens.append({"token": tok, "status": "removed"})
            elif tag == "insert":
                for tok in tokens_b[j1:j2]:
                    diff_tokens.append({"token": tok, "status": "added"})

        return {
            "edition_a": {"edition": edition_a, "text": text_a_row["text"]},
            "edition_b": {"edition": edition_b, "text": text_b_row["text"]},
            "diff_tokens": diff_tokens,
        }
    finally:
        conn.close()
