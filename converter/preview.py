"""Stream a recording into bounded waveform and spectrogram summaries."""

import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np
from scipy.signal import spectrogram

from .ffmpeg_utils import check_ffmpeg
from .inspector import AudioInspector

MAX_WAVE_BINS = 12000
MAX_SPECTRUM_COLUMNS = 1600


def build_preview(path: Path):
    metadata = AudioInspector().inspect(path)
    if metadata.get('error'):
        raise ValueError(metadata['error'])
    duration = metadata['duration']
    if duration <= 0:
        raise ValueError('Could not determine the recording length.')
    rate = min(48000, metadata['sample_rate'])
    bucket = max(1, int(np.ceil(duration * rate / MAX_WAVE_BINS)))
    chunk_samples = max(bucket, 65536 // bucket * bucket)
    columns = min(MAX_SPECTRUM_COLUMNS, max(1, int(np.ceil(duration * rate / 512))))
    spectrum = np.zeros((513, columns), dtype=np.float32)
    lows, highs = [], []
    samples = 0
    tail = np.array([], dtype=np.float32)
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [str(check_ffmpeg()), '-v', 'error', '-nostdin', '-i', str(path),
             '-map', '0:a:0', '-ac', '1', '-ar', str(rate), '-f', 'f32le', 'pipe:1'],
            stdout=subprocess.PIPE, stderr=errors,
        )
        # A broken decoder shouldn't occupy a worker indefinitely.
        deadline = threading.Timer(180, process.kill)
        deadline.start()
        try:
            while True:
                raw = process.stdout.read(chunk_samples * 4)
                if not raw:
                    break
                data = np.nan_to_num(np.frombuffer(raw, dtype='<f4'))
                padded = np.pad(data, (0, (-len(data)) % bucket), mode='edge').reshape(-1, bucket)
                lows.append(padded.min(axis=1))
                highs.append(padded.max(axis=1))
                signal = np.concatenate([tail, data])
                n = min(1024, len(signal))
                _, times, power = spectrogram(signal, fs=rate, nperseg=n, noverlap=n // 2, nfft=1024)
                times += (samples - len(tail)) / rate
                indices = np.clip((times / duration * columns).astype(int), 0, columns - 1)
                # Peak pooling keeps a brief tone visible in a whole-file view.
                np.maximum.at(spectrum.T, indices, power.T)
                tail = data[-512:]
                samples += len(data)
            code = process.wait()
            if code:
                errors.seek(0)
                raise ValueError(errors.read().decode(errors='replace').strip() or 'Preview decoding timed out.')
        finally:
            deadline.cancel()
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
    if not samples:
        raise ValueError('This file has no audio samples.')
    db = 10 * np.log10(np.maximum(spectrum, 1e-12))
    level = np.clip((db + 110) / 90, 0, 1)
    stops = np.array([[13, 21, 17], [52, 40, 94], [36, 123, 137], [98, 187, 98], [240, 232, 83]], dtype=float)
    position = level * (len(stops) - 1)
    index = np.minimum(position.astype(int), len(stops) - 2)
    fraction = (position - index)[..., None]
    rgb = (stops[index] * (1 - fraction) + stops[index + 1] * fraction).astype('uint8')
    return dict(metadata=metadata, low=np.concatenate(lows), high=np.concatenate(highs),
                seconds=samples / rate, rate=rate, spectrum_db=db,
                spectrum=np.ascontiguousarray(rgb[::-1]))
