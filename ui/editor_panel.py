"""The waveform, spectral controls, transport, and region editor view."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QScrollBar,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
)

from .audio_plot import AudioPlot
from .region_controls import RegionControls
from .spectral_controls import SpectralControls
from .widgets import button, label


class EditorPanel(QFrame):
    analyze_requested = Signal()
    report_requested = Signal()
    zoom_requested = Signal(float)
    play_requested = Signal()
    restart_requested = Signal()
    open_editor_requested = Signal()

    def __init__(self, asset_dir):
        super().__init__()
        self.setObjectName("card")
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(8)
        self.preview_header = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.preview_header.addWidget(label("Audio preview", "heading"), 1)
        box.addLayout(self.preview_header)
        self.filename = label("No file selected", "muted")
        self.filename.setWordWrap(True)
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        box.addWidget(self.filename)
        self.file_properties = label("", "muted")
        self.file_properties.setWordWrap(True)
        box.addWidget(self.file_properties)
        actions = QHBoxLayout()
        self.analyze_button = button("Analyze file", self.analyze_requested.emit)
        self.analyze_button.setEnabled(False)
        self.export_button = button("Export JSON", self.report_requested.emit, "quiet")
        self.export_button.setEnabled(False)
        actions.addWidget(self.analyze_button)
        actions.addWidget(self.export_button)
        actions.addStretch()
        self.open_editor = button("Advanced editor →", self.open_editor_requested.emit, "quiet")
        self.preview_header.addLayout(actions)
        box.addWidget(self.open_editor)
        switch = QHBoxLayout()
        self.view = QComboBox()
        self.view.addItems(["Waveform", "Spectrogram", "Mel spectrogram", "MFCC"])
        switch.addWidget(self.view)
        self.zoom = QComboBox()
        self.zoom.addItems(
            [
                "Full recording",
                "30 s window",
                "2 min window",
                "10 min window",
                "1 s window",
                "5 s window",
                "Custom window",
            ]
        )
        switch.addWidget(self.zoom)
        switch.addStretch()
        self.zoom_in = button("+", lambda: self.zoom_requested.emit(0.5), "quiet")
        self.zoom_out = button("−", lambda: self.zoom_requested.emit(2), "quiet")
        self.zoom_in.setToolTip("Zoom in (Ctrl / Command + mouse wheel)")
        self.zoom_out.setToolTip("Zoom out")
        zoom_actions = QHBoxLayout()
        zoom_actions.addWidget(self.zoom_in)
        zoom_actions.addWidget(self.zoom_out)
        zoom_actions.addStretch()
        box.addLayout(switch)
        box.addLayout(zoom_actions)
        self.spectral_controls = SpectralControls()
        self.spectral_controls.set_mode("Spectrogram")
        box.addWidget(self.spectral_controls)
        self.preview_note = label("Full recording · scroll horizontally when zoomed in", "muted")
        self.preview_note.setWordWrap(True)
        box.addWidget(self.preview_note)
        self.plot = AudioPlot()
        self.plot.setMinimumHeight(130)
        box.addWidget(self.plot, 1)
        self.timeline_scroll = QScrollBar(Qt.Orientation.Horizontal)
        self.timeline_scroll.setRange(0, 0)
        self.timeline_scroll.hide()
        self.timeline_scroll.setToolTip("Scroll through the visible time window")
        box.addWidget(self.timeline_scroll)
        self.follow = QCheckBox("Follow playback when zoomed in")
        self.follow.setChecked(True)
        self.follow.hide()
        box.addWidget(self.follow)
        self.spectrum_legend = label(
            "Frequency: 0 Hz → source Nyquist · Color: −110 to −20 dBFS/Hz (peak per time bin)",
            "muted",
        )
        self.spectrum_legend.setWordWrap(True)
        self.spectrum_legend.hide()
        box.addWidget(self.spectrum_legend)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        box.addWidget(self.seek_slider)
        self.transport = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        playback = QHBoxLayout()
        self.play_button = button("", self.play_requested.emit, "primary")
        self.play_button.setIcon(QIcon(str(asset_dir / "play.svg")))
        self.play_button.setFixedWidth(40)
        self.play_button.setEnabled(False)
        self.play_button.setToolTip("Play / pause (Space)")
        playback.addWidget(self.play_button)
        restart = button("", self.restart_requested.emit, "quiet")
        restart.setIcon(QIcon(str(asset_dir / "restart.svg")))
        restart.setToolTip("Restart recording")
        playback.addWidget(restart)
        self.time_label = label("00:00 / 00:00", "muted")
        playback.addWidget(self.time_label)
        playback.addStretch()
        self.transport.addLayout(playback, 1)
        levels = QHBoxLayout()
        self.speed = QComboBox()
        self.speed.addItems(["0.75×", "1×", "1.25×", "1.5×", "2×"])
        self.speed.setCurrentIndex(1)
        self.speed.setFixedWidth(80)
        levels.addWidget(self.speed)
        levels.addWidget(label("Vol", "muted"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(65)
        levels.addWidget(self.volume)
        levels.addStretch()
        self.transport.addLayout(levels)
        box.addLayout(self.transport)
        self.metrics = label(
            "Run audio checks to inspect levels, clipping, and quiet sections.", "muted"
        )
        self.metrics.setWordWrap(True)
        box.addWidget(self.metrics)
        self.region_controls = RegionControls()
        box.addWidget(self.region_controls)
