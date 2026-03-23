"""Generate a LaTeX document for a scripture passage with optional commentary/media."""

import os
import re
import tempfile
from jinja2 import Environment, FileSystemLoader

from backend.database import get_readonly_connection

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")

# Characters that need escaping in LaTeX
_LATEX_SPECIAL = re.compile(r'([&%$#_{}~^\\])')


def _apply_word_highlights_latex(plain_text: str, word_highlights: list[dict]) -> str:
    """
    Convert *plain_text* + *word_highlights* into a LaTeX snippet where each
    highlighted span is wrapped in ``\\colorbox{hlN}{text}``.

    Returns the plain-text-escaped LaTeX string when there are no highlights.
    *word_highlights* is a list of {start_char, end_char, color} dicts.
    """
    if not word_highlights:
        return latex_escape(plain_text)

    spans = sorted(word_highlights, key=lambda h: h["start_char"])
    n = len(plain_text)
    parts: list[str] = []
    pos = 0

    for hl in spans:
        s = max(pos, hl["start_char"])
        e = min(n, hl["end_char"])
        if e <= s:
            continue
        if s > pos:
            parts.append(latex_escape(plain_text[pos:s]))
        # Use pre-registered color name if available, else fall back to hex
        color_name = hl.get("_latex_color") or hl.get("color", "yellow")
        parts.append(
            f"\\colorbox{{{color_name}}}{{{latex_escape(plain_text[s:e])}}}"
        )
        pos = e

    if pos < n:
        parts.append(latex_escape(plain_text[pos:]))

    return "".join(parts)


def latex_escape(text: str) -> str:
    if not text:
        return ""
    # Escape backslash first to avoid double-escaping
    text = text.replace("\\", r"\textbackslash{}")
    text = re.sub(r'([&%$#_{}])', r'\\\1', text)
    text = text.replace("~", r"\textasciitilde{}")
    text = text.replace("^", r"\textasciicircum{}")
    return text


def _setup_jinja() -> Environment:
    # Use non-conflicting delimiters to avoid clashes with LaTeX syntax
    # (LaTeX uses { } # % which conflict with Jinja2's defaults)
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["latex_escape"] = latex_escape
    env.filters["truncate"] = lambda s, n: (s[:n] + "…") if len(s) > n else s
    return env


def generate(
    book: str,
    chapter_start: int,
    chapter_end: int,
    edition: str,
    include_commentary: bool = True,
    include_media: bool = True,
) -> str:
    """
    Generate a .tex file and return its path.
    Also extracts image BLOBs to temp files alongside the .tex for pdflatex.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = get_readonly_connection()
    chapters_data = []
    all_chapters = list(range(chapter_start, chapter_end + 1))
    image_temp_files = []
    # color_defs: maps LaTeX color name → hex value (built as we encounter spans)
    color_defs: dict[str, str] = {}
    _color_counter = [0]  # mutable int for use inside nested function

    def _get_color_name(hex_color: str) -> str:
        """Return a stable LaTeX color name for hex_color, registering it."""
        for k, v in color_defs.items():
            if v == hex_color:
                return k
        name = f"whl{_color_counter[0]}"
        _color_counter[0] += 1
        color_defs[name] = hex_color
        return name

    try:
        for ch in all_chapters:
            verse_rows = conn.execute(
                """SELECT verse, text FROM verses
                   WHERE book=? AND chapter=? AND edition=?
                   ORDER BY verse""",
                (book, ch, edition)
            ).fetchall()

            # Load word highlights for all verses in this chapter at once
            whl_rows = conn.execute(
                """SELECT verse, start_char, end_char, color
                   FROM word_highlights
                   WHERE book=? AND chapter=?
                   ORDER BY verse, start_char""",
                (book, ch),
            ).fetchall()
            chapter_whl: dict[int, list[dict]] = {}
            for wr in whl_rows:
                chapter_whl.setdefault(wr["verse"], []).append(
                    {"start_char": wr["start_char"], "end_char": wr["end_char"],
                     "color": wr["color"]}
                )

            verses = []
            for vr in verse_rows:
                v_num = vr["verse"]

                # Commentary
                commentary = []
                if include_commentary:
                    c_rows = conn.execute(
                        """SELECT body, created_at FROM commentary
                           WHERE book=? AND chapter=? AND verse=?
                           ORDER BY created_at""",
                        (book, ch, v_num)
                    ).fetchall()
                    commentary = []
                    for r in c_rows:
                        date_str = ""
                        if r["created_at"]:
                            try:
                                from datetime import datetime, timezone
                                dt = datetime.fromisoformat(r["created_at"])
                                date_str = dt.astimezone().strftime("%B %-d, %Y")
                            except Exception:
                                date_str = r["created_at"][:10]
                        commentary.append({"body": r["body"], "date": date_str})

                # Cross-links
                cl_rows = conn.execute(
                    """SELECT target_book, target_chapter, target_verse, note
                       FROM cross_links
                       WHERE source_book=? AND source_chapter=? AND source_verse=?""",
                    (book, ch, v_num)
                ).fetchall()
                cross_links = [
                    {
                        "target": f"{r['target_book']} {r['target_chapter']}:{r['target_verse']}",
                        "note": r["note"],
                    }
                    for r in cl_rows
                ]

                # Media
                images = []
                links = []
                if include_media:
                    m_rows = conn.execute(
                        """SELECT id, type, filename, mime_type, data,
                                  url, og_title, og_description, caption
                           FROM media WHERE book=? AND chapter=? AND verse=?
                           ORDER BY created_at""",
                        (book, ch, v_num)
                    ).fetchall()
                    for mr in m_rows:
                        if mr["type"] == "image" and mr["data"]:
                            # Write BLOB to a temp file that pdflatex can read
                            ext = (mr["mime_type"] or "image/png").split("/")[-1]
                            tmp = tempfile.NamedTemporaryFile(
                                suffix=f".{ext}", dir=OUTPUT_DIR, delete=False
                            )
                            tmp.write(bytes(mr["data"]))
                            tmp.close()
                            image_temp_files.append(tmp.name)
                            images.append({
                                "path": tmp.name,
                                "caption": mr["caption"],
                            })
                        elif mr["type"] == "link":
                            links.append({
                                "url": mr["url"],
                                "og_title": mr["og_title"],
                                "caption": mr["caption"],
                            })

                # Build verse text with word highlights
                v_word_hls = chapter_whl.get(v_num, [])
                # Rename colors to stable LaTeX names
                renamed_hls = []
                for hl in v_word_hls:
                    color_name = _get_color_name(hl["color"])
                    renamed_hls.append({**hl, "_latex_color": color_name})
                verse_text_latex = _apply_word_highlights_latex(
                    vr["text"], renamed_hls
                ) if renamed_hls else latex_escape(vr["text"])

                verses.append({
                    "verse": v_num,
                    "text": verse_text_latex,
                    "commentary": commentary,
                    "cross_links": cross_links,
                    "images": images,
                    "links": links,
                })

            chapters_data.append((ch, verses))

    finally:
        conn.close()

    env = _setup_jinja()
    template = env.get_template("scripture_export.tex.j2")
    rendered = template.render(
        book=latex_escape(book),
        chapters=all_chapters,
        color_defs=color_defs,
        chapters_data=chapters_data,
        edition=edition,
        include_commentary=include_commentary,
        include_media=include_media,
    )

    tex_path = os.path.join(OUTPUT_DIR, "export.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    return tex_path
