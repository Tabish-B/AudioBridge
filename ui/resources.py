"""Shared asset paths and the multi-resolution application icon."""

import json
import sys
from pathlib import Path

from PySide6.QtGui import QIcon

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ASSET_DIR = ROOT / "assets"
ICON_SET = ASSET_DIR / "icons" / "AppIcon.appiconset"


def application_icon():
    icon = QIcon()
    catalog = json.loads((ICON_SET / "Contents.json").read_text())
    for entry in catalog["images"]:
        icon.addFile(str(ICON_SET / entry["filename"]))
    return icon
