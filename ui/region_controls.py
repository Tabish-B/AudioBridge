"""Timestamp editing and non-destructive region actions."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RegionControls(QWidget):
    selection_changed = Signal(float, float)
    play_requested = Signal()
    export_requested = Signal()
    split_requested = Signal()
    clear_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Selection · drag across the plot or enter seconds"))
        times = QFormLayout()
        times.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for title, widget in [("Start", self.start), ("End", self.end)]:
            widget.setDecimals(6)
            widget.setRange(0, 0)
            widget.setSuffix(" s")
            widget.setMinimumWidth(0)
            times.addRow(title, widget)
            widget.valueChanged.connect(self._changed)
        layout.addLayout(times)
        actions = QGridLayout()
        self.play = QPushButton("Play selection")
        self.export = QPushButton("Export selection…")
        self.split = QPushButton("Split at cursor…")
        self.clear = QPushButton("Clear selection")
        for index, (widget, signal) in enumerate(
            [
                (self.play, self.play_requested),
                (self.export, self.export_requested),
                (self.split, self.split_requested),
                (self.clear, self.clear_requested),
            ]
        ):
            actions.addWidget(widget, index // 2, index % 2)
            widget.clicked.connect(lambda checked=False, target=signal: target.emit())
        layout.addLayout(actions)
        self.set_region(0, 0)
        self.setEnabled(False)

    def _changed(self):
        self._enable_selection()
        self.selection_changed.emit(self.start.value(), self.end.value())

    def _enable_selection(self):
        valid = self.end.value() > self.start.value()
        self.play.setEnabled(valid)
        self.export.setEnabled(valid)
        self.clear.setEnabled(valid)

    def set_duration(self, seconds):
        self.start.setMaximum(seconds)
        self.end.setMaximum(seconds)
        self.setEnabled(seconds > 0)

    def set_region(self, start, end):
        for widget, value in [(self.start, start), (self.end, end)]:
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self._enable_selection()
