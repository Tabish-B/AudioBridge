"""Small shared widgets for the desktop workspace."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, name=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(callback)
    return widget


def card(name="card"):
    widget = QFrame()
    widget.setObjectName(name)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(12)
    return widget, layout


def clock(milliseconds):
    seconds = max(0, int(milliseconds / 1000))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


class FileQueue(QListWidget):
    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMinimumHeight(60)
        self.setMaximumHeight(100)

    def add_file(self, path):
        item = QListWidgetItem()
        item.setToolTip(str(path))
        item.setData(Qt.ItemDataRole.AccessibleTextRole, path.name)
        self.addItem(item)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 10, 10, 10)
        name = label(path.name)
        name.setToolTip(str(path))
        name.setMinimumWidth(0)
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(name, 1)
        fmt = label(path.suffix[1:].upper(), "muted")
        fmt.setFixedWidth(55)
        layout.addWidget(fmt)
        state = label("Ready", "state")
        state.setFixedWidth(64)
        layout.addWidget(state)
        item.setSizeHint(row.sizeHint())
        self.setItemWidget(item, row)

    def set_status(self, index, text):
        self.itemWidget(self.item(index)).findChild(QLabel, "state").setText(text)

    def status(self, index):
        return self.itemWidget(self.item(index)).findChild(QLabel, "state").text()
