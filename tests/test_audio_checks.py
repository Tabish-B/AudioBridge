"""Check the measurements against signals with known levels."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from converter import AudioAnalyzer
from converter.preview import build_preview


class AudioChecksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.analyzer = AudioAnalyzer()

    def tearDown(self):
        self.temp.cleanup()

    def test_quiet_clipped_and_tone_sections(self):
        rate = 16000
        tone = .3 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)
        path = self.base / 'sections.wav'
        sf.write(path, np.concatenate([np.zeros(rate), tone, np.ones(rate)]), rate, subtype='FLOAT')
        report = self.analyzer.analyze(path)
        self.assertAlmostEqual(report['quiet_percent'], 100 / 3, places=2)
        self.assertAlmostEqual(report['clipping_percent'], 100 / 3, places=2)
        self.assertEqual(report['peak_dbfs'], 0)
        self.assertEqual(report['duration'], 3)

    def test_opposite_stereo_channels_do_not_cancel_in_analysis(self):
        path = self.base / 'stereo.wav'
        data = np.column_stack([np.full(800, .5), np.full(800, -.5)])
        sf.write(path, data, 8000, subtype='FLOAT')
        report = self.analyzer.analyze(path)
        self.assertEqual(report['channels'], 2)
        self.assertAlmostEqual(report['rms'], .5)
        self.assertEqual(report['quiet_percent'], 0)

    def test_empty_and_nonfinite_audio(self):
        for name, data in [('empty', np.array([])), ('invalid', np.array([float('nan')]))]:
            path = self.base / (name + '.wav')
            sf.write(path, data, 16000, subtype='FLOAT')
            self.assertIn('error', self.analyzer.analyze(path))

    def test_silence_preview_has_finite_pixels_and_bounded_envelope(self):
        path = self.base / 'silence.wav'
        sf.write(path, np.zeros(16000 * 4), 16000)
        preview = build_preview(path)
        self.assertLessEqual(len(preview['low']), 1200)
        self.assertTrue(np.isfinite(preview['spectrum']).all())
        self.assertEqual(preview['seconds'], 4)


if __name__ == '__main__':
    unittest.main()
