"""Decode short waveform windows for useful close-up inspection."""

import subprocess

import numpy as np

from .ffmpeg_utils import check_ffmpeg


def waveform_window(path, start, seconds, rate, points=12000):
    if not 0 <= start or not 0 < seconds <= 30:
        raise ValueError("Detailed waveform windows must be between 0 and 30 seconds.")
    result = subprocess.run(
        [
            str(check_ffmpeg()),
            "-v",
            "error",
            "-nostdin",
            "-ss",
            f"{start:.9f}",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-t",
            f"{seconds:.9f}",
            "-ac",
            "1",
            "-ar",
            str(rate),
            "-f",
            "f32le",
            "pipe:1",
        ],
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip())
    data = np.frombuffer(result.stdout, dtype="<f4")
    if not len(data):
        raise ValueError("No audio in this time window.")
    step = max(1, int(np.ceil(len(data) / points)))
    blocks = np.pad(data, (0, (-len(data)) % step), mode="edge").reshape(-1, step)
    return dict(
        start=start, seconds=len(data) / rate, low=blocks.min(axis=1), high=blocks.max(axis=1)
    )
