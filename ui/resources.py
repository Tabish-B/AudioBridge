"""Shared asset paths and the multi-resolution application icon."""

import json
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPixmap

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ASSET_DIR = ROOT / "assets"
ICON_SET = ASSET_DIR / "icons" / "AppIcon.appiconset"


def configure_application_font(app):
    font = QFont()
    if sys.platform == "darwin":
        font.setFamilies(
            ["Helvetica Neue", "Kohinoor Devanagari", "Arial Unicode MS", "Apple Color Emoji"]
        )
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    app.setFont(font)


def application_icon():
    """Load the pre-rendered icon sizes without resizing or masking their edges."""
    icon = QIcon()
    catalog = json.loads((ICON_SET / "Contents.json").read_text())
    for entry in catalog["images"]:
        pixmap = QPixmap(str(ICON_SET / entry["filename"]))
        pixmap.setDevicePixelRatio(float(entry["scale"].removesuffix("x")))
        icon.addPixmap(pixmap)
    return icon
