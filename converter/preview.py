"""Stream a recording into bounded waveform and spectrogram summaries."""

import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np

from .ffmpeg_utils import check_ffmpeg
from .inspector import AudioInspector
from .spectral import SpectralAccumulator, SpectralSettings, spectral_image

MAX_WAVE_BINS = 12000
MAX_SPECTRUM_COLUMNS = 1600


def build_preview(path: Path, settings=None):
    settings = settings or SpectralSettings()
    metadata = AudioInspector().inspect(path)
    if metadata.get("error"):
        raise ValueError(metadata["error"])
    duration = metadata["duration"]
    if duration <= 0:
        raise ValueError("Could not determine the recording length.")
    rate = min(48000, metadata["sample_rate"])
    bucket = max(1, int(np.ceil(duration * rate / MAX_WAVE_BINS)))
    chunk_samples = max(bucket, 65536 // bucket * bucket)
    settings.validate(rate)
    spectral = SpectralAccumulator(rate, duration, settings, MAX_SPECTRUM_COLUMNS)
    channel_count = 2 if metadata["channels"] == 2 else 1
    lows, highs = [], []
    channel_squares = np.zeros(channel_count, dtype=np.float64)
    channel_sums = np.zeros(channel_count, dtype=np.float64)
    channel_peaks = np.zeros(channel_count, dtype=np.float64)
    cross_sum = 0.0
    samples = 0
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [
                str(check_ffmpeg()),
                "-v",
                "error",
                "-nostdin",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-ac",
                str(channel_count),
                "-ar",
                str(rate),
                "-f",
                "f32le",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=errors,
        )
        # A broken decoder shouldn't occupy a worker indefinitely.
        deadline = threading.Timer(180, process.kill)
        deadline.start()
        try:
            while True:
                raw = process.stdout.read(chunk_samples * channel_count * 4)
                if not raw:
                    break
                data = np.frombuffer(raw, dtype="<f4").reshape(-1, channel_count)
                if not np.isfinite(data).all():
                    raise ValueError("This recording contains non-finite audio samples.")
                channel_squares += np.sum(data.astype(np.float64) ** 2, axis=0)
                channel_sums += np.sum(data, axis=0)
                channel_peaks = np.maximum(channel_peaks, np.max(np.abs(data), axis=0))
                if channel_count == 2:
                    cross_sum += float(np.sum(data[:, 0] * data[:, 1]))
                padded = np.pad(data, ((0, (-len(data)) % bucket), (0, 0)), mode="edge")
                blocks = padded.reshape(-1, bucket, channel_count)
                lows.append(blocks.min(axis=1).T)
                highs.append(blocks.max(axis=1).T)
                spectral.consume(data.mean(axis=1))
                samples += len(data)
            code = process.wait()
            if code:
                errors.seek(0)
                raise ValueError(
                    errors.read().decode(errors="replace").strip() or "Preview decoding timed out."
                )
        finally:
            deadline.cancel()
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
    if not samples:
        raise ValueError("This file has no audio samples.")
    values = spectral.finish()
    rgb, ticks, legend = spectral_image(values, spectral.frequencies, rate, settings)
    rms = np.sqrt(channel_squares / samples)
    correlation = None
    if channel_count == 2:
        covariance = cross_sum - channel_sums[0] * channel_sums[1] / samples
        centered_squares = np.maximum(0, channel_squares - channel_sums**2 / samples)
        denom = np.sqrt(centered_squares[0] * centered_squares[1])
        correlation = float(np.clip(covariance / denom, -1, 1)) if denom else 0.0
    return dict(
        metadata=metadata,
        low=(
            np.concatenate(lows, axis=1)[0] if channel_count == 1 else np.concatenate(lows, axis=1)
        ),
        high=(
            np.concatenate(highs, axis=1)[0]
            if channel_count == 1
            else np.concatenate(highs, axis=1)
        ),
        channel_diagnostics={
            "count": channel_count,
            "peak_dbfs": (20 * np.log10(np.maximum(channel_peaks, 1e-12))).tolist(),
            "rms_dbfs": (20 * np.log10(np.maximum(rms, 1e-12))).tolist(),
            "correlation": correlation,
            "mono_cancellation_risk": correlation is not None and correlation < -0.5,
        },
        seconds=samples / rate,
        rate=rate,
        features=values,
        spectrum=rgb,
        spectral_settings=settings,
        frequency_ticks=ticks,
        spectral_legend=legend,
        frames=spectral.frame_count,
    )
