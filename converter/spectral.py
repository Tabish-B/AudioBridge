"""Validated spectral settings and streaming STFT, Mel, and MFCC summaries."""

from dataclasses import dataclass

import numpy as np
from scipy.fft import dct
from scipy.signal import get_window


@dataclass(frozen=True)
class SpectralSettings:
    fft_size: int = 1024
    hop_length: int = 256
    window: str = "hann"
    frequency_min: float = 0
    frequency_max: float = 0  # Zero follows the display Nyquist frequency.
    db_min: float = -110
    db_max: float = -20
    frequency_scale: str = "Linear"
    mode: str = "Spectrogram"
    mel_bands: int = 64
    mfcc_count: int = 13

    def validate(self, rate):
        for name in ("fft_size", "hop_length", "mel_bands", "mfcc_count"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer.")
        if self.fft_size not in (256, 512, 1024, 2048, 4096, 8192):
            raise ValueError("FFT size must be a power of two between 256 and 8192.")
        if not 64 <= self.hop_length <= self.fft_size:
            raise ValueError("Hop length must be between 64 and the FFT size.")
        if self.window not in ("hann", "hamming", "blackman", "boxcar"):
            raise ValueError("Choose Hann, Hamming, Blackman, or Rectangular window.")
        if self.frequency_scale not in ("Linear", "Logarithmic"):
            raise ValueError("Choose linear or logarithmic frequency.")
        if self.mode not in ("Spectrogram", "Mel spectrogram", "MFCC"):
            raise ValueError("Unknown spectral view.")
        upper = self.frequency_max or rate / 2
        if not 0 <= self.frequency_min < upper <= rate / 2:
            raise ValueError(
                f"Frequency bounds must lie between 0 and {rate / 2:g} Hz, with min < max."
            )
        if not -200 <= self.db_min < self.db_max <= 20:
            raise ValueError("dB bounds must increase and lie between −200 and +20.")
        if not 8 <= self.mel_bands <= 128 or not 1 <= self.mfcc_count <= self.mel_bands:
            raise ValueError("Use 8–128 Mel bands, with MFCC count no larger than the band count.")
        return self.frequency_min, upper


def hz_to_mel(frequency):
    return 2595 * np.log10(1 + np.asarray(frequency) / 700)


def mel_to_hz(mel):
    return 700 * (10 ** (np.asarray(mel) / 2595) - 1)


def mel_filterbank(rate, settings):
    low, high = settings.validate(rate)
    points = mel_to_hz(np.linspace(hz_to_mel(low), hz_to_mel(high), settings.mel_bands + 2))
    frequencies = np.fft.rfftfreq(settings.fft_size, 1 / rate)
    rising = (frequencies[None, :] - points[:-2, None]) / (points[1:-1] - points[:-2])[:, None]
    falling = (points[2:, None] - frequencies[None, :]) / (points[2:] - points[1:-1])[:, None]
    filters = np.maximum(0, np.minimum(rising, falling))
    if np.any(filters.max(axis=1) == 0):
        raise ValueError(
            "Some Mel bands contain no FFT bins. Increase FFT size, reduce Mel bands, or widen the frequency range."
        )
    return filters, points[1:-1]


class SpectralAccumulator:
    """Keep a bounded time summary while preserving STFT overlap across blocks."""

    def __init__(self, rate, duration, settings, columns=1600):
        settings.validate(rate)
        self.rate, self.duration, self.settings = rate, duration, settings
        self.window = get_window(settings.window, settings.fft_size, fftbins=True)
        self.buffer = np.empty(0, dtype=np.float32)
        self.frame_start = 0
        self.frame_count = 0
        self.columns = max(1, min(columns, int(np.ceil(duration * rate / settings.hop_length))))
        self.filters = None
        if settings.mode == "Spectrogram":
            self.frequencies = np.fft.rfftfreq(settings.fft_size, 1 / rate)
            rows = len(self.frequencies)
        else:
            self.filters, self.frequencies = mel_filterbank(rate, settings)
            rows = settings.mfcc_count if settings.mode == "MFCC" else settings.mel_bands
        self.values = np.zeros((rows, self.columns), dtype=np.float64)
        self.counts = np.zeros(self.columns, dtype=int)

    def consume(self, data):
        self.buffer = np.concatenate([self.buffer, data])
        n, hop = self.settings.fft_size, self.settings.hop_length
        while len(self.buffer) >= n:
            count = min(128, 1 + (len(self.buffer) - n) // hop)
            frames = np.lib.stride_tricks.sliding_window_view(self.buffer, n)[::hop][:count]
            self._frames(frames)
            advance = count * hop
            self.buffer = self.buffer[advance:]
            self.frame_start += advance

    def _frames(self, frames):
        transformed = np.fft.rfft(frames * self.window, axis=1)
        power = np.abs(transformed) ** 2 / (self.rate * np.sum(self.window**2))
        power[:, 1:-1] *= 2
        times = (
            self.frame_start
            + np.arange(len(frames)) * self.settings.hop_length
            + self.settings.fft_size / 2
        ) / self.rate
        indices = np.clip((times / self.duration * self.columns).astype(int), 0, self.columns - 1)
        features = power.T
        if self.filters is not None:
            features = self.filters @ features
        if self.settings.mode == "MFCC":
            features = dct(
                10 * np.log10(np.maximum(features, 1e-12)), type=2, norm="ortho", axis=0
            )[: self.settings.mfcc_count]
            np.add.at(self.values.T, indices, features.T)
            np.add.at(self.counts, indices, 1)
        else:
            np.maximum.at(self.values.T, indices, features.T)
        self.frame_count += len(frames)

    def finish(self):
        if len(self.buffer):
            self._frames(
                np.pad(self.buffer, (0, self.settings.fft_size - len(self.buffer)))[None, :]
            )
            self.buffer = np.empty(0, dtype=np.float32)
        occupied = self.counts > 0
        if self.settings.mode == "MFCC":
            self.values[:, occupied] /= self.counts[occupied]
            # Empty time bins in tiny files follow the closest observed frame.
            if occupied.any():
                for row in self.values:
                    row[:] = np.interp(
                        np.arange(self.columns), np.flatnonzero(occupied), row[occupied]
                    )
            return self.values.astype(np.float32)
        return (10 * np.log10(np.maximum(self.values, 1e-12))).astype(np.float32)


def spectral_image(values, frequencies, rate, settings):
    """Return RGB pixels and axis/legend metadata without touching Qt."""
    low, high = settings.validate(rate)
    mode = settings.mode
    if mode == "Spectrogram":
        if settings.frequency_scale == "Logarithmic":
            low = max(low, rate / settings.fft_size)
            if low >= high:
                raise ValueError("Log frequency needs a range above the first non-zero FFT bin.")
            axis = np.geomspace(low, high, min(512, len(frequencies)))
        else:
            axis = np.linspace(low, high, min(512, len(frequencies)))
        display = np.stack([np.interp(axis, frequencies, column) for column in values.T], axis=1)
        ticks = [
            low,
            np.sqrt(low * high) if settings.frequency_scale == "Logarithmic" else (low + high) / 2,
            high,
        ]
    elif mode == "Mel spectrogram":
        display = values
        ticks = [
            float(frequencies[0]),
            float(frequencies[len(frequencies) // 2]),
            float(frequencies[-1]),
        ]
    else:
        display = values
        ticks = [0, (settings.mfcc_count - 1) / 2, settings.mfcc_count - 1]
    if mode == "MFCC":
        bound = max(1, float(np.percentile(np.abs(display), 99)))
        level = np.clip((display + bound) / (2 * bound), 0, 1)
        stops = np.array([[42, 87, 145], [235, 239, 232], [184, 65, 65]], dtype=float)
        legend = f"MFCC 0–{settings.mfcc_count - 1} · coefficient scale −{bound:.1f} to {bound:.1f} · time-bin mean"
    else:
        level = np.clip((display - settings.db_min) / (settings.db_max - settings.db_min), 0, 1)
        stops = np.array(
            [[13, 21, 17], [52, 40, 94], [36, 123, 137], [98, 187, 98], [240, 232, 83]], dtype=float
        )
        unit = "dBFS/Hz" if mode == "Spectrogram" else "dB (Mel-weighted PSD sum)"
        legend = f"{settings.db_min:g} to {settings.db_max:g} {unit} · peak per time bin"
    position = level * (len(stops) - 1)
    index = np.minimum(position.astype(int), len(stops) - 2)
    fraction = (position - index)[..., None]
    rgb = (stops[index] * (1 - fraction) + stops[index + 1] * fraction).astype("uint8")
    return np.ascontiguousarray(rgb[::-1]), ticks, legend
