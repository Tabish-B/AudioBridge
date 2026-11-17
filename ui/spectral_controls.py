"""The collapsible spectral settings editor."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from converter.spectral import SpectralSettings


class SpectralControls(QWidget):
    apply_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toggle = QPushButton("Spectral settings ▸")
        toggle.setCheckable(True)
        layout.addWidget(toggle)
        self.body = QWidget()
        form = QFormLayout(self.body)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fft = QComboBox()
        self.fft.addItems(["256", "512", "1024", "2048", "4096", "8192"])
        self.fft.setCurrentText("1024")
        form.addRow("FFT size", self.fft)
        self.hop = QSpinBox()
        self.hop.setRange(64, 8192)
        self.hop.setValue(256)
        form.addRow("Hop (samples)", self.hop)
        self.window = QComboBox()
        self.window.addItems(["Hann", "Hamming", "Blackman", "Rectangular"])
        form.addRow("Window", self.window)
        self.frequency_min = self._number(form, "Min frequency (Hz)", 0, 96000, 0)
        self.frequency_max = self._number(form, "Max Hz (0 = auto)", 0, 96000, 0)
        self.db_min = self._number(form, "dB minimum", -200, 20, -110)
        self.db_max = self._number(form, "dB maximum", -200, 20, -20)
        self.scale = QComboBox()
        self.scale.addItems(["Linear", "Logarithmic"])
        form.addRow("Frequency scale", self.scale)
        self.mel_bands = QSpinBox()
        self.mel_bands.setRange(8, 128)
        self.mel_bands.setValue(64)
        form.addRow("Mel bands", self.mel_bands)
        self.coefficients = QSpinBox()
        self.coefficients.setRange(1, 128)
        self.coefficients.setValue(13)
        form.addRow("MFCC count", self.coefficients)
        self.apply = QPushButton("Apply analysis settings")
        self.apply.clicked.connect(lambda: self.apply_requested.emit())
        form.addRow(self.apply)
        layout.addWidget(self.body)
        self.body.hide()
        toggle.toggled.connect(self.body.setVisible)
        toggle.toggled.connect(
            lambda opened: toggle.setText(
                "Spectral settings ▾" if opened else "Spectral settings ▸"
            )
        )

    @staticmethod
    def _number(form, title, low, high, default):
        widget = QDoubleSpinBox()
        widget.setRange(low, high)
        widget.setDecimals(1)
        widget.setValue(default)
        form.addRow(title, widget)
        return widget

    def settings(self, mode):
        return SpectralSettings(
            fft_size=int(self.fft.currentText()),
            hop_length=self.hop.value(),
            window=["hann", "hamming", "blackman", "boxcar"][self.window.currentIndex()],
            frequency_min=self.frequency_min.value(),
            frequency_max=self.frequency_max.value(),
            db_min=self.db_min.value(),
            db_max=self.db_max.value(),
            frequency_scale=self.scale.currentText(),
            mode=mode,
            mel_bands=self.mel_bands.value(),
            mfcc_count=self.coefficients.value(),
        )

    def set_mode(self, mode):
        self.scale.setEnabled(mode == "Spectrogram")
        self.db_min.setEnabled(mode != "MFCC")
        self.db_max.setEnabled(mode != "MFCC")
        self.mel_bands.setEnabled(mode != "Spectrogram")
        self.coefficients.setEnabled(mode == "MFCC")
