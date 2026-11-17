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
    lows, highs = [], []
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
                "1",
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
                raw = process.stdout.read(chunk_samples * 4)
                if not raw:
                    break
                data = np.frombuffer(raw, dtype="<f4")
                if not np.isfinite(data).all():
                    raise ValueError("This recording contains non-finite audio samples.")
                padded = np.pad(data, (0, (-len(data)) % bucket), mode="edge").reshape(-1, bucket)
                lows.append(padded.min(axis=1))
                highs.append(padded.max(axis=1))
                spectral.consume(data)
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
    return dict(
        metadata=metadata,
        low=np.concatenate(lows),
        high=np.concatenate(highs),
        seconds=samples / rate,
        rate=rate,
        features=values,
        spectrum=rgb,
        spectral_settings=settings,
        frequency_ticks=ticks,
        spectral_legend=legend,
        frames=spectral.frame_count,
    )
