"""Numerical checks against SciPy's independent STFT and DCT implementations."""

import unittest
from dataclasses import replace

import numpy as np
from scipy.fft import dct
from scipy.signal import spectrogram

from converter.spectral import SpectralAccumulator, SpectralSettings, mel_filterbank, spectral_image


class SpectralTests(unittest.TestCase):
    def setUp(self):
        self.rate = 8000
        self.signal = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(8000) / self.rate)
        self.settings = SpectralSettings()

    def reference(self, settings):
        return spectrogram(
            self.signal,
            fs=self.rate,
            window=settings.window,
            nperseg=settings.fft_size,
            noverlap=settings.fft_size - settings.hop_length,
            detrend=False,
            scaling="density",
        )

    def test_streamed_stft_preserves_overlap_across_arbitrary_blocks(self):
        settings = replace(self.settings, hop_length=192, window="hamming")
        accumulator = SpectralAccumulator(self.rate, 1, settings)
        for block in np.array_split(self.signal, 71):
            accumulator.consume(block)
        frequencies, times, power = self.reference(settings)
        expected = np.zeros_like(accumulator.values)
        indices = (times * accumulator.columns).astype(int)
        np.maximum.at(expected.T, indices, power.T)
        np.testing.assert_allclose(accumulator.values, expected, rtol=1e-6, atol=1e-12)
        self.assertEqual(accumulator.frame_count, len(times))
        self.assertEqual(frequencies[np.argmax(expected[:, indices[2]])], 1000)

    def test_psd_integrates_to_known_tone_power(self):
        accumulator = SpectralAccumulator(self.rate, 1, self.settings)
        accumulator.consume(self.signal)
        values = accumulator.finish()
        column = np.argmax(values.max(axis=0))
        power = np.sum(10 ** (values[:, column] / 10)) * self.rate / self.settings.fft_size
        self.assertAlmostEqual(power, 0.5**2 / 2, places=5)

    def test_mel_filters_and_mfcc_match_reference_dct(self):
        settings = replace(self.settings, mode="MFCC", mel_bands=40)
        filters, centers = mel_filterbank(self.rate, settings)
        self.assertEqual(filters.shape, (40, 513))
        self.assertTrue(np.all(np.diff(centers) > 0))
        accumulator = SpectralAccumulator(self.rate, 1, settings)
        accumulator.consume(self.signal)
        _, times, power = self.reference(settings)
        coefficients = dct(
            10 * np.log10(np.maximum(filters @ power, 1e-12)), type=2, norm="ortho", axis=0
        )[:13]
        expected = np.zeros_like(accumulator.values)
        indices = (times * accumulator.columns).astype(int)
        np.add.at(expected.T, indices, coefficients.T)
        np.testing.assert_allclose(accumulator.values, expected, rtol=1e-6, atol=1e-5)
        values = accumulator.finish()
        self.assertEqual(values.shape[0], 13)
        self.assertTrue(np.isfinite(values).all())

    def test_linear_log_frequency_and_db_controls_change_pixels(self):
        accumulator = SpectralAccumulator(self.rate, 1, self.settings)
        accumulator.consume(self.signal)
        values = accumulator.finish()
        linear, ticks, _ = spectral_image(values, accumulator.frequencies, self.rate, self.settings)
        logarithmic, log_ticks, _ = spectral_image(
            values,
            accumulator.frequencies,
            self.rate,
            replace(self.settings, frequency_scale="Logarithmic"),
        )
        narrow, _, _ = spectral_image(
            values,
            accumulator.frequencies,
            self.rate,
            replace(self.settings, db_min=-40, db_max=-5),
        )
        self.assertEqual(ticks, [0, 2000, 4000])
        self.assertGreater(log_ticks[0], 0)
        self.assertFalse(np.array_equal(linear, logarithmic))
        self.assertFalse(np.array_equal(linear, narrow))

    def test_invalid_settings_and_empty_mel_bands_are_rejected(self):
        for settings in [
            replace(self.settings, hop_length=2048),
            replace(self.settings, db_min=0, db_max=-20),
            replace(self.settings, frequency_max=5000),
            replace(self.settings, mfcc_count=65),
        ]:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                settings.validate(self.rate)
        with self.assertRaises(ValueError):
            mel_filterbank(48000, replace(self.settings, fft_size=256, mel_bands=128))


if __name__ == "__main__":
    unittest.main()
