"""Read/write config.ini for persistent app settings (theme, etc.)."""
from __future__ import annotations
import configparser
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")
_DEFAULTS = {
    "theme": "Catppuccin Mocha",
}


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATH)
    if "app" not in cfg:
        cfg["app"] = {}
    for key, val in _DEFAULTS.items():
        cfg["app"].setdefault(key, val)
    return cfg


def save_config(cfg: configparser.ConfigParser) -> None:
    with open(_CONFIG_PATH, "w") as fh:
        cfg.write(fh)


def get_theme() -> str:
    return load_config()["app"].get("theme", _DEFAULTS["theme"])


def set_theme(name: str) -> None:
    cfg = load_config()
    cfg["app"]["theme"] = name
    save_config(cfg)
