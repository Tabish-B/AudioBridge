"""Offline help for the interactions available in the editor."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AudioBridge · Help & shortcuts")
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        text = QTextBrowser()
        text.setOpenExternalLinks(False)
        text.setMarkdown("""# Help & shortcuts

| Action | Shortcut |
| --- | --- |
| Add files | Ctrl / Command + O |
| Add folder | Ctrl / Command + Shift + O |
| Play / pause | Space |
| Zoom in / out | Ctrl / Command + mouse wheel |
| Selection start / end at cursor | I / O |
| Clear selection | Escape |
| Remove queued file | Delete / Backspace |
| Show this help | F1 |

**Select audio:** drag left or right across the plot. A click moves the cursor.
You can also enter exact start/end seconds below the player.

**Listen:** Play selection prepares a temporary clip containing only that region.
Use the main play button or Space to pause or resume it.

**Export:** Export selection writes the highlighted audio to a new file using the
export settings. Split at cursor creates two new files. Source recordings stay intact.
Existing filenames are never replaced.

**Analyze:** choose Spectrogram, Mel spectrogram, or MFCC. Open Spectral settings,
change the parameters, then Apply. Invalid settings explain what needs changing.
Linear/log frequency applies to the standard spectrogram. dB bounds control the standard
and Mel views. Mel uses its
own frequency spacing and MFCC uses coefficient values rather than dB.
Use **Export view PNG** to save the full-recording analysis image with its time axis,
frequency or coefficient ticks, and settings in the PNG metadata.

**Annotate:** choose a queued recording, select an interval on its waveform, choose a
tier, and add text. Double-click a row to jump back to it. Segments can be edited, played,
and exported to AudioBridge JSON or CSV.

**If an import fails:** check the filename shown in the notice. Remove damaged or
unsupported files; other queued files can still be converted. If an output folder
is unavailable, select another folder and retry.

Delete and Backspace remove a queued recording only while the queue has focus.
Single-key shortcuts pause while typing in a text field.
""")
        layout.addWidget(text)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
