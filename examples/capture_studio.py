"""Render a README screenshot with generated audio, without opening a desktop window."""

import os
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_MEDIA_BACKEND'] = 'ffmpeg'

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from examples.make_demo import make_demo
from ui.studio import AudioBridgeGUI


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    with tempfile.TemporaryDirectory() as folder:
        source = make_demo(Path(folder) / 'Synthetic quality-check demo.wav')
        window = AudioBridgeGUI()
        window.resize(1512, 1080)
        window.show()
        window.add_files([source])
        window._analyze()
        attempts = 0
        def capture():
            nonlocal attempts
            attempts += 1
            if window.plot.preview is not None and window.report is not None and window.play_button.isEnabled():
                destination = ROOT / 'docs' / 'audiobridge.png'
                destination.parent.mkdir(parents=True, exist_ok=True)
                saved = window.grab().save(str(destination))
                window.view.setCurrentText('Spectrogram')
                app.processEvents()
                saved = window.grab().save(str(ROOT / 'docs' / 'spectrogram.png')) and saved
                window.close()
                app.exit(0 if saved else 1)
            elif attempts >= 150:
                window.close()
                app.exit(1)
            else:
                QTimer.singleShot(100, capture)
        QTimer.singleShot(400, capture)
        return app.exec()


if __name__ == '__main__':
    sys.exit(main())
