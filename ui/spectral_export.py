"""Render a full-recording spectral raster with its time and value axes."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from .widgets import clock


def render_spectral_image(preview, source_name, mode):
    rgb = preview["spectrum"]
    raster = QImage(
        rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888
    ).copy()
    left, top, right, bottom = 116, 44, 24, 104
    image = QImage(
        raster.width() + left + right,
        raster.height() + top + bottom,
        QImage.Format.Format_ARGB32,
    )
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    area = QRectF(left, top, raster.width(), raster.height())
    painter.setPen(QColor("#18231b"))
    title_font = QFont(painter.font())
    title_font.setBold(True)
    title_font.setPointSize(12)
    painter.setFont(title_font)
    painter.drawText(
        QRectF(left, 8, raster.width(), 28),
        Qt.AlignmentFlag.AlignVCenter,
        f"{source_name} · {mode}",
    )
    painter.setFont(QFont(painter.font().family(), 9))
    painter.drawImage(area, raster)
    painter.setPen(QPen(QColor("#26352a"), 1))
    painter.drawRect(area)

    duration = preview["seconds"]
    for fraction in (0, 0.5, 1):
        x = area.left() + fraction * area.width()
        painter.drawLine(int(x), int(area.bottom()), int(x), int(area.bottom() + 5))
        label = clock(duration * fraction * 1000)
        painter.drawText(
            QRectF(x - 48, area.bottom() + 8, 96, 18),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            label,
        )
    painter.drawText(
        QRectF(area.left(), area.bottom() + 27, area.width(), 18),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "Time",
    )

    ticks = preview.get("frequency_ticks", (0, 0, 0))
    for fraction, value in zip((1, 0.5, 0), ticks):
        y = area.top() + fraction * area.height()
        painter.drawLine(int(area.left() - 5), int(y), int(area.left()), int(y))
        if mode == "MFCC":
            tick = f"C{value:g}"
        else:
            tick = f"{value / 1000:g} kHz" if value >= 1000 else f"{value:g} Hz"
        painter.drawText(
            QRectF(4, y - 10, left - 14, 20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            tick,
        )
    painter.drawText(
        QRectF(4, 25, left - 14, 18),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        "Frequency" if mode != "MFCC" else "Coefficient",
    )
    painter.setPen(QColor("#46554a"))
    painter.drawText(
        QRectF(left, area.bottom() + 51, raster.width(), bottom - 54),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
        preview.get("spectral_legend", ""),
    )
    painter.end()

    settings = preview["spectral_settings"]
    image.setText("Source file", source_name)
    image.setText("View", mode)
    image.setText("Duration (s)", f"{duration:.6f}")
    image.setText("Legend", preview.get("spectral_legend", ""))
    image.setText("Sample rate (Hz)", str(preview["rate"]))
    image.setText("FFT size", str(settings.fft_size))
    image.setText("Hop length", str(settings.hop_length))
    image.setText("Window", settings.window)
    image.setText("Spectral settings", str(settings))
    return image
