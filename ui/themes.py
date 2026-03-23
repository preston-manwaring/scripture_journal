"""
Colour themes for Scripture Journal.

Module-level colour constants (DARK, SURFACE, …) are resolved at import
time from the active theme stored in config.ini.  A theme change saves the
preference and takes full effect on the next application launch.
"""
from __future__ import annotations

# ── Palette definitions ───────────────────────────────────────────────────────

THEMES: dict[str, dict[str, str]] = {
    "Catppuccin Mocha": {
        "base":     "#1e1e2e",
        "surface":  "#181825",
        "elevated": "#252536",
        "overlay":  "#313244",
        "overlay1": "#45475a",
        "dim":      "#585b70",
        "subtext":  "#a6adc8",
        "text":     "#cdd6f4",
        "select":   "#2a2a4a",
        "accent":   "#7c83e0",
        "red":      "#f38ba8",
        "green":    "#a6e3a1",
        "blue":     "#89b4fa",
        "yellow":   "#f9e2af",
        "peach":    "#fab387",
        "mauve":    "#cba6f7",
    },
    "Catppuccin Latte": {
        "base":     "#eff1f5",
        "surface":  "#e6e9ef",
        "elevated": "#dce0e8",
        "overlay":  "#ccd0da",
        "overlay1": "#bcc0cc",
        "dim":      "#9ca0b0",
        "subtext":  "#6c6f85",
        "text":     "#4c4f69",
        "select":   "#c8ccdd",
        "accent":   "#7287fd",
        "red":      "#d20f39",
        "green":    "#40a02b",
        "blue":     "#1e66f5",
        "yellow":   "#df8e1d",
        "peach":    "#fe640b",
        "mauve":    "#8839ef",
    },
    "Nord": {
        "base":     "#2e3440",
        "surface":  "#272c36",
        "elevated": "#3b4252",
        "overlay":  "#434c5e",
        "overlay1": "#4c566a",
        "dim":      "#4c566a",
        "subtext":  "#d8dee9",
        "text":     "#eceff4",
        "select":   "#434c5e",
        "accent":   "#88c0d0",
        "red":      "#bf616a",
        "green":    "#a3be8c",
        "blue":     "#81a1c1",
        "yellow":   "#ebcb8b",
        "peach":    "#d08770",
        "mauve":    "#b48ead",
    },
    "Solarized Dark": {
        "base":     "#002b36",
        "surface":  "#073642",
        "elevated": "#0d3d4a",
        "overlay":  "#094555",
        "overlay1": "#586e75",
        "dim":      "#657b83",
        "subtext":  "#839496",
        "text":     "#fdf6e3",
        "select":   "#094555",
        "accent":   "#268bd2",
        "red":      "#dc322f",
        "green":    "#859900",
        "blue":     "#6c71c4",
        "yellow":   "#b58900",
        "peach":    "#cb4b16",
        "mauve":    "#d33682",
    },
}

THEME_NAMES: list[str] = list(THEMES.keys())


def get_palette(name: str) -> dict[str, str]:
    return THEMES.get(name, THEMES["Catppuccin Mocha"])


# ── Resolve active palette at import time ─────────────────────────────────────

def _load_active() -> dict[str, str]:
    try:
        from config import get_theme
        return get_palette(get_theme())
    except Exception:
        return get_palette("Catppuccin Mocha")


_p = _load_active()

# Exported colour constants — import these in widget files
DARK     = _p["base"]
SURFACE  = _p["surface"]
ELEVATED = _p["elevated"]
OVERLAY  = _p["overlay"]
OVERLAY1 = _p["overlay1"]
DIM      = _p["dim"]
SUBTEXT  = _p["subtext"]
TEXT     = _p["text"]
SELECT   = _p["select"]
ACCENT   = _p["accent"]
RED      = _p["red"]
GREEN    = _p["green"]
BLUE     = _p["blue"]
YELLOW   = _p["yellow"]
PEACH    = _p["peach"]
MAUVE    = _p["mauve"]


def build_app_stylesheet() -> str:
    """Return a comprehensive QSS stylesheet for the active theme."""
    p = _p
    return f"""
        * {{ font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; }}
        QToolTip {{ background: {p['overlay']}; color: {p['text']};
                    border: 1px solid {p['overlay1']}; }}
        QScrollBar:vertical {{ background: {p['surface']}; width: 8px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {p['overlay1']}; border-radius: 4px;
                                        min-height: 20px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ background: {p['surface']}; height: 8px; margin: 0; }}
        QScrollBar::handle:horizontal {{ background: {p['overlay1']}; border-radius: 4px; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """
