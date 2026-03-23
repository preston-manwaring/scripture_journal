"""
Reconstruct verse text from a list of (wid, token) pairs for one edition.

Token rules:
  ⌴  (U+2364) → emit a single space character
  ∅  (U+2205) → skip (word absent in this edition)
  anything else → emit as-is

WID sort key: "1" → (1, 0), "1.01" → (1, 1), "1.02" → (1, 2), etc.
"""

SPACE_CHAR = "\u2334"  # ⌴ (U+2334, as used in the TSV files)
ABSENT_CHAR = "\u2205"  # ∅


def wid_sort_key(wid: str) -> tuple[int, int]:
    # Some TSV files use comma as decimal separator (e.g. "2,01" instead of "2.01")
    normalized = wid.replace(",", ".")
    parts = normalized.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    return (major, minor)


def reconstruct(tokens: list[tuple[str, str]]) -> str:
    """
    tokens: list of (wid, token_value) pairs, unsorted.
    Returns the reconstructed verse string.
    """
    sorted_tokens = sorted(tokens, key=lambda t: wid_sort_key(t[0]))
    parts = []
    for _wid, token in sorted_tokens:
        if token == ABSENT_CHAR or token is None:
            continue
        if token == SPACE_CHAR:
            parts.append(" ")
        else:
            parts.append(token)
    return "".join(parts)
