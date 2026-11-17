"""Launch AudioBridge's local conversion studio."""

import os
import sys
from pathlib import Path

# AVFoundation avoids FFmpeg playback stalls on macOS; exports still use FFmpeg.
if sys.platform == "darwin":
    os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.resources import application_icon
from ui.startup import StartupSplash
from version import __version__


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AudioBridge")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("AudioBridge")
    app.setWindowIcon(application_icon())
    app.setStyle("Fusion")
    splash = StartupSplash()
    splash.show()
    app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
    window = None
    startup_failed = False

    def open_workspace():
        nonlocal window, startup_failed
        # Import the audio stack after the splash has had a chance to paint.
        try:
            from ui.studio import AudioBridgeGUI

            window = AudioBridgeGUI()
        except (ImportError, RuntimeError) as exc:
            startup_failed = True
            splash.close()
            QMessageBox.critical(None, "AudioBridge could not start", str(exc))
            app.quit()
            return
        window.show()
        splash.finish(window)
        window.raise_()
        window.activateWindow()
        window.add_files([Path(arg) for arg in sys.argv[1:]])

    QTimer.singleShot(0, open_workspace)
    result = app.exec()
    return 1 if startup_failed else result


if __name__ == "__main__":
    sys.exit(main())
