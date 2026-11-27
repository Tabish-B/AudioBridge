"""Waveform and feature display, with timeline navigation and region selection."""

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .widgets import clock


class AudioPlot(QWidget):
    seek = Signal(float)
    selection_changed = Signal(float, float)
    zoom_requested = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview = None
        self.image = None
        self.spectral_loading = False
        self.selection = None
        self.detail = None
        self.drag_anchor = None
        self.drag_origin = None
        self.dragging = False
        self.view = "Waveform"
        self.position = 0
        self.offset = 0
        self.window_seconds = None
        self.message = "Select a file to see its waveform"
        self.setToolTip(
            "Click to seek. Choose a time window, then scroll left or right through the recording."
        )

    def set_preview(self, preview):
        self.preview = preview
        self.detail = None
        self.image = None
        if preview is not None:
            rgb = preview["spectrum"]
            self.image = QImage(
                rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888
            ).copy()
        self.update()

    def visible_seconds(self):
        if self.preview is None:
            return 0
        return min(self.window_seconds or self.preview["seconds"], self.preview["seconds"])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101612"))
        area = self.rect().adjusted(48 if self.view != "Waveform" else 12, 12, -12, -26)
        painter.setPen(QColor("#223427"))
        for i in range(1, 8):
            x = area.left() + area.width() * i / 8
            painter.drawLine(QLineF(x, area.top(), x, area.bottom()))
        if self.preview is None:
            painter.setPen(QColor("#94a29c"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        duration = self.preview["seconds"]
        span = max(0.001, self.visible_seconds())
        start = min(self.offset, max(0, duration - span))
        if self.view != "Waveform" and self.spectral_loading:
            painter.setPen(QColor("#94a29c"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Computing " + self.view.lower() + "…"
            )
            return
        if self.view != "Waveform":
            source = QRectF(
                start / duration * self.image.width(),
                0,
                span / duration * self.image.width(),
                self.image.height(),
            )
            painter.drawImage(QRectF(area), self.image, source)
            painter.setPen(QColor("#94a29c"))
            ticks = self.preview.get(
                "frequency_ticks", [0, self.preview["rate"] / 4, self.preview["rate"] / 2]
            )
            for fraction, value in zip((0, 0.5, 1), ticks):
                if self.view == "MFCC":
                    text = f"C{value:g}"
                else:
                    text = f"{value / 1000:.1f}k" if value >= 1000 else f"{value:.0f}"
                painter.drawText(3, int(area.bottom() - fraction * (area.height() - 12)), text)
        else:
            low, high = self.preview["low"], self.preview["high"]
            channel_count = low.shape[0] if low.ndim == 2 else 1
            if low.ndim == 1:
                low, high = low[None, :], high[None, :]
            wave_start, wave_duration = 0, duration
            if (
                channel_count == 1
                and self.detail
                and self.detail["start"] <= start + 0.0001
                and self.detail["start"] + self.detail["seconds"] >= start + span - 0.001
            ):
                low, high = self.detail["low"][None, :], self.detail["high"][None, :]
                wave_start, wave_duration = self.detail["start"], self.detail["seconds"]
            bin_count = low.shape[-1]
            first = max(0, int((start - wave_start) / wave_duration * bin_count))
            last = max(
                first + 1,
                int(np.ceil((start + span - wave_start) / wave_duration * bin_count)),
            )
            low, high = low[:, first:last], high[:, first:last]
            for channel in range(channel_count):
                channel_low, channel_high = low[channel], high[channel]
                step = max(1, int(np.ceil(len(channel_low) / max(1, area.width()))))
                padding = (-len(channel_low)) % step
                channel_low = (
                    np.pad(channel_low, (0, padding), mode="edge").reshape(-1, step).min(axis=1)
                )
                channel_high = (
                    np.pad(channel_high, (0, padding), mode="edge").reshape(-1, step).max(axis=1)
                )
                lane_height = area.height() / channel_count
                lane = QRectF(
                    area.left(), area.top() + channel * lane_height, area.width(), lane_height
                )
                middle, scale = lane.center().y(), lane.height() / 2
                painter.setPen(QPen(QColor("#b8f59a" if channel == 0 else "#79b5c5"), 1))
                lines = [
                    QLineF(
                        area.left() + i * area.width() / max(1, len(channel_low) - 1),
                        middle - float(lo) * scale,
                        area.left() + i * area.width() / max(1, len(channel_low) - 1),
                        middle - float(hi) * scale,
                    )
                    for i, (lo, hi) in enumerate(zip(channel_low, channel_high))
                ]
                if np.array_equal(channel_low, channel_high):
                    painter.drawPolyline(
                        QPolygonF([QPointF(line.x1(), line.y1()) for line in lines])
                    )
                else:
                    painter.drawLines(lines)
                if channel_count == 2:
                    painter.setPen(QPen(QColor("#34473b"), 1, Qt.PenStyle.DashLine))
                    painter.drawLine(
                        QLineF(lane.left(), lane.bottom(), lane.right(), lane.bottom())
                    )
        if self.selection:
            selected_start, selected_end = self.selection
            left = area.left() + (max(start, selected_start) - start) / span * area.width()
            right = area.left() + (min(start + span, selected_end) - start) / span * area.width()
            if right > left:
                painter.fillRect(
                    QRectF(left, area.top(), right - left, area.height()), QColor(184, 245, 154, 55)
                )
                painter.setPen(QPen(QColor("#b8f59a"), 2))
                for x in (left, right):
                    painter.drawLine(QLineF(x, area.top(), x, area.bottom()))
        current = self.position / 1000
        if start <= current <= start + span:
            x = area.left() + (current - start) / span * area.width()
            painter.setPen(QPen(QColor("#eff4ef"), 1))
            painter.drawLine(QLineF(x, area.top(), x, area.bottom()))
        painter.setPen(QColor("#94a29c"))
        painter.drawText(area.left(), self.height() - 7, clock(start * 1000))
        end = clock((start + span) * 1000)
        painter.drawText(
            self.width() - painter.fontMetrics().horizontalAdvance(end) - 12, self.height() - 7, end
        )

    def _time_at(self, x):
        left = 48 if self.view != "Waveform" else 12
        fraction = max(0, min(1, (x - left) / max(1, self.width() - left - 12)))
        return self.offset + fraction * self.visible_seconds()

    def mousePressEvent(self, event):
        if self.preview and event.button() == Qt.MouseButton.LeftButton:
            self.drag_anchor = self._time_at(event.position().x())
            self.drag_origin = event.position().x()
            self.dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_anchor is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if abs(event.position().x() - self.drag_origin) >= 4:
                self.dragging = True
            if self.dragging:
                self.selection = tuple(
                    sorted((self.drag_anchor, self._time_at(event.position().x())))
                )
                self.selection_changed.emit(*self.selection)
                self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_anchor is not None and event.button() == Qt.MouseButton.LeftButton:
            if not self.dragging:
                self.seek.emit(self._time_at(event.position().x()) * 1000)
            else:
                self.selection = tuple(
                    sorted((self.drag_anchor, self._time_at(event.position().x())))
                )
                self.selection_changed.emit(*self.selection)
                self.update()
            self.drag_anchor = None
            event.accept()

    def wheelEvent(self, event):
        if self.preview and event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            self.zoom_requested.emit(
                0.5 if event.angleDelta().y() > 0 else 2, self._time_at(event.position().x())
            )
            event.accept()
        else:
            event.ignore()
