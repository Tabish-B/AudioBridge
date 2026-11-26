"""Render documentation screenshots using synthetic audio and actual Qt widgets."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from examples.make_demo import make_demo
from ui.studio import AudioBridgeGUI


def main():
    app = QApplication([])
    app.setStyle("Fusion")
    with tempfile.TemporaryDirectory() as folder:
        source = make_demo(Path(folder) / "Synthetic quality-check demo.wav")
        window = AudioBridgeGUI()
        window.resize(1512, 1080)
        window.show()
        window.add_files([source])
        state, attempts = 0, 0
        destination = ROOT / "docs"
        destination.mkdir(exist_ok=True)

        def save(name):
            if not window.grab().save(str(destination / name)):
                raise OSError(f"Could not save screenshot: {name}")

        def capture():
            nonlocal state, attempts
            attempts += 1
            plot = window.editor.plot
            ready = (
                plot.preview is not None
                and not plot.spectral_loading
                and window.editor.play_button.isEnabled()
            )
            if ready:
                if state == 0:
                    save("audiobridge.png")
                    window._set_page(2)
                    state = 2
                elif state == 2:
                    save("editor.png")
                    window.editor.view.setCurrentText("Spectrogram")
                    state = 3
                elif state == 3 and plot.preview["spectral_settings"].mode == "Spectrogram":
                    save("spectrogram.png")
                    window.editor.view.setCurrentText("Mel spectrogram")
                    state = 4
                elif state == 4 and plot.preview["spectral_settings"].mode == "Mel spectrogram":
                    save("mel.png")
                    window.editor.view.setCurrentText("MFCC")
                    state = 5
                elif state == 5 and plot.preview["spectral_settings"].mode == "MFCC":
                    save("mfcc.png")
                    window.close()
                    app.exit(0)
                    return
            if attempts >= 600:
                print("Screenshot timed out:", window.status.text())
                window.close()
                app.exit(1)
                return
            QTimer.singleShot(100, capture)

        QTimer.singleShot(400, capture)
        return app.exec()


if __name__ == "__main__":
    sys.exit(main())
