"""The conversion workspace, with background checks and a built-in player."""

import csv
import json
import os
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if sys.platform == 'darwin':
    os.environ.setdefault('QT_MEDIA_BACKEND', 'darwin')

import numpy as np
from PySide6.QtCore import QObject, Qt, QUrl, Signal, QLineF, QRectF
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QShortcut, QKeySequence, QFontDatabase
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget, QBoxLayout, QStackedWidget, QLineEdit, QTextEdit, QScrollBar, QCheckBox,
)

from converter import AudioAnalyzer, AudioConverter
from converter.preview import build_preview
from converter.formats import FORMATS
from version import __version__

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
ASSET_DIR = ROOT / 'assets'


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


def card(name='card'):
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
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


class Events(QObject):
    finished = Signal(str, object, object)
    progress = Signal(int, int, object)


class AudioPlot(QWidget):
    seek = Signal(float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview = None
        self.image = None
        self.view = 'Waveform'
        self.position = 0
        self.offset = 0
        self.window_seconds = None
        self.message = 'Select a file to see its waveform'
        self.setToolTip('Click to seek. Choose a time window, then scroll left or right through the recording.')

    def set_preview(self, preview):
        self.preview = preview
        self.image = None
        if preview is not None:
            rgb = preview['spectrum']
            self.image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.update()

    def visible_seconds(self):
        if self.preview is None:
            return 0
        return min(self.window_seconds or self.preview['seconds'], self.preview['seconds'])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101612'))
        area = self.rect().adjusted(48 if self.view == 'Spectrogram' else 12, 12, -12, -26)
        painter.setPen(QColor('#223427'))
        for i in range(1, 8):
            x = area.left() + area.width() * i / 8
            painter.drawLine(QLineF(x, area.top(), x, area.bottom()))
        if self.preview is None:
            painter.setPen(QColor('#94a29c'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        duration = self.preview['seconds']
        span = max(.001, self.visible_seconds())
        start = min(self.offset, max(0, duration - span))
        if self.view == 'Spectrogram':
            source = QRectF(start / duration * self.image.width(), 0,
                            span / duration * self.image.width(), self.image.height())
            painter.drawImage(QRectF(area), self.image, source)
            painter.setPen(QColor('#94a29c'))
            for fraction in (0, .5, 1):
                frequency = self.preview['rate'] / 2 * fraction
                text = f'{frequency / 1000:g}k' if frequency >= 1000 else f'{frequency:g}'
                painter.drawText(3, int(area.bottom() - fraction * (area.height() - 12)), text)
        else:
            low, high = self.preview['low'], self.preview['high']
            first = max(0, int(start / duration * len(low)))
            last = max(first + 1, int(np.ceil((start + span) / duration * len(low))))
            low, high = low[first:last], high[first:last]
            # Bound painting work even when the entire recording is visible.
            step = max(1, int(np.ceil(len(low) / max(1, area.width()))))
            padding = (-len(low)) % step
            low = np.pad(low, (0, padding), mode='edge').reshape(-1, step).min(axis=1)
            high = np.pad(high, (0, padding), mode='edge').reshape(-1, step).max(axis=1)
            middle, scale = area.center().y(), area.height() / 2
            painter.setPen(QPen(QColor('#b8f59a'), 1))
            lines = [QLineF(area.left() + i * area.width() / max(1, len(low) - 1), middle - float(lo) * scale,
                            area.left() + i * area.width() / max(1, len(low) - 1), middle - float(hi) * scale)
                     for i, (lo, hi) in enumerate(zip(low, high))]
            painter.drawLines(lines)
        current = self.position / 1000
        if start <= current <= start + span:
            x = area.left() + (current - start) / span * area.width()
            painter.setPen(QPen(QColor('#eff4ef'), 1))
            painter.drawLine(QLineF(x, area.top(), x, area.bottom()))
        painter.setPen(QColor('#94a29c'))
        painter.drawText(area.left(), self.height() - 7, clock(start * 1000))
        end = clock((start + span) * 1000)
        painter.drawText(self.width() - painter.fontMetrics().horizontalAdvance(end) - 12, self.height() - 7, end)

    def mousePressEvent(self, event):
        if self.preview and event.button() == Qt.MouseButton.LeftButton:
            left = 48 if self.view == 'Spectrogram' else 12
            fraction = max(0, min(1, (event.position().x() - left) / max(1, self.width() - left - 12)))
            self.seek.emit((self.offset + fraction * self.visible_seconds()) * 1000)


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
        fmt = label(path.suffix[1:].upper(), 'muted')
        fmt.setFixedWidth(55)
        layout.addWidget(fmt)
        state = label('Ready', 'state')
        state.setFixedWidth(64)
        layout.addWidget(state)
        item.setSizeHint(row.sizeHint())
        self.setItemWidget(item, row)

    def set_status(self, index, text):
        self.itemWidget(self.item(index)).findChild(QLabel, 'state').setText(text)

    def status(self, index):
        return self.itemWidget(self.item(index)).findChild(QLabel, 'state').text()


class AudioBridgeGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'AudioBridge {__version__} · Conversion studio')
        self.setWindowIcon(QIcon(str(ASSET_DIR / 'audiobridge.png')))
        self.resize(1400, 950)
        self.setMinimumSize(420, 500)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
        self.setStyleSheet((ROOT / 'ui' / 'theme.qss').read_text().replace('@UI_FONT@', font).replace('@ASSET_DIR@', ASSET_DIR.as_posix()))
        self.converter = AudioConverter()
        self.analyzer = AudioAnalyzer()
        self.files = []
        self.selected_file = None
        self.report = None
        self.audit_results = []
        self.annotations = []
        self.segment_start = None
        self.audit_busy = False
        self.busy = False
        self.output_dir = Path.home() / 'Downloads' / 'AudioBridge'
        self.cache = OrderedDict()
        self.pending = set()
        self.analysis_pending = set()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='audio-check')
        self.conversion_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='audio-export')
        self.events = Events(self)
        self.events.finished.connect(self._finished)
        self.events.progress.connect(self._progress)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.player.setAudioOutput(self.audio)
        self._build_ui()
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.errorOccurred.connect(self._player_error)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.shortcuts = [QShortcut(QKeySequence('Space'), self), QShortcut(QKeySequence('Delete'), self), QShortcut(QKeySequence('Backspace'), self)]
        self.shortcuts[0].activated.connect(self._toggle_play)
        for shortcut in self.shortcuts[1:]:
            shortcut.activated.connect(self._remove_file)
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self.setAcceptDrops(True)

    def _focus_changed(self, old, current):
        editing = isinstance(current, (QLineEdit, QTextEdit, QComboBox))
        for shortcut in self.shortcuts:
            shortcut.setEnabled(not editing)

    def _build_ui(self):
        host = QWidget()
        host.setObjectName('workspace')
        self.setCentralWidget(host)
        shell = QHBoxLayout(host)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(205)
        nav = QVBoxLayout(self.sidebar)
        nav.setContentsMargins(18, 26, 18, 22)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSET_DIR / 'audiobridge.png')).scaled(33, 33, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand.addWidget(logo)
        brand.addWidget(label('AudioBridge', 'brand'))
        nav.addLayout(brand)
        nav.addWidget(label(f'VERSION {__version__}', 'eyebrow'))
        nav.addSpacing(24)
        self.nav_buttons = []
        for index, title in enumerate(['Conversion studio', 'Dataset audit', 'Segment annotations']):
            item = button(title, lambda checked=False, page=index: self._set_page(page), 'nav')
            item.setCheckable(True)
            nav.addWidget(item)
            self.nav_buttons.append(item)
        nav.addStretch()
        privacy = label('Your audio. Your device.\n\nProcessed locally.\nOriginal files stay intact.', 'muted')
        privacy.setWordWrap(True)
        nav.addWidget(privacy)
        shell.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        studio_scroll = QScrollArea()
        studio_scroll.setWidgetResizable(True)
        self.studio_content = QWidget()
        self.studio_content.setObjectName('workspace')
        workspace = QVBoxLayout(self.studio_content)
        workspace.setContentsMargins(22, 22, 22, 22)
        workspace.setSpacing(14)
        studio_scroll.setWidget(self.studio_content)
        self.pages.addWidget(studio_scroll)
        self.page_picker = QComboBox()
        self.page_picker.addItems(['Conversion studio', 'Dataset audit', 'Segment annotations'])
        self.page_picker.currentIndexChanged.connect(self._set_page)
        # The compact page picker stays outside the scrolling pages.
        mobile_host = QWidget()
        mobile_layout = QVBoxLayout(mobile_host)
        mobile_layout.setContentsMargins(0, 0, 0, 0)
        mobile_layout.addWidget(self.page_picker)
        mobile_layout.addWidget(self.pages, 1)
        shell.addWidget(mobile_host, 1)
        top = QHBoxLayout()
        top.addWidget(label(f'AudioBridge {__version__}', 'muted'))
        top.addStretch()
        top.addWidget(label('●  Local engine ready', 'badge'))
        workspace.addLayout(top)
        workspace.addWidget(label('Conversion studio', 'title'))
        subtitle = label('Convert recordings, listen back, and inspect the signal.', 'muted')
        subtitle.setWordWrap(True)
        workspace.addWidget(subtitle)
        self.body = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.body.setSpacing(18)
        workspace.addLayout(self.body, 1)
        center_host = QWidget()
        center = QVBoxLayout(center_host)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(14)
        self.body.addWidget(center_host, 1)
        upload, box = card('upload')
        self.upload_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        copy = QVBoxLayout()
        copy.addWidget(label('Bring your audio in', 'heading'))
        note = label('Drop audio or video files here, or browse to get started.', 'muted')
        note.setWordWrap(True)
        copy.addWidget(note)
        self.upload_row.addLayout(copy, 1)
        actions = QVBoxLayout()
        actions.addWidget(button('+   Select files', self._upload_files, 'primary'))
        actions.addWidget(button('Select a folder', self._upload_folder, 'quiet'))
        self.upload_row.addLayout(actions)
        box.addLayout(self.upload_row)
        center.addWidget(upload)
        queue_card, box = card()
        queue_card.setFixedHeight(166)
        self.queue_label = label('Files in queue   ·   0', 'heading')
        self.queue_header = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.queue_header.addWidget(self.queue_label, 1)
        queue_actions = QHBoxLayout()
        self.remove_button = button('Remove selected', self._remove_file, 'quiet')
        self.clear_button = button('Clear all', self._clear_files, 'quiet')
        queue_actions.addWidget(self.remove_button)
        queue_actions.addWidget(self.clear_button)
        queue_actions.addStretch()
        self.queue_header.addLayout(queue_actions)
        box.addLayout(self.queue_header)
        self.table = FileQueue()
        self.table.setMinimumHeight(60)
        self.table.setMaximumHeight(84)
        self.table.itemSelectionChanged.connect(self._on_select)
        box.addWidget(self.table)
        center.addWidget(queue_card)
        preview, box = card()
        box.setSpacing(8)
        self.preview_header = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.preview_header.addWidget(label('Audio preview', 'heading'), 1)
        box.addLayout(self.preview_header)
        self.filename = label('No file selected', 'muted')
        self.filename.setWordWrap(True)
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        box.addWidget(self.filename)
        actions = QHBoxLayout()
        self.analyze_button = button('Analyze file', self._analyze)
        self.analyze_button.setEnabled(False)
        self.export_button = button('Export JSON', self._export_report, 'quiet')
        self.export_button.setEnabled(False)
        actions.addWidget(self.analyze_button)
        actions.addWidget(self.export_button)
        actions.addStretch()
        self.preview_header.addLayout(actions)
        switch = QHBoxLayout()
        self.view = QComboBox()
        self.view.addItems(['Waveform', 'Spectrogram'])
        self.view.currentTextChanged.connect(self._change_view)
        switch.addWidget(self.view)
        self.zoom = QComboBox()
        self.zoom.addItems(['Full recording', '30 s window', '2 min window', '10 min window'])
        self.zoom.currentIndexChanged.connect(self._set_zoom)
        switch.addWidget(self.zoom)
        switch.addStretch()
        box.addLayout(switch)
        self.preview_note = label('Full recording · scroll horizontally when zoomed in', 'muted')
        self.preview_note.setWordWrap(True)
        box.addWidget(self.preview_note)
        self.plot = AudioPlot()
        self.plot.setMinimumHeight(130)
        self.plot.seek.connect(lambda value: self.player.setPosition(int(value)))
        box.addWidget(self.plot, 1)
        self.timeline_scroll = QScrollBar(Qt.Orientation.Horizontal)
        self.timeline_scroll.setRange(0, 0)
        self.timeline_scroll.hide()
        self.timeline_scroll.setToolTip('Scroll through the visible time window')
        self.timeline_scroll.valueChanged.connect(self._scroll_plot)
        box.addWidget(self.timeline_scroll)
        self.follow = QCheckBox('Follow playback when zoomed in')
        self.follow.setChecked(True)
        self.follow.hide()
        box.addWidget(self.follow)
        self.spectrum_legend = label('Frequency: 0 Hz → source Nyquist · Color: −110 to −20 dBFS/Hz (peak per time bin)', 'muted')
        self.spectrum_legend.setWordWrap(True)
        self.spectrum_legend.hide()
        box.addWidget(self.spectrum_legend)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.player.setPosition)
        box.addWidget(self.seek_slider)
        self.transport = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        playback = QHBoxLayout()
        self.play_button = button('', self._toggle_play, 'primary')
        self.play_button.setIcon(QIcon(str(ASSET_DIR / 'play.svg')))
        self.play_button.setFixedWidth(40)
        self.play_button.setEnabled(False)
        self.play_button.setToolTip('Play / pause (Space)')
        playback.addWidget(self.play_button)
        restart = button('', lambda: self.player.setPosition(0), 'quiet')
        restart.setIcon(QIcon(str(ASSET_DIR / 'restart.svg')))
        restart.setToolTip('Restart recording')
        playback.addWidget(restart)
        self.time_label = label('00:00 / 00:00', 'muted')
        playback.addWidget(self.time_label)
        playback.addStretch()
        self.transport.addLayout(playback, 1)
        levels = QHBoxLayout()
        self.speed = QComboBox()
        self.speed.addItems(['0.75×', '1×', '1.25×', '1.5×', '2×'])
        self.speed.setCurrentIndex(1)
        self.speed.setFixedWidth(80)
        self.speed.currentIndexChanged.connect(lambda index: self.player.setPlaybackRate([.75, 1, 1.25, 1.5, 2][index]))
        levels.addWidget(self.speed)
        levels.addWidget(label('Vol', 'muted'))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(65)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        levels.addWidget(self.volume)
        levels.addStretch()
        self.transport.addLayout(levels)
        box.addLayout(self.transport)
        self.metrics = label('Run audio checks to inspect levels, clipping, and quiet sections.', 'muted')
        self.metrics.setWordWrap(True)
        box.addWidget(self.metrics)
        center.addWidget(preview, 1)
        self.settings_card, settings = card()
        self.settings_card.setMinimumWidth(250)
        self.settings_card.setMaximumWidth(290)
        self.body.addWidget(self.settings_card)
        settings.addWidget(label('Export settings', 'heading'))
        self.output_format = self._combo(settings, 'Output format', list(FORMATS))
        self.format_note = label(FORMATS['WAV'][1], 'muted')
        self.format_note.setWordWrap(True)
        settings.addWidget(self.format_note)
        self.preset = self._combo(settings, 'Processing preset (optional)', ['Keep source settings', 'ASR input · 16 kHz mono', 'Archive · 48 kHz / 24-bit', 'Custom'])
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.rate = self._combo(settings, 'Sample rate', ['Keep original', '16000 Hz', '22050 Hz', '44100 Hz', '48000 Hz'])
        self.depth = self._combo(settings, 'Bit depth · lossless formats', ['16-bit PCM', '24-bit PCM'])
        self.channels = self._combo(settings, 'Channels', ['Mono', 'Keep original'], 1)
        self.settings_note = label('Keep source settings preserves sample rate and channels. PCM depth is chosen separately. Lossy formats are re-encoded.', 'muted')
        self.settings_note.setWordWrap(True)
        settings.addWidget(self.settings_note)
        settings.addWidget(label('Save converted files to'))
        self.output_label = label(self._display_path(self.output_dir), 'muted')
        self.output_label.setWordWrap(True)
        settings.addWidget(self.output_label)
        settings.addWidget(button('Change folder', self._select_output_dir))
        note = label('Original files are always preserved.', 'muted')
        note.setWordWrap(True)
        settings.addWidget(note)
        settings.addStretch()
        footer, layout = card('footer')
        self.status = label('●  Ready when you are', 'heading')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.footer_actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.output_summary = label('', 'muted')
        self.output_summary.setWordWrap(True)
        self.footer_actions.addWidget(self.output_summary, 1)
        self.convert_button = button('Convert files   →', self._start_conversion, 'primary')
        self.footer_actions.addWidget(self.convert_button)
        layout.addLayout(self.footer_actions)
        workspace.addWidget(footer)
        for combo in (self.rate, self.depth, self.channels):
            combo.currentTextChanged.connect(self._manual_settings)
        self.output_format.currentTextChanged.connect(self._format_changed)
        self._build_research_pages()
        self._update_summary()
        self._set_page(0)
        self._apply_responsive()

    def _set_page(self, index):
        self.pages.setCurrentIndex(index)
        self.page_picker.blockSignals(True)
        self.page_picker.setCurrentIndex(index)
        self.page_picker.blockSignals(False)
        for i, item in enumerate(self.nav_buttons):
            item.setChecked(i == index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'body'):
            self._apply_responsive()

    def _apply_responsive(self):
        narrow = self.width() < 1100
        compact = self.width() < 650
        self.sidebar.setVisible(self.width() >= 950)
        self.page_picker.setVisible(self.width() < 950)
        self.body.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        self.settings_card.setMaximumWidth(16777215 if narrow else 290)
        self.settings_card.setMinimumWidth(0 if narrow else 250)
        direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        for layout in (self.upload_row, self.transport, self.footer_actions, self.queue_header, self.preview_header):
            layout.setDirection(direction)

    def _research_page(self, title, description):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName('workspace')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        layout.addWidget(label(title, 'title'))
        note = label(description, 'muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        return layout

    def _build_research_pages(self):
        audit = self._research_page('Dataset audit', 'Check the files in your conversion queue together. Flags describe signal levels; they are not speech detection or an ASR quality score.')
        self.audit_status = label('Add recordings in Conversion studio, then scan the queue.', 'muted')
        self.audit_status.setWordWrap(True)
        audit.addWidget(self.audit_status)
        self.audit_button = button('Scan queued recordings', self._audit, 'primary')
        audit.addWidget(self.audit_button)
        self.audit_export = button('Export audit CSV', self._export_audit)
        self.audit_export.setEnabled(False)
        audit.addWidget(self.audit_export)
        self.audit_text = QTextEdit()
        self.audit_text.setReadOnly(True)
        self.audit_text.setMinimumHeight(240)
        audit.addWidget(self.audit_text, 1)
        annotations = self._research_page('Segment annotations', 'Mark time ranges while listening, label them, and export a CSV for dataset review. These are manual annotations; the original recording is not edited.')
        self.annotation_time = label('Select a recording in Conversion studio.', 'muted')
        self.annotation_time.setWordWrap(True)
        annotations.addWidget(self.annotation_time)
        self.annotation_label = QLineEdit()
        self.annotation_label.setPlaceholderText('Label, e.g. speech, background noise, overlap')
        self.annotation_label.setMaxLength(100)
        annotations.addWidget(self.annotation_label)
        annotations.addWidget(button('Mark start at playhead', self._mark_start))
        annotations.addWidget(button('Mark end and add segment', self._mark_end))
        self.annotation_status = label('Start playback in the studio, then mark the segment here.', 'muted')
        self.annotation_status.setWordWrap(True)
        annotations.addWidget(self.annotation_status)
        self.annotation_list = QListWidget()
        self.annotation_list.setMinimumHeight(180)
        annotations.addWidget(self.annotation_list, 1)
        annotations.addWidget(button('Remove selected annotation', self._remove_annotation, 'quiet'))
        annotations.addWidget(button('Export annotations CSV', self._export_annotations))

    def _audit(self):
        if self.audit_busy:
            return
        if not self.files:
            self.audit_status.setText('Add recordings to the conversion queue first.')
            return
        paths = list(self.files)
        self.audit_busy = True
        self.audit_button.setEnabled(False)
        self.audit_status.setText(f'Scanning {len(paths)} recordings…')
        def scan():
            results = []
            for path in paths:
                result = self.analyzer.analyze(path)
                row = dict(file=str(path), **result)
                flags = []
                if 'error' not in result:
                    if result['clipping_percent'] > .01:
                        flags.append('near full scale > 0.01%')
                    if result['rms_dbfs'] < -35:
                        flags.append('low RMS < -35 dBFS')
                    if result['quiet_percent'] > 75:
                        flags.append('quiet windows > 75%')
                row['flags'] = '; '.join(flags)
                results.append(row)
            return results
        self._submit('audit', None, scan)

    def _finish_audit(self, result):
        self.audit_busy = False
        self.audit_button.setEnabled(True)
        if isinstance(result, dict) and 'error' in result:
            self.audit_status.setText(result['error'])
            return
        self.audit_results = result
        self.audit_export.setEnabled(bool(result))
        failures = sum('error' in row for row in result)
        self.audit_status.setText(f'{len(result)} recordings checked · {failures} could not be read')
        lines = []
        for row in result:
            lines.append(Path(row['file']).name)
            if 'error' in row:
                lines.append('  Could not analyze: ' + row['error'])
            else:
                lines.append(f"  {row['duration']:.2f} s | {row['sample_rate']} Hz | {row['channels']} ch | RMS {row['rms_dbfs']:.1f} dBFS | Peak {row['peak_dbfs']:.1f} dBFS")
                lines.append('  ' + (row['flags'] or 'No level flags at the configured thresholds'))
            lines.append('')
        self.audit_text.setPlainText('\n'.join(lines))

    def _write_csv(self, destination, rows, fields):
        with Path(destination).open('w', newline='', encoding='utf-8') as output:
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)

    def _export_audit(self):
        if not self.audit_results:
            return
        destination, _ = QFileDialog.getSaveFileName(self, 'Save dataset audit', 'dataset_audit.csv', 'CSV (*.csv)')
        if destination:
            try:
                self._write_csv(destination, self.audit_results, ['file', 'duration', 'sample_rate', 'channels', 'rms_dbfs', 'peak_dbfs', 'crest_db', 'clipping_percent', 'quiet_percent', 'flags', 'error'])
                self.audit_status.setText('Dataset audit saved')
            except OSError as exc:
                self.audit_status.setText(str(exc))

    def _mark_start(self):
        if self.selected_file is None:
            self.annotation_status.setText('Select a recording in Conversion studio first.')
            return
        self.segment_start = (self.selected_file, self.player.position() / 1000)
        self.annotation_status.setText(f'Start marked at {self.segment_start[1]:.3f} s. Seek or play to the end of the segment.')

    def _mark_end(self):
        if self.segment_start is None or self.segment_start[0] != self.selected_file:
            self.annotation_status.setText('Mark a start point in the selected recording first.')
            return
        start = self.segment_start[1]
        end = self.player.position() / 1000
        if end <= start:
            self.annotation_status.setText('The end must be after the start point.')
            return
        text = self.annotation_label.text().strip() or 'unlabelled'
        row = dict(file=str(self.selected_file), start_seconds=round(start, 3), end_seconds=round(end, 3), label=text)
        self.annotations.append(row)
        self.annotation_list.addItem(f'{self.selected_file.name}\n{start:.3f}–{end:.3f} s · {text}')
        self.segment_start = None
        self.annotation_status.setText('Segment added. Mark another start to continue.')

    def _remove_annotation(self):
        index = self.annotation_list.currentRow()
        if index >= 0:
            self.annotation_list.takeItem(index)
            self.annotations.pop(index)

    def _export_annotations(self):
        if not self.annotations:
            self.annotation_status.setText('Add a segment before exporting.')
            return
        destination, _ = QFileDialog.getSaveFileName(self, 'Save annotations', 'annotations.csv', 'CSV (*.csv)')
        if destination:
            try:
                self._write_csv(destination, self.annotations, ['file', 'start_seconds', 'end_seconds', 'label'])
                self.annotation_status.setText('Annotations saved')
            except OSError as exc:
                self.annotation_status.setText(str(exc))

    def _combo(self, layout, title, values, index=0):
        layout.addSpacing(4)
        layout.addWidget(label(title))
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentIndex(index)
        layout.addWidget(combo)
        return combo

    def _preset_changed(self, index):
        if index == 3:
            return
        rate, depth, channels = [(0, 0, 1), (1, 0, 0), (4, 1, 1)][index]
        for combo, value in [(self.rate, rate), (self.depth, depth), (self.channels, channels)]:
            combo.blockSignals(True)
            combo.setCurrentIndex(value)
            combo.blockSignals(False)
        self._update_summary()

    def _manual_settings(self):
        self.preset.setCurrentIndex(3)
        self._update_summary()

    def _format_changed(self, value):
        self.format_note.setText(FORMATS[value][1])
        self.depth.setEnabled(value in ('WAV', 'FLAC', 'AIFF', 'Keep original'))
        self._update_summary()

    def _update_summary(self):
        self.output_summary.setText(f'{self.output_format.currentText()}  /  {self.rate.currentText()}  /  {self.channels.currentText()}')

    def _upload_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Select audio or video files')
        self.add_files(paths)

    def _upload_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Select a folder of recordings')
        if path:
            self.add_files(sorted(p for p in Path(path).iterdir() if p.is_file() and self.converter.inspector.is_supported(p)))

    def add_files(self, paths):
        if self.busy:
            self.status.setText('Finish this conversion before changing the queue')
            return
        rejected = 0
        for path in paths:
            path = Path(path).resolve()
            if not path.is_file() or not self.converter.inspector.is_supported(path):
                rejected += 1
                continue
            if path in self.files:
                continue
            self.files.append(path)
            self.table.add_file(path)
        self.queue_label.setText(f'Files in queue   ·   {len(self.files)}')
        if self.files and self.table.currentRow() < 0:
            self.table.setCurrentRow(0)
        if rejected:
            self.status.setText(f'Skipped {rejected} unsupported or missing files')

    def _reset_selection(self):
        self.segment_start = None
        self.player.stop()
        self.player.setSource(QUrl())
        self.selected_file = self.report = None
        self.filename.setText('No file selected')
        self.plot.message = 'Select a file to see its waveform'
        self.plot.set_preview(None)
        self.plot.offset = 0
        self.timeline_scroll.setRange(0, 0)
        self.timeline_scroll.hide()
        self.follow.hide()
        self.metrics.setText('Run audio checks to inspect levels, clipping, and quiet sections.')
        self.play_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.seek_slider.setEnabled(False)

    def _clear_files(self):
        if self.busy:
            return
        self._reset_selection()
        self.table.blockSignals(True)
        self.table.clear()
        self.table.blockSignals(False)
        self.files.clear()
        self.cache.clear()
        self.queue_label.setText('Files in queue   ·   0')
        self.status.setText('●  Ready when you are')

    def _remove_file(self):
        row = self.table.currentRow()
        if self.busy or row < 0 or not self.table.hasFocus():
            # Buttons can remove the selected row too; ignore text-entry shortcuts.
            if self.busy or row < 0 or isinstance(self.focusWidget(), QComboBox):
                return
        self._reset_selection()
        self.table.blockSignals(True)
        self.table.takeItem(row)
        removed = self.files.pop(row)
        self.cache.pop(removed, None)
        self.table.blockSignals(False)
        self.queue_label.setText(f'Files in queue   ·   {len(self.files)}')
        if self.files:
            self.table.setCurrentRow(min(row, len(self.files) - 1))
            self._on_select()

    def _on_select(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.files):
            return
        path = self.files[row]
        if path == self.selected_file:
            return
        self._reset_selection()
        self.selected_file = path
        self.filename.setText(path.name)
        self.filename.setToolTip(str(path))
        self.analyze_button.setEnabled(path not in self.analysis_pending)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.plot.position = 0
        if path in self.cache:
            self.cache.move_to_end(path)
            self._show_preview(self.cache[path])
        else:
            self.plot.message = 'Loading preview…'
            self.plot.update()
            if path not in self.pending:
                self.pending.add(path)
                self._submit('preview', path, lambda: build_preview(path))

    def _submit(self, kind, path, operation, pool=None):
        future = (pool or self.pool).submit(operation)
        def done(completed):
            if completed.cancelled():
                return
            try:
                result = completed.result()
            except Exception as exc:
                result = {'error': str(exc)}
            self.events.finished.emit(kind, path, result)
        future.add_done_callback(done)

    def _finished(self, kind, path, result):
        if kind == 'audit':
            self._finish_audit(result)
            return
        if kind == 'conversion':
            self.busy = False
            self.convert_button.setEnabled(True)
            self.remove_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            if 'error' in result:
                self.status.setText('Conversion failed')
                QMessageBox.warning(self, 'Could not convert files', result['error'])
                return
            self.status.setText(f"{result['successful']} exported · {result['failed']} failed")
            failures = [f"{r['input_path'].name}: {r['error']}" for r in result['results'] if not r['success']]
            if failures:
                QMessageBox.warning(self, 'Some files could not be converted', '\n'.join(failures))
            return
        if kind == 'preview':
            self.pending.discard(path)
            if 'error' not in result and path in self.files:
                self.cache[path] = result
                self.cache.move_to_end(path)
                while len(self.cache) > 4:
                    self.cache.popitem(last=False)
        else:
            self.analysis_pending.discard(path)
        # A slow result from the previous file must never replace the current one.
        if path != self.selected_file:
            return
        if 'error' in result:
            if kind == 'preview':
                self.plot.message = 'Preview unavailable · try converting to WAV'
                self.plot.set_preview(None)
            else:
                self.analyze_button.setEnabled(True)
                self.metrics.setText(result['error'] + '\nTry converting this file to WAV first.')
                self.status.setText('Audio checks could not finish')
            return
        if kind == 'preview':
            self._show_preview(result)
        else:
            self.report = dict(file=str(path), **result)
            r = result
            self.metrics.setText(f"{r['duration']:.1f} s  ·  {r['sample_rate']:,} Hz  ·  {r['channels']} ch     |     Peak {r['peak_dbfs']:.1f} dBFS  ·  RMS {r['rms_dbfs']:.1f} dBFS\nCrest {r['crest_db']:.1f} dB  ·  Near full scale {r['clipping_percent']:.2f}%  ·  Quiet {r['quiet_percent']:.1f}% (< −40 dBFS)")
            self.analyze_button.setEnabled(True)
            self.export_button.setEnabled(True)
            self.status.setText('Audio checks complete')

    def _show_preview(self, result):
        self.plot.offset = 0
        self.plot.set_preview(result)
        self._set_zoom()
        self.spectrum_legend.setText(f"Frequency: 0–{result['rate'] / 2 / 1000:g} kHz · Color: −110 to −20 dBFS/Hz · Peak per time bin")
        self.preview_note.setText(f"Whole recording: {clock(result['seconds'] * 1000)} · Display: mono / {result['rate']:,} Hz")

    def _set_zoom(self, index=None):
        self.plot.window_seconds = [None, 30, 120, 600][self.zoom.currentIndex()]
        if self.plot.preview is None:
            self.timeline_scroll.setRange(0, 0)
            return
        span = self.plot.visible_seconds()
        self.timeline_scroll.setRange(0, max(0, round((self.plot.preview['seconds'] - span) * 1000)))
        self.timeline_scroll.setVisible(self.timeline_scroll.maximum() > 0)
        self.follow.setVisible(self.timeline_scroll.maximum() > 0)
        self.timeline_scroll.setPageStep(max(1, round(span * 1000)))
        self.timeline_scroll.setSingleStep(max(1, round(span * 100)))
        self.plot.offset = self.timeline_scroll.value() / 1000
        self.plot.update()

    def _scroll_plot(self, milliseconds):
        self.plot.offset = milliseconds / 1000
        self.plot.update()

    def _change_view(self, view):
        self.plot.view = view
        self.spectrum_legend.setVisible(view == 'Spectrogram')
        self.plot.update()

    def _analyze(self):
        path = self.selected_file
        if path is None or path in self.analysis_pending:
            return
        self.analysis_pending.add(path)
        self.analyze_button.setEnabled(False)
        self.status.setText('Checking audio…')
        self._submit('analysis', path, lambda: self.analyzer.analyze(path))

    def _export_report(self):
        if self.report is None:
            self.status.setText('Select a file and run audio checks first')
            return
        destination, _ = QFileDialog.getSaveFileName(self, 'Save audio report', self.selected_file.stem + '_analysis.json', 'JSON (*.json)')
        if destination:
            try:
                Path(destination).write_text(json.dumps(self.report, indent=2, allow_nan=False) + '\n')
                self.status.setText('Analysis report saved')
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Could not save report', str(exc))

    def _toggle_play(self):
        if not self.play_button.isEnabled():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def _media_status(self, status):
        ready = status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.EndOfMedia)
        self.play_button.setEnabled(ready and self.selected_file is not None)
        self.seek_slider.setEnabled(ready and self.player.duration() > 0)

    def _playback_changed(self, state):
        icon = 'pause.svg' if state == QMediaPlayer.PlaybackState.PlayingState else 'play.svg'
        self.play_button.setIcon(QIcon(str(ASSET_DIR / icon)))

    def _position_changed(self, position):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)
        self.time_label.setText(f'{clock(position)} / {clock(self.player.duration())}')
        self.plot.position = position
        if self.plot.preview and self.follow.isChecked() and self.plot.window_seconds:
            span = self.plot.visible_seconds()
            if not self.plot.offset <= position / 1000 < self.plot.offset + span:
                self.timeline_scroll.setValue(round(position / 1000 // span * span * 1000))
        if hasattr(self, 'annotation_time'):
            self.annotation_time.setText(f'{self.selected_file.name if self.selected_file else "No file selected"} · {clock(position)}')
        self.plot.update()

    def _duration_changed(self, duration):
        self.seek_slider.setRange(0, max(0, duration))
        self._position_changed(self.player.position())

    def _player_error(self, error, message):
        self.play_button.setEnabled(False)
        self.status.setText('Playback unavailable · try converting to WAV')
        self.play_button.setToolTip(message)

    @staticmethod
    def _display_path(path):
        try:
            return '~/' + str(path.relative_to(Path.home()))
        except ValueError:
            return str(path)

    def _select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, 'Save converted audio to', str(self.output_dir))
        if path:
            self.output_dir = Path(path)
            self.output_label.setText(self._display_path(self.output_dir))

    def _start_conversion(self):
        if self.busy:
            return
        if not self.files:
            self.status.setText('Add files to start converting')
            return
        rate = self.rate.currentText()
        options = dict(sample_rate=None if rate == 'Keep original' else int(rate.split()[0]),
                       mono=self.channels.currentText() == 'Mono', bit_depth=int(self.depth.currentText().split('-')[0]), output_format=self.output_format.currentText())
        files, destination = list(self.files), self.output_dir
        self.busy = True
        self.convert_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.progress.setValue(0)
        self.status.setText('Converting…')
        def run():
            def progress(current, total, path, result):
                self.events.progress.emit(current, total, result)
            return self.converter.batch_convert(files, destination, progress_callback=progress, **options)
        self._submit('conversion', None, run, self.conversion_pool)

    def _progress(self, current, total, result):
        self.progress.setValue(round(100 * current / total))
        self.table.set_status(current - 1, 'Exported' if result['success'] else 'Failed')
        self.status.setText(f'Converting {current} / {total}')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy:
            self.status.setText('Wait for the conversion to finish before closing')
            event.ignore()
            return
        self.player.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.conversion_pool.shutdown(wait=False, cancel_futures=True)
        # Running callbacks still own this object until their results arrive.
        event.accept()
