"""The conversion workspace, with background checks and a built-in player."""

import csv
import json
import os
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if sys.platform == "darwin":
    os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QFontDatabase, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from converter import AudioAnalyzer, AudioConverter
from converter.formats import FORMATS, output_suffix
from converter.preview import build_preview
from converter.regions import AudioRegion, check_destination, export_region, split_recording
from converter.spectral import SpectralSettings
from converter.waveform import waveform_window
from version import __version__

from .editor_panel import EditorPanel
from .region_playback import RegionPlayback
from .widgets import FileQueue, button, card, clock, label

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ASSET_DIR = ROOT / "assets"


class Events(QObject):
    finished = Signal(str, object, object)
    progress = Signal(int, int, object)


class AudioBridgeGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AudioBridge {__version__} · Conversion studio")
        self.setWindowIcon(QIcon(str(ASSET_DIR / "audiobridge.png")))
        self.resize(1400, 950)
        self.setMinimumSize(420, 500)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
        self.setStyleSheet(
            (ROOT / "ui" / "theme.qss")
            .read_text()
            .replace("@UI_FONT@", font)
            .replace("@ASSET_DIR@", ASSET_DIR.as_posix())
        )
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
        self.output_dir = Path.home() / "Downloads" / "AudioBridge"
        self.cache = OrderedDict()
        self.spectral_settings = SpectralSettings()
        self.preview_request = None
        self.detail_request = None
        self.detail_timer = QTimer(self)
        self.detail_timer.setSingleShot(True)
        self.detail_timer.setInterval(120)
        self.detail_timer.timeout.connect(self._load_detail)
        self._closing = False
        self.pending_source_seek = None
        self.pending = set()
        self.analysis_pending = set()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audio-check")
        self.conversion_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-export")
        self.events = Events(self)
        self.events.finished.connect(self._finished)
        self.events.progress.connect(self._progress)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        self.region_player = RegionPlayback(self)
        self.region_player.audio.setVolume(0.7)
        self.region_player.position_changed.connect(self._selection_position)
        self.region_player.state_changed.connect(self._playback_changed)
        self.region_player.ended.connect(self._selection_ended)
        self.region_player.ready.connect(self._selection_ready)
        self.region_player.error.connect(self._selection_error)
        self._build_ui()
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.errorOccurred.connect(self._player_error)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.shortcuts = [
            QShortcut(QKeySequence("Space"), self),
            QShortcut(QKeySequence("Delete"), self),
            QShortcut(QKeySequence("Backspace"), self),
        ]
        self.shortcuts[0].activated.connect(self._toggle_play)
        for shortcut in self.shortcuts[1:]:
            shortcut.activated.connect(self._remove_file)
        for keys, callback in [
            ("Ctrl+O" if sys.platform != "darwin" else "Meta+O", self._upload_files),
            ("Ctrl+Shift+O" if sys.platform != "darwin" else "Meta+Shift+O", self._upload_folder),
            ("I", self._mark_selection_start),
            ("O", self._mark_selection_end),
            ("Escape", self._clear_selection),
            ("F1", self._show_help),
        ]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self.setAcceptDrops(True)

    def _set_status(self, text):
        self.status.setText(text)
        if hasattr(self, "editor_feedback"):
            self.editor_feedback.setText(text)

    def _focus_changed(self, old, current):
        editing = isinstance(current, (QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox))
        for shortcut in self.shortcuts:
            shortcut.setEnabled(not editing)

    def _build_ui(self):
        host = QWidget()
        host.setObjectName("workspace")
        self.setCentralWidget(host)
        shell = QHBoxLayout(host)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(205)
        nav = QVBoxLayout(self.sidebar)
        nav.setContentsMargins(18, 26, 18, 22)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(ASSET_DIR / "audiobridge.png")).scaled(
                33,
                33,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        brand.addWidget(logo)
        brand.addWidget(label("AudioBridge", "brand"))
        nav.addLayout(brand)
        nav.addWidget(label(f"VERSION {__version__}", "eyebrow"))
        nav.addSpacing(24)
        self.nav_buttons = []
        for index, title in [
            (0, "Conversion studio"),
            (3, "Audio editor"),
            (1, "Dataset audit"),
            (2, "Segment annotations"),
        ]:
            item = button(title, lambda checked=False, page=index: self._set_page(page), "nav")
            item.setCheckable(True)
            item.setProperty("page", index)
            nav.addWidget(item)
            self.nav_buttons.append(item)
        nav.addStretch()
        nav.addWidget(button("Help & shortcuts", self._show_help, "nav"))
        privacy = label(
            "Your audio. Your device.\n\nProcessed locally.\nOriginal files stay intact.", "muted"
        )
        privacy.setWordWrap(True)
        nav.addWidget(privacy)
        shell.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        studio_scroll = QScrollArea()
        studio_scroll.setWidgetResizable(True)
        self.studio_content = QWidget()
        self.studio_content.setObjectName("workspace")
        workspace = QVBoxLayout(self.studio_content)
        workspace.setContentsMargins(22, 22, 22, 22)
        workspace.setSpacing(14)
        studio_scroll.setWidget(self.studio_content)
        self.pages.addWidget(studio_scroll)
        self.page_picker = QComboBox()
        self.page_picker.addItems(
            ["Conversion studio", "Dataset audit", "Segment annotations", "Audio editor"]
        )
        self.page_picker.currentIndexChanged.connect(self._set_page)
        # The compact page picker stays outside the scrolling pages.
        mobile_host = QWidget()
        mobile_layout = QVBoxLayout(mobile_host)
        mobile_layout.setContentsMargins(0, 0, 0, 0)
        mobile_layout.addWidget(self.page_picker)
        mobile_layout.addWidget(self.pages, 1)
        shell.addWidget(mobile_host, 1)
        top = QHBoxLayout()
        top.addWidget(label(f"AudioBridge {__version__}", "muted"))
        top.addStretch()
        top.addWidget(label("●  Local engine ready", "badge"))
        workspace.addLayout(top)
        workspace.addWidget(label("Conversion studio", "title"))
        subtitle = label("Convert recordings, listen back, and inspect the signal.", "muted")
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
        upload, box = card("upload")
        self.upload_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        copy = QVBoxLayout()
        copy.addWidget(label("Bring your audio in", "heading"))
        note = label("Drop audio or video files here, or browse to get started.", "muted")
        note.setWordWrap(True)
        copy.addWidget(note)
        self.upload_row.addLayout(copy, 1)
        actions = QVBoxLayout()
        actions.addWidget(button("+   Select files", self._upload_files, "primary"))
        actions.addWidget(button("Select a folder", self._upload_folder, "quiet"))
        self.upload_row.addLayout(actions)
        box.addLayout(self.upload_row)
        center.addWidget(upload)
        queue_card, box = card()
        queue_card.setFixedHeight(166)
        self.import_notice = label("", "notice")
        self.import_notice.setWordWrap(True)
        self.import_notice.hide()
        workspace.addWidget(self.import_notice)
        self.queue_label = label("Files in queue   ·   0", "heading")
        self.queue_header = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.queue_header.addWidget(self.queue_label, 1)
        queue_actions = QHBoxLayout()
        self.remove_button = button("Remove selected", self._remove_file, "quiet")
        self.clear_button = button("Clear all", self._clear_files, "quiet")
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
        self.editor = EditorPanel(ASSET_DIR)
        self._connect_editor()
        self.studio_editor_layout = center
        center.addWidget(self.editor, 1)
        self.settings_card, settings = card()
        self.settings_card.setMinimumWidth(250)
        self.settings_card.setMaximumWidth(290)
        self.body.addWidget(self.settings_card)
        settings.addWidget(label("Export settings", "heading"))
        self.output_format = self._combo(settings, "Output format", list(FORMATS))
        self.format_note = label(FORMATS["WAV"][1], "muted")
        self.format_note.setWordWrap(True)
        settings.addWidget(self.format_note)
        self.preset = self._combo(
            settings,
            "Processing preset (optional)",
            [
                "Keep source settings",
                "ASR input · 16 kHz mono",
                "Archive · 48 kHz / 24-bit",
                "Custom",
            ],
        )
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.rate = self._combo(
            settings,
            "Sample rate",
            ["Keep original", "16000 Hz", "22050 Hz", "44100 Hz", "48000 Hz"],
        )
        self.depth = self._combo(
            settings, "Bit depth · lossless formats", ["16-bit PCM", "24-bit PCM"]
        )
        self.channels = self._combo(settings, "Channels", ["Mono", "Keep original"], 1)
        self.settings_note = label(
            "Keep source settings preserves sample rate and channels. PCM depth is chosen separately. Lossy formats are re-encoded.",
            "muted",
        )
        self.settings_note.setWordWrap(True)
        settings.addWidget(self.settings_note)
        settings.addWidget(label("Save converted files to"))
        self.output_label = label(self._display_path(self.output_dir), "muted")
        self.output_label.setWordWrap(True)
        settings.addWidget(self.output_label)
        settings.addWidget(button("Change folder", self._select_output_dir))
        note = label("Original files are always preserved.", "muted")
        note.setWordWrap(True)
        settings.addWidget(note)
        settings.addStretch()
        footer, layout = card("footer")
        self.status = label("●  Ready when you are", "heading")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.footer_actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.output_summary = label("", "muted")
        self.output_summary.setWordWrap(True)
        self.footer_actions.addWidget(self.output_summary, 1)
        self.convert_button = button("Convert files   →", self._start_conversion, "primary")
        self.convert_button.setEnabled(False)
        self.footer_actions.addWidget(self.convert_button)
        layout.addLayout(self.footer_actions)
        workspace.addWidget(footer)
        for combo in (self.rate, self.depth, self.channels):
            combo.currentTextChanged.connect(self._manual_settings)
        self.output_format.currentTextChanged.connect(self._format_changed)
        self._build_research_pages()
        self.editor_page_layout = self._research_page(
            "Audio editor", "Inspect spectral features, select regions, and export new audio files."
        )
        self.editor_feedback = label("Recording ready", "muted")
        self.editor_feedback.setWordWrap(True)
        self.editor_page_layout.addWidget(self.editor_feedback)
        self._update_summary()
        self._set_page(0)
        self._apply_responsive()

    def _connect_editor(self):
        panel = self.editor
        panel.open_editor_requested.connect(lambda: self._set_page(3))
        panel.analyze_requested.connect(self._analyze)
        panel.report_requested.connect(self._export_report)
        panel.zoom_requested.connect(self._zoom_by)
        panel.play_requested.connect(self._toggle_play)
        panel.restart_requested.connect(lambda: self._seek(0))
        panel.view.currentTextChanged.connect(self._change_view)
        panel.zoom.currentIndexChanged.connect(self._set_zoom)
        panel.spectral_controls.apply_requested.connect(self._apply_spectral)
        panel.plot.seek.connect(self._seek)
        panel.plot.selection_changed.connect(self._drag_selection)
        panel.plot.zoom_requested.connect(self._zoom_by)
        panel.timeline_scroll.valueChanged.connect(self._scroll_plot)
        panel.seek_slider.sliderMoved.connect(self._seek)
        panel.speed.currentIndexChanged.connect(self._set_speed)
        panel.volume.valueChanged.connect(self._set_volume)
        panel.region_controls.selection_changed.connect(self._typed_selection)
        panel.region_controls.play_requested.connect(self._play_selection)
        panel.region_controls.export_requested.connect(self._export_selection)
        panel.region_controls.split_requested.connect(self._split_audio)
        panel.region_controls.clear_requested.connect(self._clear_selection)

    def _set_page(self, index):
        self.pages.setCurrentIndex(index)
        self.page_picker.blockSignals(True)
        self.page_picker.setCurrentIndex(index)
        self.page_picker.blockSignals(False)
        for item in self.nav_buttons:
            item.setChecked(item.property("page") == index)
        if index == 3:
            self.editor_page_layout.addWidget(self.editor, 1)
        elif self.editor.parentWidget() is not self.studio_editor_layout.parentWidget():
            self.studio_editor_layout.addWidget(self.editor, 1)
        self.editor.spectral_controls.setVisible(index == 3)
        self.editor.region_controls.setVisible(index == 3)
        self.editor.zoom_in.setVisible(index == 3)
        self.editor.zoom_out.setVisible(index == 3)
        self.editor.open_editor.setVisible(index != 3)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "body"):
            self._apply_responsive()

    def _apply_responsive(self):
        narrow = self.width() < 1100
        compact = self.width() < 650
        self.sidebar.setVisible(self.width() >= 950)
        self.page_picker.setVisible(self.width() < 950)
        self.body.setDirection(
            QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        )
        self.settings_card.setMaximumWidth(16777215 if narrow else 290)
        self.settings_card.setMinimumWidth(0 if narrow else 250)
        direction = (
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )
        for layout in (
            self.upload_row,
            self.editor.transport,
            self.footer_actions,
            self.queue_header,
            self.editor.preview_header,
        ):
            layout.setDirection(direction)

    def _research_page(self, title, description):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("workspace")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        layout.addWidget(label(title, "title"))
        note = label(description, "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        return layout

    def _build_research_pages(self):
        audit = self._research_page(
            "Dataset audit",
            "Check the files in your conversion queue together. Flags describe signal levels; they are not speech detection or an ASR quality score.",
        )
        self.audit_status = label(
            "Add recordings in Conversion studio, then scan the queue.", "muted"
        )
        self.audit_status.setWordWrap(True)
        audit.addWidget(self.audit_status)
        self.audit_button = button("Scan queued recordings", self._audit, "primary")
        audit.addWidget(self.audit_button)
        self.audit_export = button("Export audit CSV", self._export_audit)
        self.audit_export.setEnabled(False)
        audit.addWidget(self.audit_export)
        self.audit_text = QTextEdit()
        self.audit_text.setReadOnly(True)
        self.audit_text.setMinimumHeight(240)
        audit.addWidget(self.audit_text, 1)
        annotations = self._research_page(
            "Segment annotations",
            "Mark time ranges while listening, label them, and export a CSV for dataset review. These are manual annotations; the original recording is not edited.",
        )
        self.annotation_time = label("Select a recording in Conversion studio.", "muted")
        self.annotation_time.setWordWrap(True)
        annotations.addWidget(self.annotation_time)
        self.annotation_label = QLineEdit()
        self.annotation_label.setPlaceholderText("Label, e.g. speech, background noise, overlap")
        self.annotation_label.setMaxLength(100)
        annotations.addWidget(self.annotation_label)
        annotations.addWidget(button("Mark start at playhead", self._mark_start))
        annotations.addWidget(button("Mark end and add segment", self._mark_end))
        self.annotation_status = label(
            "Start playback in the studio, then mark the segment here.", "muted"
        )
        self.annotation_status.setWordWrap(True)
        annotations.addWidget(self.annotation_status)
        self.annotation_list = QListWidget()
        self.annotation_list.setMinimumHeight(180)
        annotations.addWidget(self.annotation_list, 1)
        annotations.addWidget(
            button("Remove selected annotation", self._remove_annotation, "quiet")
        )
        annotations.addWidget(button("Export annotations CSV", self._export_annotations))

    def _audit(self):
        if self.audit_busy:
            return
        if not self.files:
            self.audit_status.setText("Add recordings to the conversion queue first.")
            return
        paths = list(self.files)
        self.audit_busy = True
        self.audit_button.setEnabled(False)
        self.audit_status.setText(f"Scanning {len(paths)} recordings…")

        def scan():
            results = []
            for path in paths:
                result = self.analyzer.analyze(path)
                row = dict(file=str(path), **result)
                flags = []
                if "error" not in result:
                    if result["clipping_percent"] > 0.01:
                        flags.append("near full scale > 0.01%")
                    if result["rms_dbfs"] < -35:
                        flags.append("low RMS < -35 dBFS")
                    if result["quiet_percent"] > 75:
                        flags.append("quiet windows > 75%")
                row["flags"] = "; ".join(flags)
                results.append(row)
            return results

        self._submit("audit", None, scan)

    def _finish_audit(self, result):
        self.audit_busy = False
        self.audit_button.setEnabled(True)
        if isinstance(result, dict) and "error" in result:
            self.audit_status.setText(result["error"])
            return
        self.audit_results = result
        self.audit_export.setEnabled(bool(result))
        failures = sum("error" in row for row in result)
        self.audit_status.setText(
            f"{len(result)} recordings checked · {failures} could not be read"
        )
        lines = []
        for row in result:
            lines.append(Path(row["file"]).name)
            if "error" in row:
                lines.append("  Could not analyze: " + row["error"])
            else:
                lines.append(
                    f"  {row['duration']:.2f} s | {row['sample_rate']} Hz | {row['channels']} ch | RMS {row['rms_dbfs']:.1f} dBFS | Peak {row['peak_dbfs']:.1f} dBFS"
                )
                lines.append("  " + (row["flags"] or "No level flags at the configured thresholds"))
            lines.append("")
        self.audit_text.setPlainText("\n".join(lines))

    def _write_csv(self, destination, rows, fields):
        with Path(destination).open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def _export_audit(self):
        if not self.audit_results:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save dataset audit", "dataset_audit.csv", "CSV (*.csv)"
        )
        if destination:
            try:
                self._write_csv(
                    destination,
                    self.audit_results,
                    [
                        "file",
                        "duration",
                        "sample_rate",
                        "channels",
                        "rms_dbfs",
                        "peak_dbfs",
                        "crest_db",
                        "clipping_percent",
                        "quiet_percent",
                        "flags",
                        "error",
                    ],
                )
                self.audit_status.setText("Dataset audit saved")
            except OSError as exc:
                self.audit_status.setText(str(exc))

    def _mark_start(self):
        if self.selected_file is None:
            self.annotation_status.setText("Select a recording in Conversion studio first.")
            return
        self.segment_start = (self.selected_file, self.editor.plot.position / 1000)
        self.annotation_status.setText(
            f"Start marked at {self.segment_start[1]:.3f} s. Seek or play to the end of the segment."
        )

    def _mark_end(self):
        if self.segment_start is None or self.segment_start[0] != self.selected_file:
            self.annotation_status.setText("Mark a start point in the selected recording first.")
            return
        start = self.segment_start[1]
        end = self.editor.plot.position / 1000
        if end <= start:
            self.annotation_status.setText("The end must be after the start point.")
            return
        text = self.annotation_label.text().strip() or "unlabelled"
        row = dict(
            file=str(self.selected_file),
            start_seconds=round(start, 3),
            end_seconds=round(end, 3),
            label=text,
        )
        self.annotations.append(row)
        self.annotation_list.addItem(f"{self.selected_file.name}\n{start:.3f}–{end:.3f} s · {text}")
        self.segment_start = None
        self.annotation_status.setText("Segment added. Mark another start to continue.")

    def _remove_annotation(self):
        index = self.annotation_list.currentRow()
        if index >= 0:
            self.annotation_list.takeItem(index)
            self.annotations.pop(index)

    def _export_annotations(self):
        if not self.annotations:
            self.annotation_status.setText("Add a segment before exporting.")
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save annotations", "annotations.csv", "CSV (*.csv)"
        )
        if destination:
            try:
                self._write_csv(
                    destination, self.annotations, ["file", "start_seconds", "end_seconds", "label"]
                )
                self.annotation_status.setText("Annotations saved")
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
        self.depth.setEnabled(value in ("WAV", "FLAC", "AIFF", "Keep original"))
        self._update_summary()

    def _update_summary(self):
        self.output_summary.setText(
            f"{self.output_format.currentText()}  /  {self.rate.currentText()}  /  {self.channels.currentText()}"
        )

    def _upload_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select audio or video files")
        self.add_files(paths)

    def _upload_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select a folder of recordings")
        if path:
            self.add_files(
                sorted(
                    p
                    for p in Path(path).iterdir()
                    if p.is_file() and self.converter.inspector.is_supported(p)
                )
            )

    def add_files(self, paths):
        if self.busy:
            self._set_status("Finish this conversion before changing the queue")
            return
        issues = []
        for path in paths:
            path = Path(path).resolve()
            if not path.is_file() or not self.converter.inspector.is_supported(path):
                issues.append(f"{path.name}: unsupported format or missing file")
                continue
            if path in self.files:
                issues.append(f"{path.name}: already queued")
                continue
            self.files.append(path)
            self.table.add_file(path)
        self.queue_label.setText(f"Files in queue   ·   {len(self.files)}")
        self.convert_button.setEnabled(bool(self.files) and not self.busy)
        if self.files and self.table.currentRow() < 0:
            self.table.setCurrentRow(0)
        self.import_notice.setText(
            "\n".join(issues[:4]) + (f"\n…and {len(issues) - 4} more" if len(issues) > 4 else "")
        )
        self.import_notice.setVisible(bool(issues))
        if issues:
            self._set_status(f"{len(issues)} import notices · review the filenames above")

    def _reset_selection(self):
        self.pending_source_seek = None
        self.segment_start = None
        self.region_player.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.selected_file = self.report = None
        self.editor.filename.setText("No file selected")
        self.editor.file_properties.clear()
        self.editor.plot.message = "Select a file to see its waveform"
        self.editor.plot.set_preview(None)
        self.editor.plot.selection = None
        self.detail_request = None
        self.editor.region_controls.set_region(0, 0)
        self.editor.region_controls.set_duration(0)
        self.editor.plot.offset = 0
        self.editor.timeline_scroll.setRange(0, 0)
        self.editor.timeline_scroll.hide()
        self.editor.follow.hide()
        self.editor.metrics.setText(
            "Run audio checks to inspect levels, clipping, and quiet sections."
        )
        self.editor.play_button.setEnabled(False)
        self.editor.analyze_button.setEnabled(False)
        self.editor.export_button.setEnabled(False)
        self.editor.seek_slider.setEnabled(False)

    def _clear_files(self):
        if self.busy:
            return
        self._reset_selection()
        self.table.blockSignals(True)
        self.table.clear()
        self.table.blockSignals(False)
        self.files.clear()
        self.cache.clear()
        self.import_notice.hide()
        self.queue_label.setText("Files in queue   ·   0")
        self.convert_button.setEnabled(False)
        self._set_status("●  Ready when you are")

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
        self.queue_label.setText(f"Files in queue   ·   {len(self.files)}")
        self.convert_button.setEnabled(bool(self.files) and not self.busy)
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
        self.editor.filename.setText(path.name)
        self.editor.filename.setToolTip(str(path))
        self.editor.analyze_button.setEnabled(path not in self.analysis_pending)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.editor.plot.position = 0
        cached = self.cache.get(path)
        if cached and cached.get("spectral_settings") == self.spectral_settings:
            self.cache.move_to_end(path)
            self._show_preview(cached)
        else:
            self._request_preview()

    def _request_preview(self):
        path = self.selected_file
        if path is None:
            return
        settings = self.spectral_settings
        request = (path, settings)
        self.preview_request = request
        if request in self.pending:
            return
        self.pending.add(request)
        self.editor.plot.spectral_loading = True
        self.editor.plot.message = "Preparing recording…"
        self.editor.plot.update()
        self._set_status("Preparing analysis…")
        self._submit("preview", request, lambda: build_preview(path, settings))

    def _submit(self, kind, path, operation, pool=None):
        if self._closing:
            return
        future = (pool or self.pool).submit(operation)

        def done(completed):
            if completed.cancelled():
                return
            try:
                result = completed.result()
            except Exception as exc:
                result = {"error": str(exc)}
            if not self._closing:
                self.events.finished.emit(kind, path, result)

        future.add_done_callback(done)

    def _finished(self, kind, path, result):
        if self._closing:
            return
        if kind == "detail":
            if path == self.detail_request and "error" not in result:
                self.editor.plot.detail = result
                self.editor.plot.update()
            return
        if kind == "edit":
            self._finish_edit(result)
            return
        if kind == "preview" and isinstance(path, tuple):
            request = path
            self.pending.discard(request)
            path = request[0]
            if request != self.preview_request:
                return
        if kind == "audit":
            self._finish_audit(result)
            return
        if kind == "conversion":
            self.busy = False
            self.convert_button.setEnabled(True)
            self.remove_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            if "error" in result:
                self._set_status("Conversion failed")
                QMessageBox.warning(self, "Could not convert files", result["error"])
                return
            self._set_status(f"{result['successful']} exported · {result['failed']} failed")
            failures = [
                f"{r['input_path'].name}: {r['error']}"
                for r in result["results"]
                if not r["success"]
            ]
            if failures:
                QMessageBox.warning(self, "Some files could not be converted", "\n".join(failures))
            return
        if kind == "preview":
            self.pending.discard(path)
            self.editor.plot.spectral_loading = False
            if "error" not in result and path in self.files:
                self.cache[path] = result
                self.cache.move_to_end(path)
                while len(self.cache) > 4:
                    self.cache.popitem(last=False)
        else:
            self.analysis_pending.discard(path)
        # A slow result from the previous file must never replace the current one.
        if path != self.selected_file:
            return
        if "error" in result:
            if kind == "preview":
                self.editor.plot.message = "Analysis unavailable · check the settings or recording"
                if self.editor.plot.preview is not None:
                    self.editor.view.setCurrentText("Waveform")
                else:
                    self.editor.plot.set_preview(None)
                    self.editor.region_controls.set_duration(0)
                self._set_status(result["error"])
                self.import_notice.setText(f"{path.name}: {result['error']}")
                self.import_notice.show()
            else:
                self.editor.analyze_button.setEnabled(True)
                self.editor.metrics.setText(
                    result["error"] + "\nTry converting this file to WAV first."
                )
                self._set_status("Audio checks could not finish")
            return
        if kind == "preview":
            self._show_preview(result)
        else:
            self.report = dict(file=str(path), **result)
            r = result
            self.editor.metrics.setText(
                f"{r['duration']:.1f} s  ·  {r['sample_rate']:,} Hz  ·  {r['channels']} ch     |     Peak {r['peak_dbfs']:.1f} dBFS  ·  RMS {r['rms_dbfs']:.1f} dBFS\nCrest {r['crest_db']:.1f} dB  ·  Near full scale {r['clipping_percent']:.2f}%  ·  Quiet {r['quiet_percent']:.1f}% (< −40 dBFS)"
            )
            self.editor.analyze_button.setEnabled(True)
            self.editor.export_button.setEnabled(True)
            self._set_status("Audio checks complete")

    def _show_preview(self, result):
        self.editor.plot.set_preview(result)
        info = result["metadata"]
        self.editor.file_properties.setText(
            f"Source: {info['sample_rate']:,} Hz · {info['channels']} ch · {info['codec']}"
        )
        self.editor.plot.spectral_loading = False
        self.editor.region_controls.set_duration(result["seconds"])
        self._set_status("Recording ready")
        self._set_zoom()
        self.editor.spectrum_legend.setText(result.get("spectral_legend", "Spectral power"))
        self.editor.preview_note.setText(
            f"Whole recording: {clock(result['seconds'] * 1000)} · Display: mono / {result['rate']:,} Hz"
        )

    def _set_zoom(self, index=None):
        if self.editor.zoom.currentIndex() != 6:
            self.editor.plot.window_seconds = [None, 30, 120, 600, 1, 5][
                self.editor.zoom.currentIndex()
            ]
        if self.editor.plot.preview is None:
            self.editor.timeline_scroll.setRange(0, 0)
            return
        span = self.editor.plot.visible_seconds()
        self.editor.timeline_scroll.setRange(
            0, max(0, round((self.editor.plot.preview["seconds"] - span) * 1000))
        )
        self.editor.timeline_scroll.setVisible(self.editor.timeline_scroll.maximum() > 0)
        self.editor.follow.setVisible(self.editor.timeline_scroll.maximum() > 0)
        self.editor.timeline_scroll.setPageStep(max(1, round(span * 1000)))
        self.editor.timeline_scroll.setSingleStep(max(1, round(span * 100)))
        self.editor.plot.offset = self.editor.timeline_scroll.value() / 1000
        self.detail_timer.start()
        self.editor.plot.update()

    def _scroll_plot(self, milliseconds):
        self.editor.plot.offset = milliseconds / 1000
        self.detail_timer.start()
        self.editor.plot.update()

    def _change_view(self, view):
        self.editor.plot.view = view
        self.editor.spectrum_legend.setVisible(view != "Waveform")
        if view != "Waveform":
            self.editor.spectral_controls.set_mode(view)
            if self.spectral_settings.mode != view:
                self._apply_spectral()
        self.editor.plot.update()

    def _apply_spectral(self):
        mode = self.editor.view.currentText()
        if mode == "Waveform":
            mode = "Spectrogram"
            self.editor.view.blockSignals(True)
            self.editor.view.setCurrentText(mode)
            self.editor.view.blockSignals(False)
            self.editor.plot.view = mode
            self.editor.spectrum_legend.show()
        try:
            settings = self.editor.spectral_controls.settings(mode)
            rate = self.editor.plot.preview["rate"] if self.editor.plot.preview else 48000
            settings.validate(rate)
        except ValueError as exc:
            self._set_status(str(exc))
            return
        self.spectral_settings = settings
        self.editor.spectral_controls.set_mode(mode)
        self._request_preview()

    def _set_speed(self, index):
        speed = [0.75, 1, 1.25, 1.5, 2][index]
        self.player.setPlaybackRate(speed)
        self.region_player.player.setPlaybackRate(speed)

    def _set_volume(self, value):
        self.audio.setVolume(value / 100)
        self.region_player.audio.setVolume(value / 100)

    def _seek(self, milliseconds):
        self.region_player.stop()
        position = round(milliseconds)
        self.pending_source_seek = (
            position
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
            else None
        )
        self.player.setPosition(position)
        self._display_position(position)

    def _zoom_by(self, factor, anchor=None):
        if self.editor.plot.preview is None:
            return
        duration = self.editor.plot.preview["seconds"]
        span = self.editor.plot.visible_seconds()
        anchor = self.editor.plot.offset + span / 2 if anchor is None else anchor
        fraction = (anchor - self.editor.plot.offset) / span
        new_span = min(duration, max(0.01, span * factor))
        self.editor.zoom.blockSignals(True)
        self.editor.zoom.setCurrentIndex(0 if new_span >= duration else 6)
        self.editor.zoom.blockSignals(False)
        self.editor.plot.window_seconds = None if new_span >= duration else new_span
        self._set_zoom()
        self.editor.timeline_scroll.setValue(round(max(0, anchor - fraction * new_span) * 1000))

    def _load_detail(self):
        if self._closing:
            return
        if self.selected_file is None or self.editor.plot.preview is None:
            return
        span = self.editor.plot.visible_seconds()
        if span > 30:
            return
        path, start, rate = (
            self.selected_file,
            self.editor.plot.offset,
            self.editor.plot.preview["rate"],
        )
        request = (path, start, span)
        if request == self.detail_request:
            return
        self.detail_request = request
        self._submit("detail", request, lambda: waveform_window(path, start, span, rate))

    def _drag_selection(self, start, end):
        if self.region_player.active:
            self._seek(self.editor.plot.position)
        self.editor.region_controls.set_region(start, end)
        self.editor.plot.selection = (start, end) if end > start else None
        self.editor.plot.update()

    def _typed_selection(self, start, end):
        if self.region_player.active:
            self._seek(self.editor.plot.position)
        self.editor.plot.selection = (start, end) if end > start else None
        self.editor.plot.update()

    def _clear_selection(self):
        if self.region_player.active:
            self._seek(self.editor.plot.position)
        self.editor.region_controls.set_region(0, 0)
        self.editor.plot.selection = None
        self.editor.plot.update()

    def _selected_region(self):
        if self.selected_file is None or self.editor.plot.preview is None:
            raise ValueError("Choose a recording first.")
        region = AudioRegion(
            self.editor.region_controls.start.value(), self.editor.region_controls.end.value()
        )
        info = self.editor.plot.preview["metadata"]
        region.sample_bounds(info["sample_rate"], info["duration"])
        return region

    def _play_selection(self):
        try:
            region = self._selected_region()
        except ValueError as exc:
            self._set_status(str(exc))
            return
        self.player.pause()
        self._seek(region.start * 1000)
        self._set_status("Preparing selected audio…")
        self.region_player.play(self.selected_file, region)

    def _selection_ready(self):
        self.editor.play_button.setEnabled(True)
        self._set_status("Playing selected region")

    def _selection_position(self, position):
        if self.region_player.active:
            self._display_position(position)

    def _selection_ended(self, seconds):
        self._seek(seconds * 1000)
        self._set_status("Selected region finished")

    def _selection_error(self, message):
        self.region_player.stop()
        self._set_status("Selection playback failed: " + message)

    def _edit_options(self):
        rate = self.rate.currentText()
        return dict(
            sample_rate=None if rate == "Keep original" else int(rate.split()[0]),
            mono=self.channels.currentText() == "Mono",
            bit_depth=int(self.depth.currentText().split("-")[0]),
        )

    def _export_selection(self):
        if self.busy:
            return
        try:
            region = self._selected_region()
            suffix = output_suffix(self.selected_file, self.output_format.currentText())
        except ValueError as exc:
            self._set_status(str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export selected region",
            str(self.output_dir / (self.selected_file.stem + "_selection" + suffix)),
            f"Audio (*{suffix})",
        )
        if not path:
            return
        source, options = self.selected_file, self._edit_options()
        self._start_edit(lambda: [export_region(source, Path(path), region, **options)])

    def _split_audio(self):
        if self.busy or self.selected_file is None:
            return
        cursor = self.editor.plot.position / 1000
        if self.editor.plot.preview is None or not 0 < cursor < self.editor.plot.preview["seconds"]:
            self._set_status("Place the cursor inside the recording before splitting.")
            return
        path = QFileDialog.getExistingDirectory(
            self, "Save the two split files", str(self.output_dir)
        )
        if not path:
            return
        source, options, fmt = (
            self.selected_file,
            self._edit_options(),
            self.output_format.currentText(),
        )
        self._start_edit(
            lambda: split_recording(source, Path(path), cursor, output_format=fmt, **options)
        )

    def _start_edit(self, operation):
        self.busy = True
        self.convert_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.editor.region_controls.setEnabled(False)
        self._set_status("Writing new audio files…")
        self._submit("edit", None, operation, self.conversion_pool)

    def _finish_edit(self, result):
        self.busy = False
        self.convert_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.editor.region_controls.setEnabled(self.selected_file is not None)
        if isinstance(result, dict) and "error" in result:
            self._set_status("Audio export failed")
            QMessageBox.warning(self, "Could not export audio", result["error"])
        else:
            self._set_status("Saved " + ", ".join(path.name for path in result))

    def _mark_selection_start(self):
        self.editor.region_controls.start.setValue(self.editor.plot.position / 1000)

    def _mark_selection_end(self):
        self.editor.region_controls.end.setValue(self.editor.plot.position / 1000)

    def _show_help(self):
        from .help_dialog import HelpDialog

        dialog = HelpDialog(self)
        dialog.exec()

    def _analyze(self):
        path = self.selected_file
        if path is None or path in self.analysis_pending:
            return
        self.analysis_pending.add(path)
        self.editor.analyze_button.setEnabled(False)
        self._set_status("Checking audio…")
        self._submit("analysis", path, lambda: self.analyzer.analyze(path))

    def _export_report(self):
        if self.report is None:
            self._set_status("Select a file and run audio checks first")
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save audio report", self.selected_file.stem + "_analysis.json", "JSON (*.json)"
        )
        if destination:
            try:
                Path(destination).write_text(
                    json.dumps(self.report, indent=2, allow_nan=False) + "\n"
                )
                self._set_status("Analysis report saved")
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Could not save report", str(exc))

    def _toggle_play(self):
        if self.region_player.active:
            if self.region_player.clip is None:
                self.region_player.stop()
                self._set_status("Selection playback cancelled")
            else:
                self.region_player.toggle()
            return
        if not self.editor.play_button.isEnabled():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def _media_status(self, status):
        ready = status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
            QMediaPlayer.MediaStatus.EndOfMedia,
        )
        self.editor.play_button.setEnabled(ready and self.selected_file is not None)
        self.editor.seek_slider.setEnabled(ready and self.player.duration() > 0)

    def _playback_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState and not self.region_player.active:
            if self.pending_source_seek is not None:
                position, self.pending_source_seek = self.pending_source_seek, None
                self.player.setPosition(position)
        icon = "pause.svg" if state == QMediaPlayer.PlaybackState.PlayingState else "play.svg"
        self.editor.play_button.setIcon(QIcon(str(ASSET_DIR / icon)))

    def _position_changed(self, position):
        if self.region_player.active:
            return
        # AVFoundation can report zero for a seek while the source is paused.
        if (
            self.pending_source_seek is not None
            and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        ):
            position = self.pending_source_seek
        self._display_position(position)

    def _display_position(self, position):
        if not self.editor.seek_slider.isSliderDown():
            self.editor.seek_slider.setValue(round(position))
        self.editor.time_label.setText(f"{clock(position)} / {clock(self.player.duration())}")
        self.editor.plot.position = position
        if (
            self.editor.plot.preview
            and self.editor.follow.isChecked()
            and self.editor.plot.window_seconds
        ):
            span = self.editor.plot.visible_seconds()
            if not self.editor.plot.offset <= position / 1000 < self.editor.plot.offset + span:
                self.editor.timeline_scroll.setValue(round(position / 1000 // span * span * 1000))
        if hasattr(self, "annotation_time"):
            self.annotation_time.setText(
                f"{self.selected_file.name if self.selected_file else 'No file selected'} · {clock(position)}"
            )
        self.editor.plot.update()

    def _duration_changed(self, duration):
        self.editor.seek_slider.setRange(0, max(0, duration))
        self._position_changed(self.player.position())

    def _player_error(self, error, message):
        self.editor.play_button.setEnabled(False)
        self._set_status("Playback unavailable · try converting to WAV")
        self.editor.play_button.setToolTip(message)

    @staticmethod
    def _display_path(path):
        try:
            return "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            return str(path)

    def _select_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Save converted audio to", str(self.output_dir)
        )
        if path:
            self.output_dir = Path(path)
            self.output_label.setText(self._display_path(self.output_dir))

    def _start_conversion(self):
        if self.busy:
            return
        if not self.files:
            self._set_status("Add files to start converting")
            return
        rate = self.rate.currentText()
        options = dict(
            sample_rate=None if rate == "Keep original" else int(rate.split()[0]),
            mono=self.channels.currentText() == "Mono",
            bit_depth=int(self.depth.currentText().split("-")[0]),
            output_format=self.output_format.currentText(),
        )
        files, destination = list(self.files), self.output_dir
        try:
            check_destination(destination)
        except OSError as exc:
            self._set_status("Destination unavailable · choose another folder")
            QMessageBox.warning(
                self,
                "Destination unavailable",
                f"Cannot write to {destination}.\n{exc}\n\nChoose another folder. Your queue and source files are unchanged.",
            )
            return
        self.busy = True
        self.convert_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.progress.setValue(0)
        self._set_status("Converting…")

        def run():
            def progress(current, total, path, result):
                self.events.progress.emit(current, total, result)

            return self.converter.batch_convert(
                files, destination, progress_callback=progress, **options
            )

        self._submit("conversion", None, run, self.conversion_pool)

    def _progress(self, current, total, result):
        self.progress.setValue(round(100 * current / total))
        self.table.set_status(current - 1, "Exported" if result["success"] else "Failed")
        self._set_status(f"Converting {current} / {total}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy:
            self._set_status("Wait for the conversion to finish before closing")
            event.ignore()
            return
        self._closing = True
        self.detail_timer.stop()
        self.region_player.close()
        self.player.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.conversion_pool.shutdown(wait=False, cancel_futures=True)
        # Running callbacks still own this object until their results arrive.
        event.accept()
