"""Prepare small previews away from the UI thread."""

import subprocess
from pathlib import Path

import numpy as np
from scipy.signal import spectrogram

from .ffmpeg_utils import check_ffmpeg
from .inspector import AudioInspector

PREVIEW_SECONDS = 120
PREVIEW_RATE = 16000


def build_preview(path: Path):
    metadata = AudioInspector().inspect(path)
    if metadata.get('error'):
        raise ValueError(metadata['error'])
    decoded = subprocess.run(
        [str(check_ffmpeg()), '-v', 'error', '-nostdin', '-i', str(path),
         '-map', '0:a:0', '-t', str(PREVIEW_SECONDS), '-ac', '1',
         '-ar', str(PREVIEW_RATE), '-f', 'f32le', 'pipe:1'],
        capture_output=True, timeout=45,
    )
    if decoded.returncode:
        raise ValueError(decoded.stderr.decode(errors='replace').strip())
    data = np.frombuffer(decoded.stdout, dtype='<f4')
    if not len(data):
        raise ValueError('This file has no audio samples.')
    data = np.nan_to_num(data)
    # At most 1,200 vertical strokes, regardless of recording length.
    step = max(1, int(np.ceil(len(data) / 1200)))
    padded = np.pad(data, (0, (-len(data)) % step), mode='edge').reshape(-1, step)
    low, high = padded.min(axis=1), padded.max(axis=1)
    n = min(512, len(data))
    _, _, power = spectrogram(data, fs=PREVIEW_RATE, nperseg=n, noverlap=n // 2)
    db = 10 * np.log10(np.maximum(power, 1e-12))
    # Pool time bins before sending the image back to the window.
    stride = max(1, int(np.ceil(db.shape[1] / 1000)))
    db = db[:, ::stride]
    level = np.clip((db + 100) / 80, 0, 1)
    stops = np.array([[13, 21, 17], [32, 76, 64], [70, 144, 105], [184, 245, 154]], dtype=float)
    position = level * (len(stops) - 1)
    index = np.minimum(position.astype(int), len(stops) - 2)
    fraction = (position - index)[..., None]
    rgb = (stops[index] * (1 - fraction) + stops[index + 1] * fraction).astype('uint8')
    return dict(metadata=metadata, low=low, high=high,
                seconds=len(data) / PREVIEW_RATE, spectrum=np.ascontiguousarray(rgb[::-1]))
