"""Check exported samples, split boundaries, and source protection."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from converter.regions import AudioRegion, export_region, split_recording
from converter.waveform import waveform_window


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "source.wav"
        self.rate = 8000
        self.data = np.sin(2 * np.pi * 100 * np.arange(self.rate * 2) / self.rate) * 0.5
        sf.write(self.source, self.data, self.rate, subtype="PCM_24")
        self.original = self.source.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_export_matches_exact_source_sample_range(self):
        destination = self.base / "cut.wav"
        export_region(self.source, destination, AudioRegion(0.250125, 0.750125), bit_depth=24)
        actual, rate = sf.read(destination)
        original, _ = sf.read(self.source)
        np.testing.assert_array_equal(actual, original[2001:6001])
        self.assertEqual(rate, self.rate)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_split_reassembles_source_and_keeps_existing_outputs(self):
        outputs = split_recording(self.source, self.base, 0.333125, bit_depth=24)
        combined = np.concatenate([sf.read(path)[0] for path in outputs])
        np.testing.assert_array_equal(combined, sf.read(self.source)[0])
        again = split_recording(self.source, self.base, 1, bit_depth=24)
        self.assertFalse(set(outputs) & set(again))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_invalid_regions_and_existing_destinations_are_preserved(self):
        for region in [
            AudioRegion(1, 0),
            AudioRegion(-1, 1),
            AudioRegion(0, 3),
            AudioRegion(0, float("nan")),
            AudioRegion(0, 0.000001),
        ]:
            with self.subTest(region=region), self.assertRaises(ValueError):
                export_region(self.source, self.base / "invalid.wav", region)
        existing = self.base / "existing.wav"
        existing.write_bytes(b"keep this")
        with self.assertRaises(FileExistsError):
            export_region(self.source, existing, AudioRegion(0, 1))
        self.assertEqual(existing.read_bytes(), b"keep this")
        with self.assertRaises(ValueError):
            export_region(self.source, self.source, AudioRegion(0, 1))

    def test_detail_window_is_bounded_and_resolves_local_signal(self):
        detail = waveform_window(self.source, 0.5, 0.1, self.rate)
        self.assertEqual(detail["start"], 0.5)
        self.assertAlmostEqual(detail["seconds"], 0.1, places=5)
        self.assertLessEqual(len(detail["low"]), 12000)
        self.assertGreater(detail["high"].max(), 0.49)


if __name__ == "__main__":
    unittest.main()
