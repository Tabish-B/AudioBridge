"""Regression checks for the player and background work. No audio is played aloud."""

import os
import sys

if sys.platform == "darwin":
    os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from converter.preview import build_preview
from ui.studio import AudioBridgeGUI


def wait_for(condition, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        if condition():
            return
        QTest.qWait(10)
    raise AssertionError("Timed out waiting for the app")


class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.path = self.base / "tone.wav"
        sf.write(self.path, 0.2 * np.sin(np.arange(16000 * 3) * 2 * np.pi * 440 / 16000), 16000)
        self.window = AudioBridgeGUI()
        self.window.audio.setMuted(True)
        self.window.region_player.audio.setMuted(True)
        self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.window.pool.shutdown(wait=True)
        self.window.conversion_pool.shutdown(wait=True)
        self.window.region_player.pool.shutdown(wait=True)
        QApplication.processEvents()
        self.temp.cleanup()

    def load(self):
        self.window.add_files([self.path])
        wait_for(
            lambda: (
                self.window.editor.plot.preview is not None
                and self.window.editor.play_button.isEnabled()
            )
        )

    def test_single_click_player_pause_seek_speed_and_volume(self):
        self.load()
        w = self.window
        QTest.mouseClick(w.editor.play_button, Qt.MouseButton.LeftButton)
        wait_for(lambda: w.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        wait_for(lambda: w.player.position() > 80)
        QTest.mouseClick(w.editor.play_button, Qt.MouseButton.LeftButton)
        wait_for(lambda: w.player.playbackState() == QMediaPlayer.PlaybackState.PausedState)
        w.player.setPosition(1500)
        wait_for(lambda: abs(w.player.position() - 1500) < 100)
        w.editor.speed.setCurrentIndex(3)
        self.assertEqual(w.player.playbackRate(), 1.5)
        w.editor.volume.setValue(30)
        self.assertAlmostEqual(w.audio.volume(), 0.3, places=2)

    def test_slow_preview_does_not_block_clicks_or_duplicate_work(self):
        calls = []

        def slow_preview(path, settings=None):
            calls.append(path)
            time.sleep(0.3)
            return build_preview(path, settings)

        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        with patch("ui.studio.build_preview", slow_preview):
            self.window.add_files([self.path])
            for _ in range(10):
                self.window._on_select()
            QTest.mouseClick(self.window.audit_button, Qt.MouseButton.LeftButton)
            wait_for(
                lambda: not self.window.audit_busy and self.window.editor.plot.preview is not None
            )
        timer.stop()
        self.assertEqual(calls, [self.path.resolve()])
        self.assertGreater(len(ticks), 10)
        prepared = self.window.editor.plot.preview
        for _ in range(10):
            self.window.editor.view.setCurrentText("Spectrogram")
            self.window.editor.view.setCurrentText("Waveform")
        self.assertIs(self.window.editor.plot.preview, prepared)

    def test_stale_preview_does_not_replace_selection(self):
        first = build_preview(self.path)
        second_path = self.base / "second.wav"
        sf.write(second_path, np.zeros(8000), 8000)
        self.window.add_files([self.path, second_path])
        self.window.table.setCurrentRow(1)
        wait_for(lambda: self.window.editor.plot.preview is not None)
        current = self.window.editor.plot.preview
        self.window._finished("preview", self.path.resolve(), first)
        self.assertIs(self.window.editor.plot.preview, current)
        self.assertEqual(self.window.selected_file, second_path.resolve())

    def test_conversion_is_16khz_mono_and_does_not_overwrite(self):
        self.load()
        self.window.output_dir = self.base / "exports"
        for name in ("tone.wav", "tone_1.wav"):
            QTest.mouseClick(self.window.convert_button, Qt.MouseButton.LeftButton)
            wait_for(lambda: not self.window.busy)
            info = sf.info(self.window.output_dir / name)
            self.assertEqual((info.samplerate, info.channels, info.subtype), (16000, 1, "PCM_16"))
        self.assertEqual(self.window.table.status(0), "Exported")
        self.assertIn("Verified output", self.window.output_summary.text())

    def test_remove_and_clear_stop_playback(self):
        self.load()
        self.window._remove_file()
        self.assertEqual(self.window.files, [])
        self.assertFalse(self.window.editor.play_button.isEnabled())
        self.assertIsNone(self.window.editor.plot.preview)
        self.window.add_files([self.path])
        self.window._clear_files()
        self.assertIsNone(self.window.selected_file)

    def test_zoom_scroll_seek_and_spectrogram(self):
        self.load()
        w = self.window
        prepared = dict(w.editor.plot.preview)
        prepared["seconds"] = 300
        w._show_preview(prepared)
        w.editor.zoom.setCurrentIndex(2)
        self.assertEqual(w.editor.timeline_scroll.maximum(), 180000)
        w.editor.follow.setChecked(False)
        w.editor.timeline_scroll.setValue(150000)
        self.assertEqual(w.editor.plot.offset, 150)
        self.assertEqual(w.editor.plot.visible_seconds(), 120)
        w.editor.view.setCurrentText("Spectrogram")
        QApplication.processEvents()
        self.assertFalse(w.editor.spectrum_legend.isHidden())
        self.assertIsNotNone(w.editor.plot.image)
        image = w.editor.plot.grab().toImage()
        self.assertFalse(image.isNull())
        w.editor.zoom.setCurrentIndex(0)
        self.assertEqual(w.editor.timeline_scroll.maximum(), 0)
        self.assertEqual(w.editor.plot.visible_seconds(), 300)

    def test_small_windows_reflow_without_control_overlap(self):
        self.load()
        self.window._audit()
        wait_for(lambda: not self.window.audit_busy)
        self.window.editor.view.setCurrentText("Spectrogram")
        from PySide6.QtWidgets import QBoxLayout

        for width, height in [(420, 550), (640, 600), (800, 600), (1024, 768), (1400, 950)]:
            self.window.resize(width, height)
            QTest.qWait(80)
            self.assertEqual(self.window.width(), width)
            self.assertEqual(self.window.pages.widget(0).horizontalScrollBar().maximum(), 0)
            self.assertEqual(
                self.window.body.direction(),
                QBoxLayout.Direction.TopToBottom
                if width < 1100
                else QBoxLayout.Direction.LeftToRight,
            )
            # Scrollable content may be taller than the viewport, but its controls cannot overlap.
            controls = [
                widget
                for widget in [
                    self.window.editor.plot,
                    self.window.editor.timeline_scroll,
                    self.window.editor.follow,
                    self.window.editor.seek_slider,
                    self.window.editor.metrics,
                ]
                if not widget.isHidden()
            ]
            for first, second in zip(controls, controls[1:]):
                self.assertLessEqual(first.geometry().bottom(), second.geometry().top())
            self.assertGreaterEqual(self.window.editor.plot.width(), 200)
            self.assertGreaterEqual(self.window.editor.plot.height(), 130)
            self.assertEqual(self.window.sidebar.isHidden(), width < 950)

    def test_signal_checks_selected_file_and_queue(self):
        self.load()
        w = self.window
        w._audit()
        wait_for(lambda: not w.audit_busy)
        self.assertEqual(len(w.audit_results), 1)
        self.assertNotIn("error", w.audit_results[0])
        self.assertIn("flags", w.audit_results[0])

    def test_stereo_waveform_preview_renders_both_channels(self):
        left = 0.4 * np.sin(2 * np.pi * 440 * np.arange(16000) / 16000)
        stereo = self.base / "stereo.wav"
        sf.write(stereo, np.column_stack([left, -left]), 16000, subtype="FLOAT")
        self.window.add_files([stereo])
        self.window.table.setCurrentRow(1)
        wait_for(lambda: self.window.editor.plot.preview is not None)
        preview = self.window.editor.plot.preview
        self.assertEqual(preview["low"].shape[0], 2)
        self.assertTrue(preview["channel_diagnostics"]["mono_cancellation_risk"])
        self.assertFalse(self.window.editor.plot.grab().toImage().isNull())

    def test_drag_selection_timestamp_editing_and_zoom(self):
        self.load()
        w = self.window
        plot = w.editor.plot
        QTest.mousePress(plot, Qt.MouseButton.LeftButton, pos=QPoint(30, 40))
        QTest.mouseMove(plot, QPoint(plot.width() - 30, 40), delay=30)
        QTest.mouseRelease(plot, Qt.MouseButton.LeftButton, pos=QPoint(plot.width() - 30, 40))
        self.assertIsNotNone(plot.selection)
        self.assertGreater(
            w.editor.region_controls.end.value(), w.editor.region_controls.start.value()
        )
        w.editor.region_controls.start.setValue(0.25)
        w.editor.region_controls.end.setValue(0.75)
        self.assertEqual(plot.selection, (0.25, 0.75))
        w._zoom_by(0.5)
        self.assertAlmostEqual(plot.visible_seconds(), 1.5)
        wait_for(lambda: plot.detail is not None)
        self.assertLessEqual(len(plot.detail["low"]), 12000)
        w._clear_selection()
        self.assertIsNone(plot.selection)

    def test_spectral_modes_and_applied_settings(self):
        self.load()
        w = self.window
        for mode in ["Mel spectrogram", "MFCC", "Spectrogram"]:
            w.editor.view.setCurrentText(mode)
            wait_for(
                lambda mode=mode: (
                    w.editor.plot.preview is not None
                    and w.editor.plot.preview["spectral_settings"].mode == mode
                    and not w.editor.plot.spectral_loading
                )
            )
            self.assertFalse(w.editor.plot.image.isNull())
        controls = w.editor.spectral_controls
        controls.fft.setCurrentText("2048")
        controls.hop.setValue(512)
        controls.window.setCurrentText("Blackman")
        controls.frequency_min.setValue(100)
        controls.frequency_max.setValue(4000)
        controls.scale.setCurrentText("Logarithmic")
        w._apply_spectral()
        wait_for(
            lambda: (
                w.editor.plot.preview is not None
                and w.editor.plot.preview["spectral_settings"].fft_size == 2048
            )
        )
        self.assertEqual(w.editor.plot.preview["spectral_settings"].hop_length, 512)
        self.assertEqual(w.editor.plot.preview["frequency_ticks"][-1], 4000)
        controls.hop.setValue(8192)
        w._apply_spectral()
        self.assertIn("Hop length", w.status.text())

    def test_selection_playback_is_an_exact_clip(self):
        self.load()
        w = self.window
        w.editor.region_controls.set_region(0.2, 0.6)
        w._play_selection()
        wait_for(lambda: w.region_player.clip is not None)
        info = sf.info(w.region_player.clip)
        self.assertEqual(info.frames, 6400)
        self.assertEqual(w.player.source().toLocalFile(), str(self.path.resolve()))
        wait_for(lambda: not w.region_player.active)
        self.assertAlmostEqual(w.editor.plot.position, 600, delta=20)
        w._toggle_play()
        wait_for(lambda: w.player.position() >= 600)
        self.assertLess(w.player.position(), 1500)
        w.player.pause()

    def test_region_export_and_split_from_controls(self):
        self.load()
        w = self.window
        w.editor.region_controls.set_region(0.2, 0.8)
        destination = self.base / "selected.wav"
        with patch("ui.studio.QFileDialog.getSaveFileName", return_value=(str(destination), "")):
            w._export_selection()
        wait_for(lambda: not w.busy)
        self.assertEqual(sf.info(destination).frames, 9600)
        w.editor.plot.position = 1000
        with patch(
            "ui.studio.QFileDialog.getExistingDirectory", return_value=str(self.base / "split")
        ):
            w._split_audio()
        wait_for(lambda: not w.busy)
        parts = sorted((self.base / "split").glob("*.wav"))
        self.assertEqual(len(parts), 2)
        self.assertEqual(sum(sf.info(path).frames for path in parts), sf.info(self.path).frames)

    def test_advanced_editor_reflows_with_expanded_controls(self):
        self.load()
        w = self.window
        w._set_page(2)
        w.editor.spectral_controls.body.show()
        for width, height in [(420, 600), (640, 600), (1024, 768), (1400, 950)]:
            w.resize(width, height)
            QTest.qWait(100)
            self.assertEqual(w.pages.widget(2).horizontalScrollBar().maximum(), 0)
            controls = [
                w.editor.plot,
                w.editor.seek_slider,
                w.editor.metrics,
                w.editor.region_controls,
            ]
            for first, second in zip(controls, controls[1:]):
                self.assertLessEqual(first.geometry().bottom(), second.geometry().top())
        w._set_page(0)
        self.assertTrue(w.editor.region_controls.isHidden())

    def test_import_notices_identify_duplicate_and_unsupported_files(self):
        self.load()
        unknown = self.base / "notes.pdf"
        unknown.write_text("Not audio")
        self.window.add_files([self.path, unknown])
        self.assertIn("already queued", self.window.import_notice.text())
        self.assertIn("notes.pdf", self.window.import_notice.text())
        self.assertEqual(len(self.window.files), 1)

    def test_unavailable_destination_keeps_queue_and_source(self):
        self.load()
        original = self.path.read_bytes()
        with (
            patch("ui.studio.check_destination", side_effect=OSError("Drive disconnected")),
            patch("ui.studio.QMessageBox.warning") as warning,
        ):
            self.window._start_conversion()
        self.assertFalse(self.window.busy)
        self.assertEqual(len(self.window.files), 1)
        self.assertEqual(self.path.read_bytes(), original)
        warning.assert_called_once()
        self.assertIn("Destination unavailable", self.window.status.text())


if __name__ == "__main__":
    unittest.main()
