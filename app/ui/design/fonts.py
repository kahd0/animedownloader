"""Font registration for the application.

Loads Inter and JetBrains Mono from the assets directory if available,
falling back to system fonts gracefully.
"""
from __future__ import annotations

import os
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "fonts")

_FONT_FILES = [
    ("Inter-Regular.ttf",     "Inter", False, False),
    ("Inter-Medium.ttf",      "Inter", False, False),
    ("Inter-SemiBold.ttf",    "Inter", False, False),
    ("Inter-Bold.ttf",        "Inter", False, False),
    ("JetBrainsMono-Regular.ttf", "JetBrains Mono", False, False),
]

_PRIMARY_FAMILY  = "Inter"
_FALLBACK_FAMILY = "Segoe UI, SF Pro Display, Noto Sans, sans-serif"
_MONO_FAMILY     = "JetBrains Mono"
_MONO_FALLBACK   = "Consolas, Courier New, monospace"

_fonts_registered = False


def register_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return

    for filename, *_ in _FONT_FILES:
        path = os.path.join(ASSETS_DIR, filename)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)

    _fonts_registered = True


def apply_default_font(app: QApplication) -> None:
    register_fonts()
    families = QFontDatabase.families()

    if _PRIMARY_FAMILY in families:
        family = _PRIMARY_FAMILY
    else:
        family = "Segoe UI"

    font = QFont(family, 13)
    font.setWeight(QFont.Weight.Normal)
    app.setFont(font)


def body_font(size: int = 13, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    register_fonts()
    f = QFont(_PRIMARY_FAMILY if _PRIMARY_FAMILY in QFontDatabase.families() else "Segoe UI", size)
    f.setWeight(weight)
    return f


def mono_font(size: int = 12) -> QFont:
    register_fonts()
    families = QFontDatabase.families()
    family = _MONO_FAMILY if _MONO_FAMILY in families else "Consolas"
    f = QFont(family, size)
    f.setWeight(QFont.Weight.Normal)
    return f
