"""Show the supplied splash art while the workspace starts."""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from version import __version__

from .resources import ASSET_DIR


class StartupSplash(QSplashScreen):
    def __init__(self):
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry()
        width = min(520, max(240, available.width() - 48))
        height = min(320, max(200, available.height() - 48))
        ratio = screen.devicePixelRatio()
        pixels = QSize(round(width * ratio), round(height * ratio))
        artwork = QPixmap(str(ASSET_DIR / "splash.png")).scaled(
            pixels,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        artwork = artwork.copy(
            (artwork.width() - pixels.width()) // 2,
            (artwork.height() - pixels.height()) // 2,
            pixels.width(),
            pixels.height(),
        )
        artwork.setDevicePixelRatio(ratio)
        super().__init__(artwork, Qt.WindowType.WindowStaysOnTopHint)

    def drawContents(self, painter: QPainter):
        painter.setPen(QColor("#183019"))
        font = painter.font()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRect(0, self.height() - 73, self.width(), 30),
            Qt.AlignmentFlag.AlignCenter,
            "AudioBridge",
        )
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QRect(0, self.height() - 36, self.width(), 24),
            Qt.AlignmentFlag.AlignCenter,
            f"v{__version__} · Starting your workspace…",
        )
