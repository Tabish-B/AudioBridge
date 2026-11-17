"""Regression checks for the player and background work. No audio is played aloud."""

import os
import sys
if sys.platform == 'darwin':
    os.environ.setdefault('QT_MEDIA_BACKEND', 'darwin')
else:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from PySide6.QtCore import Qt, QTimer
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
    raise AssertionError('Timed out waiting for the app')


class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.path = self.base / 'tone.wav'
        sf.write(self.path, .2 * np.sin(np.arange(16000 * 3) * 2 * np.pi * 440 / 16000), 16000)
        self.window = AudioBridgeGUI()
        self.window.audio.setMuted(True)
        self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.window.show()

    def tearDown(self):
        self.window.player.stop()
        self.window.pool.shutdown(wait=True)
        self.window.conversion_pool.shutdown(wait=True)
        QApplication.processEvents()
        self.window.close()
        self.temp.cleanup()

    def load(self):
        self.window.add_files([self.path])
        wait_for(lambda: self.window.plot.preview is not None and self.window.play_button.isEnabled())

    def test_single_click_player_pause_seek_speed_and_volume(self):
        self.load()
        w = self.window
        QTest.mouseClick(w.play_button, Qt.MouseButton.LeftButton)
        wait_for(lambda: w.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        wait_for(lambda: w.player.position() > 80)
        QTest.mouseClick(w.play_button, Qt.MouseButton.LeftButton)
        wait_for(lambda: w.player.playbackState() == QMediaPlayer.PlaybackState.PausedState)
        w.player.setPosition(1500)
        wait_for(lambda: abs(w.player.position() - 1500) < 100)
        w.speed.setCurrentIndex(3)
        self.assertEqual(w.player.playbackRate(), 1.5)
        w.volume.setValue(30)
        self.assertAlmostEqual(w.audio.volume(), .3, places=2)

    def test_slow_preview_does_not_block_clicks_or_duplicate_work(self):
        calls = []
        def slow_preview(path):
            calls.append(path)
            time.sleep(.3)
            return build_preview(path)
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        with patch('ui.studio.build_preview', slow_preview):
            self.window.add_files([self.path])
            for _ in range(10):
                self.window._on_select()
            QTest.mouseClick(self.window.analyze_button, Qt.MouseButton.LeftButton)
            wait_for(lambda: self.window.report is not None and self.window.plot.preview is not None)
        timer.stop()
        self.assertEqual(calls, [self.path.resolve()])
        self.assertGreater(len(ticks), 10)
        prepared = self.window.plot.preview
        for _ in range(10):
            self.window.view.setCurrentText('Spectrogram')
            self.window.view.setCurrentText('Waveform')
        self.assertIs(self.window.plot.preview, prepared)

    def test_stale_preview_does_not_replace_selection(self):
        first = build_preview(self.path)
        second_path = self.base / 'second.wav'
        sf.write(second_path, np.zeros(8000), 8000)
        self.window.add_files([self.path, second_path])
        self.window.table.setCurrentRow(1)
        wait_for(lambda: self.window.plot.preview is not None)
        current = self.window.plot.preview
        self.window._finished('preview', self.path.resolve(), first)
        self.assertIs(self.window.plot.preview, current)
        self.assertEqual(self.window.selected_file, second_path.resolve())

    def test_conversion_is_16khz_mono_and_does_not_overwrite(self):
        self.load()
        self.window.output_dir = self.base / 'exports'
        for name in ('tone.wav', 'tone_1.wav'):
            QTest.mouseClick(self.window.convert_button, Qt.MouseButton.LeftButton)
            wait_for(lambda: not self.window.busy)
            info = sf.info(self.window.output_dir / name)
            self.assertEqual((info.samplerate, info.channels, info.subtype), (16000, 1, 'PCM_16'))
        self.assertEqual(self.window.table.status(0), 'Exported')

    def test_remove_and_clear_stop_playback(self):
        self.load()
        self.window._remove_file()
        self.assertEqual(self.window.files, [])
        self.assertFalse(self.window.play_button.isEnabled())
        self.assertIsNone(self.window.plot.preview)
        self.window.add_files([self.path])
        self.window._clear_files()
        self.assertIsNone(self.window.selected_file)
        self.assertIsNone(self.window.report)

    def test_zoom_scroll_seek_and_spectrogram(self):
        self.load()
        w = self.window
        prepared = dict(w.plot.preview)
        prepared['seconds'] = 300
        w._show_preview(prepared)
        w.zoom.setCurrentIndex(2)
        self.assertEqual(w.timeline_scroll.maximum(), 180000)
        w.follow.setChecked(False)
        w.timeline_scroll.setValue(150000)
        self.assertEqual(w.plot.offset, 150)
        self.assertEqual(w.plot.visible_seconds(), 120)
        w.view.setCurrentText('Spectrogram')
        QApplication.processEvents()
        self.assertFalse(w.spectrum_legend.isHidden())
        self.assertIsNotNone(w.plot.image)
        image = w.plot.grab().toImage()
        self.assertFalse(image.isNull())
        w.zoom.setCurrentIndex(0)
        self.assertEqual(w.timeline_scroll.maximum(), 0)
        self.assertEqual(w.plot.visible_seconds(), 300)

    def test_small_windows_reflow_without_control_overlap(self):
        self.load()
        self.window._analyze()
        wait_for(lambda: self.window.report is not None)
        self.window.view.setCurrentText('Spectrogram')
        from PySide6.QtWidgets import QBoxLayout
        for width, height in [(420, 550), (640, 600), (800, 600), (1024, 768), (1400, 950)]:
            self.window.resize(width, height)
            QTest.qWait(80)
            self.assertEqual(self.window.width(), width)
            self.assertEqual(self.window.pages.widget(0).horizontalScrollBar().maximum(), 0)
            self.assertEqual(self.window.body.direction(), QBoxLayout.Direction.TopToBottom if width < 1100 else QBoxLayout.Direction.LeftToRight)
            # Scrollable content may be taller than the viewport, but its controls cannot overlap.
            controls = [widget for widget in [self.window.plot, self.window.timeline_scroll, self.window.follow, self.window.seek_slider, self.window.metrics] if not widget.isHidden()]
            for first, second in zip(controls, controls[1:]):
                self.assertLessEqual(first.geometry().bottom(), second.geometry().top())
            self.assertGreaterEqual(self.window.plot.width(), 200)
            self.assertGreaterEqual(self.window.plot.height(), 130)
            self.assertEqual(self.window.sidebar.isHidden(), width < 950)

    def test_research_audit_and_segment_annotations(self):
        self.load()
        w = self.window
        w._audit()
        wait_for(lambda: not w.audit_busy)
        self.assertEqual(len(w.audit_results), 1)
        self.assertNotIn('error', w.audit_results[0])
        w.player.setPosition(200)
        w._mark_start()
        w.player.setPosition(1200)
        w.annotation_label.setText('background noise')
        w._mark_end()
        self.assertEqual(w.annotations[0]['start_seconds'], .2)
        self.assertEqual(w.annotations[0]['end_seconds'], 1.2)
        destination = self.base / 'annotations.csv'
        w._write_csv(destination, w.annotations, ['file', 'start_seconds', 'end_seconds', 'label'])
        self.assertIn('background noise', destination.read_text())


if __name__ == '__main__':
    unittest.main()
