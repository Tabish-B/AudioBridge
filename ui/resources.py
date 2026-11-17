"""Shared asset paths and the multi-resolution application icon."""

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPainter, QPixmap

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
    """Load the platform icon sizes with the supplied rounded silhouette."""
    icon = QIcon()
    catalog = json.loads((ICON_SET / "Contents.json").read_text())
    mask_source = QPixmap(str(ASSET_DIR / "audiobridge.png"))
    for entry in catalog["images"]:
        source = QPixmap(str(ICON_SET / entry["filename"]))
        pixmap = QPixmap(source.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        mask = mask_source.scaled(
            source.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(pixmap)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawPixmap(0, 0, mask)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
