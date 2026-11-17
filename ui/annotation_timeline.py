"""Compact, time-aligned tier overview for manual annotations."""

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .widgets import clock


class AnnotationTimeline(QWidget):
    annotation_activated = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(100)
        self.setMouseTracking(True)
        self.rows = []
        self.tiers = []
        self.duration = 0.0
        self.source = None
        self.selected = None
        self._lane_geometry = None

    def sizeHint(self):
        return QSize(700, max(100, 54 + len(self.tiers) * 36))

    def set_data(self, annotations, tiers, source, duration, selected=None):
        self.source = Path(source).resolve() if source else None
        self.duration = max(0.0, float(duration or 0))
        self.tiers = list(tiers)
        self.selected = selected
        self.rows = [
            (index, row)
            for index, row in enumerate(annotations)
            if self.source and Path(row["file"]).resolve() == self.source
        ]
        self.setMinimumHeight(max(100, 54 + len(self.tiers) * 36))
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101612"))
        left, right, top, bottom = 118, 12, 30, 20
        lane_area = QRectF(
            left, top, max(1, self.width() - left - right), max(1, self.height() - top - bottom)
        )
        lane_height = lane_area.height() / max(1, len(self.tiers))
        self._lane_geometry = (lane_area, lane_height)
        painter.setPen(QColor("#94a29c"))
        painter.drawText(
            QRectF(8, 4, left - 12, 20), Qt.AlignmentFlag.AlignVCenter, "Annotation tiers"
        )
        if self.duration <= 0 or not self.tiers:
            painter.drawText(
                lane_area,
                Qt.AlignmentFlag.AlignCenter,
                "Choose a recording to see its annotated timeline",
            )
            return

        painter.setPen(QPen(QColor("#27372c"), 1))
        for fraction in (0, 0.25, 0.5, 0.75, 1):
            x = lane_area.left() + fraction * lane_area.width()
            painter.drawLine(int(x), int(lane_area.top()), int(x), int(lane_area.bottom()))
            painter.setPen(QColor("#94a29c"))
            painter.drawText(
                QRectF(x - 38, lane_area.bottom() + 2, 76, 16),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                clock(self.duration * fraction * 1000),
            )
            painter.setPen(QPen(QColor("#27372c"), 1))

        palette = ["#b8f59a", "#91c9e8", "#e9b76f", "#d5a6ed", "#7dd6c3"]
        for lane, tier in enumerate(self.tiers):
            y = lane_area.top() + lane * lane_height
            painter.setPen(QColor("#29382e"))
            painter.drawLine(int(lane_area.left()), int(y), int(lane_area.right()), int(y))
            painter.setPen(QColor("#c5cec7"))
            painter.drawText(
                QRectF(8, y, left - 16, lane_height),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                tier,
            )
            for index, row in self.rows:
                if row["tier"] != tier:
                    continue
                start = max(0.0, row["start_seconds"])
                end = min(self.duration, row["end_seconds"])
                if end <= start:
                    continue
                x1 = lane_area.left() + start / self.duration * lane_area.width()
                x2 = lane_area.left() + end / self.duration * lane_area.width()
                rect = QRectF(x1, y + 5, max(2, x2 - x1), max(8, lane_height - 10))
                color = QColor(palette[lane % len(palette)])
                if index == self.selected:
                    color = QColor("#e6f8de")
                painter.setPen(QPen(color.lighter(115), 1))
                painter.setBrush(color)
                painter.drawRoundedRect(rect, 4, 4)
                if rect.width() > 42:
                    painter.setPen(QColor("#172118"))
                    painter.drawText(
                        rect.adjusted(5, 0, -4, 0),
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        row["label"],
                    )
        painter.setPen(QColor("#29382e"))
        painter.drawLine(
            int(lane_area.left()),
            int(lane_area.bottom()),
            int(lane_area.right()),
            int(lane_area.bottom()),
        )

    def mousePressEvent(self, event):
        if (
            not self._lane_geometry
            or self.duration <= 0
            or event.button() != Qt.MouseButton.LeftButton
        ):
            return
        area, lane_height = self._lane_geometry
        point = event.position()
        if not area.contains(point):
            return
        lane = min(len(self.tiers) - 1, int((point.y() - area.top()) / lane_height))
        tier = self.tiers[lane]
        seconds = (point.x() - area.left()) / area.width() * self.duration
        candidates = [
            index
            for index, row in self.rows
            if row["tier"] == tier and row["start_seconds"] <= seconds <= row["end_seconds"]
        ]
        if candidates:
            self.annotation_activated.emit(candidates[-1])
