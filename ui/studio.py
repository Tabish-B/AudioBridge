"""The conversion workspace, with background checks and a built-in player."""

import json
import os
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if sys.platform == 'darwin':
    os.environ.setdefault('QT_MEDIA_BACKEND', 'darwin')

import numpy as np
from PySide6.QtCore import QObject, Qt, QUrl, Signal, QLineF, QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QShortcut, QKeySequence, QFontDatabase
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from converter import AudioAnalyzer, AudioConverter
from converter.preview import build_preview

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
        self.message = 'Select a file to see its waveform'
        self.setToolTip('Click the preview to seek within the first 120 seconds')

    def set_preview(self, preview):
        self.preview = preview
        self.image = None
        if preview is not None:
            rgb = preview['spectrum']
            self.image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101612'))
        area = self.rect().adjusted(12, 10, -12, -24)
        painter.setPen(QColor('#223427'))
        for i in range(1, 8):
            x = area.left() + area.width() * i / 8
            painter.drawLine(QLineF(x, area.top(), x, area.bottom()))
        if self.preview is None:
            painter.setPen(QColor('#94a29c'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        if self.view == 'Spectrogram':
            painter.drawImage(area, self.image)
        else:
            low, high = self.preview['low'], self.preview['high']
            middle, scale = area.center().y(), area.height() / 2
            painter.setPen(QPen(QColor('#b8f59a'), 1))
            lines = [QLineF(area.left() + i * area.width() / max(1, len(low) - 1), middle - float(lo) * scale,
                            area.left() + i * area.width() / max(1, len(low) - 1), middle - float(hi) * scale)
                     for i, (lo, hi) in enumerate(zip(low, high))]
            painter.drawLines(lines)
        seconds = self.preview['seconds']
        if 0 <= self.position / 1000 <= seconds:
            x = area.left() + self.position / 1000 / max(seconds, .001) * area.width()
            painter.setPen(QPen(QColor('#eff4ef'), 1))
            painter.drawLine(QLineF(x, area.top(), x, area.bottom()))
        painter.setPen(QColor('#94a29c'))
        painter.drawText(12, self.height() - 7, '00:00')
        end = clock(seconds * 1000)
        painter.drawText(self.width() - painter.fontMetrics().horizontalAdvance(end) - 12, self.height() - 7, end)
        if self.view == 'Spectrogram':
            painter.drawText(18, 22, '8 kHz')
        painter.end()

    def mousePressEvent(self, event):
        if self.preview and event.button() == Qt.MouseButton.LeftButton:
            fraction = max(0, min(1, (event.position().x() - 12) / max(1, self.width() - 24)))
            self.seek.emit(fraction * self.preview['seconds'] * 1000)


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
        self.setWindowTitle('AudioBridge · Conversion studio')
        self.setWindowIcon(QIcon(str(ASSET_DIR / 'audiobridge.png')))
        self.resize(1400, 950)
        self.setMinimumSize(1080, 760)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
        self.setStyleSheet((ROOT / 'ui' / 'theme.qss').read_text().replace('@UI_FONT@', font).replace('@ASSET_DIR@', ASSET_DIR.as_posix()))
        self.converter = AudioConverter()
        self.analyzer = AudioAnalyzer()
        self.files = []
        self.selected_file = None
        self.report = None
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
        self.setAcceptDrops(True)

    def _build_ui(self):
        host = QWidget()
        host.setObjectName('workspace')
        self.setCentralWidget(host)
        shell = QHBoxLayout(host)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(205)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(18, 26, 18, 22)
        nav.setSpacing(8)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSET_DIR / 'audiobridge.png')).scaled(33, 33, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand.addWidget(logo)
        brand.addWidget(label('AudioBridge', 'brand'))
        nav.addLayout(brand)
        nav.addSpacing(32)
        nav.addWidget(label('WORKSPACE', 'eyebrow'))
        nav.addSpacing(8)
        active = button('⇄   Convert audio', lambda: self.table.setFocus(), 'nav')
        active.setCheckable(True)
        active.setChecked(True)
        nav.addWidget(active)
        nav.addWidget(button('▥   Audio analysis', self._analyze, 'nav'))
        nav.addWidget(button('↗   Export report', self._export_report, 'nav'))
        nav.addStretch()
        privacy, layout = card()
        privacy.setMinimumHeight(140)
        layout.addWidget(label('Your audio. Your device.'))
        note = label('Processed locally, always.\nOriginal files stay intact.', 'muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        nav.addWidget(privacy)
        shell.addWidget(sidebar)
        workspace = QVBoxLayout()
        workspace.setContentsMargins(28, 22, 28, 24)
        workspace.setSpacing(12)
        shell.addLayout(workspace, 1)
        top = QHBoxLayout()
        top.addWidget(label('Workspace    /    Conversion studio', 'muted'))
        top.addStretch()
        top.addWidget(label('●  Local engine ready', 'badge'))
        workspace.addLayout(top)
        workspace.addSpacing(6)
        workspace.addWidget(label('Conversion studio', 'title'))
        workspace.addWidget(label('Your sound, ready for what’s next. Convert, refine, and inspect in one place.', 'muted'))
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body_content = QWidget()
        body_content.setObjectName('workspace')
        body = QHBoxLayout(body_content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(22)
        body_scroll.setWidget(body_content)
        workspace.addWidget(body_scroll, 1)
        center = QVBoxLayout()
        center.setSpacing(14)
        body.addLayout(center, 1)
        upload, box = card('upload')
        upload.setFixedHeight(108)
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label('Bring your audio in', 'heading'))
        copy.addWidget(label('Drop files here, or browse to get started', 'muted'))
        copy.addSpacing(6)
        copy.addWidget(label('WAV, MP3, FLAC, AAC, OGG, AIFF & video', 'muted'))
        row.addLayout(copy, 1)
        actions = QVBoxLayout()
        actions.addWidget(button('+   Select files', self._upload_files, 'primary'))
        actions.addWidget(button('Select a folder', self._upload_folder, 'quiet'))
        row.addLayout(actions)
        box.addLayout(row)
        center.addWidget(upload)
        queue_card, box = card()
        queue_card.setFixedHeight(146)
        queue_heading = QHBoxLayout()
        self.queue_label = label('Files in queue   ·   0', 'heading')
        queue_heading.addWidget(self.queue_label)
        queue_heading.addStretch()
        self.remove_button = button('Remove', self._remove_file, 'quiet')
        queue_heading.addWidget(self.remove_button)
        self.clear_button = button('Clear all', self._clear_files, 'quiet')
        queue_heading.addWidget(self.clear_button)
        box.addLayout(queue_heading)
        self.table = FileQueue()
        self.table.itemSelectionChanged.connect(self._on_select)
        box.addWidget(self.table)
        center.addWidget(queue_card)
        preview, box = card()
        preview.setMinimumHeight(334)
        box.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label('Audio preview', 'heading'))
        self.filename = label('No file selected', 'muted')
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        head.addWidget(self.filename, 1)
        self.analyze_button = button('Analyze file', self._analyze)
        self.analyze_button.setEnabled(False)
        head.addWidget(self.analyze_button)
        self.export_button = button('Export JSON', self._export_report, 'quiet')
        self.export_button.setEnabled(False)
        head.addWidget(self.export_button)
        box.addLayout(head)
        switch = QHBoxLayout()
        self.view = QComboBox()
        self.view.addItems(['Waveform', 'Spectrogram'])
        self.view.currentTextChanged.connect(self._change_view)
        switch.addWidget(self.view)
        switch.addWidget(label('Preview · first 120 s · mono / 16 kHz', 'muted'))
        switch.addStretch()
        box.addLayout(switch)
        self.plot = AudioPlot()
        self.plot.seek.connect(lambda value: self.player.setPosition(int(value)))
        box.addWidget(self.plot, 1)
        transport = QHBoxLayout()
        self.play_button = button('', self._toggle_play, 'primary')
        self.play_button.setIcon(QIcon(str(ASSET_DIR / 'play.svg')))
        self.play_button.setIconSize(QSize(12, 14))
        self.play_button.setFixedWidth(40)
        self.play_button.setEnabled(False)
        self.play_button.setToolTip('Play / pause (Space)')
        transport.addWidget(self.play_button)
        restart = button('', lambda: self.player.setPosition(0), 'quiet')
        restart.setIcon(QIcon(str(ASSET_DIR / 'restart.svg')))
        restart.setToolTip('Restart recording')
        transport.addWidget(restart)
        self.time_label = label('00:00 / 00:00', 'muted')
        transport.addWidget(self.time_label)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.player.setPosition)
        transport.addWidget(self.seek_slider, 1)
        self.speed = QComboBox()
        self.speed.addItems(['0.75×', '1×', '1.25×', '1.5×', '2×'])
        self.speed.setCurrentIndex(1)
        self.speed.setFixedWidth(80)
        self.speed.currentIndexChanged.connect(lambda index: self.player.setPlaybackRate([.75, 1, 1.25, 1.5, 2][index]))
        transport.addWidget(self.speed)
        transport.addWidget(label('Vol', 'muted'))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(55)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        transport.addWidget(self.volume)
        box.addLayout(transport)
        self.metrics = label('Run audio checks to inspect levels, clipping, and quiet sections.', 'muted')
        self.metrics.setWordWrap(True)
        box.addWidget(self.metrics)
        center.addWidget(preview, 1)
        settings_card, settings = card()
        settings_card.setFixedWidth(278)
        body.addWidget(settings_card)
        settings.addWidget(label('Conversion settings', 'heading'))
        settings.addSpacing(6)
        self.preset = self._combo(settings, 'Preset', ['Speech / ASR', 'Keep source', 'Studio WAV'])
        self.preset.currentIndexChanged.connect(self._preset_changed)
        settings.addWidget(label('Output format     WAV · lossless PCM', 'muted'))
        self.rate = self._combo(settings, 'Sample rate', ['Keep original', '16000 Hz', '22050 Hz', '44100 Hz', '48000 Hz'], 1)
        self.depth = self._combo(settings, 'Bit depth', ['16-bit PCM', '24-bit PCM'])
        self.channels = self._combo(settings, 'Channels', ['Mono', 'Keep original'])
        settings.addWidget(label('Save converted files to'))
        self.output_label = label(self._display_path(self.output_dir), 'muted')
        self.output_label.setWordWrap(True)
        settings.addWidget(self.output_label)
        settings.addWidget(button('Change folder', self._select_output_dir))
        settings.addWidget(label('Original files are always preserved.', 'muted'))
        note = label('Speech preset\n16 kHz · mono · 16-bit PCM\n\nCheck your model’s input requirements before exporting.', 'muted')
        note.setWordWrap(True)
        settings.addWidget(note)
        settings.addStretch()
        footer, layout = card('footer')
        bottom = QHBoxLayout()
        summary = QVBoxLayout()
        self.status = label('●  Ready when you are', 'heading')
        summary.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        summary.addWidget(self.progress)
        bottom.addLayout(summary, 1)
        self.output_summary = label('WAV  /  16 kHz  /  Mono', 'muted')
        bottom.addWidget(self.output_summary, 1)
        self.convert_button = button('Convert files   →', self._start_conversion, 'primary')
        self.convert_button.setMinimumWidth(210)
        bottom.addWidget(self.convert_button)
        layout.addLayout(bottom)
        workspace.addWidget(footer)
        for combo in (self.rate, self.depth, self.channels):
            combo.currentTextChanged.connect(self._update_summary)

    def _combo(self, layout, title, values, index=0):
        layout.addSpacing(4)
        layout.addWidget(label(title))
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentIndex(index)
        layout.addWidget(combo)
        return combo

    def _preset_changed(self, index):
        rate, depth, channels = [(1, 0, 0), (0, 0, 1), (4, 1, 1)][index]
        self.rate.setCurrentIndex(rate)
        self.depth.setCurrentIndex(depth)
        self.channels.setCurrentIndex(channels)

    def _update_summary(self):
        self.output_summary.setText(f'WAV  /  {self.rate.currentText()}  /  {self.channels.currentText()}')

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
        self.player.stop()
        self.player.setSource(QUrl())
        self.selected_file = self.report = None
        self.filename.setText('No file selected')
        self.plot.message = 'Select a file to see its waveform'
        self.plot.set_preview(None)
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
            self.plot.set_preview(self.cache[path])
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
            self.plot.set_preview(result)
        else:
            self.report = dict(file=str(path), **result)
            r = result
            self.metrics.setText(f"{r['duration']:.1f} s  ·  {r['sample_rate']:,} Hz  ·  {r['channels']} ch     |     Peak {r['peak_dbfs']:.1f} dBFS  ·  RMS {r['rms_dbfs']:.1f} dBFS\nCrest {r['crest_db']:.1f} dB  ·  Near full scale {r['clipping_percent']:.2f}%  ·  Quiet {r['quiet_percent']:.1f}% (< −40 dBFS)")
            self.analyze_button.setEnabled(True)
            self.export_button.setEnabled(True)
            self.status.setText('Audio checks complete')

    def _change_view(self, view):
        self.plot.view = view
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
                       mono=self.channels.currentText() == 'Mono', bit_depth=int(self.depth.currentText().split('-')[0]))
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
