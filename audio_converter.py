"""Launch AudioBridge's local conversion studio."""

import os
import sys
from pathlib import Path

# AVFoundation avoids FFmpeg playback stalls on macOS; exports still use FFmpeg.
if sys.platform == 'darwin':
    os.environ.setdefault('QT_MEDIA_BACKEND', 'darwin')

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.studio import AudioBridgeGUI, ASSET_DIR


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('AudioBridge')
    app.setOrganizationName('AudioBridge')
    app.setWindowIcon(QIcon(str(ASSET_DIR / 'audiobridge.png')))
    app.setStyle('Fusion')
    try:
        window = AudioBridgeGUI()
    except RuntimeError as exc:
        QMessageBox.critical(None, 'AudioBridge could not start', str(exc))
        return 1
    window.show()
    window.raise_()
    window.activateWindow()
    window.add_files([Path(arg) for arg in sys.argv[1:]])
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
