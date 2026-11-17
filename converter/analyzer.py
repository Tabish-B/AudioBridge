"""Small, local checks for deciding what an audio file needs before ASR."""

from pathlib import Path

import numpy as np
import soundfile as sf


class AudioAnalyzer:
    def load_preview(self, file_path: Path, max_seconds=120):
        # Keep previews small, even when someone opens a long recording.
        with sf.SoundFile(str(file_path)) as source:
            rate = source.samplerate
            data = source.read(
                min(len(source), int(rate * max_seconds)), dtype="float32", always_2d=True
            )
        return data.mean(axis=1), rate

    def analyze(self, file_path: Path):
        """Scan in blocks so long recordings don't have to fit in memory."""
        try:
            with sf.SoundFile(str(file_path)) as source:
                rate, channels, frames = source.samplerate, source.channels, len(source)
                if not frames:
                    return {"error": "This file has no audio samples."}
                power = 0.0
                peak = 0.0
                clipped = count = quiet_frames = total_frames = 0
                # 20 ms RMS windows; quiet is a level threshold, not speech detection.
                window = max(1, round(rate * 0.02))
                for block in source.blocks(blocksize=window, dtype="float64", always_2d=True):
                    if not np.isfinite(block).all():
                        return {"error": "This file contains non-finite audio samples."}
                    power += float(np.sum(block**2))
                    peak = max(peak, float(np.max(np.abs(block))))
                    clipped += int(np.count_nonzero(np.abs(block) >= 0.999))
                    count += block.size
                    if np.sqrt(np.mean(block**2)) < 10 ** (-40 / 20):
                        quiet_frames += len(block)
                    total_frames += len(block)
                rms = float(np.sqrt(power / count))

                def db(value):
                    return float(20 * np.log10(max(value, 1e-12)))

                return {
                    "duration": frames / rate,
                    "sample_rate": rate,
                    "channels": channels,
                    "rms": rms,
                    "peak": peak,
                    "rms_dbfs": db(rms),
                    "peak_dbfs": db(peak),
                    "crest_db": db(peak) - db(rms),
                    "clipping_percent": 100 * clipped / count,
                    "quiet_percent": 100 * quiet_frames / total_frames,
                }
        except Exception as exc:
            return {"error": str(exc)}
