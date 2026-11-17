"""Round-trip exports through FFmpeg and inspect the resulting streams."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from converter import AudioConverter


class FormatTests(unittest.TestCase):
    def test_supported_formats_preserve_rate_and_channels_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source.wav"
            tone = 0.2 * np.sin(2 * np.pi * 440 * np.arange(24000) / 48000)
            sf.write(source, np.column_stack([tone, tone * 0.5]), 48000, subtype="PCM_24")
            converter = AudioConverter()
            for fmt, suffix, codec in [
                ("WAV", ".wav", "pcm_s24le"),
                ("FLAC", ".flac", "flac"),
                ("MP3", ".mp3", "mp3"),
                ("AIFF", ".aiff", "pcm_s24be"),
                ("Keep original", ".wav", "pcm_s24le"),
            ]:
                with self.subTest(format=fmt):
                    result = converter.batch_convert(
                        [source], base / fmt, bit_depth=24, output_format=fmt
                    )
                    self.assertEqual(result["successful"], 1, result)
                    output = result["results"][0]["output_path"]
                    self.assertEqual(output.suffix, suffix)
                    info = converter.inspector.inspect(output)
                    self.assertEqual(
                        (info["sample_rate"], info["channels"], info["codec"]), (48000, 2, codec)
                    )

    def test_asr_settings_are_independent_of_output_format(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source.wav"
            sf.write(source, np.ones((4800, 2)) * 0.1, 48000)
            converter = AudioConverter()
            result = converter.batch_convert(
                [source], base / "out", sample_rate=16000, mono=True, output_format="FLAC"
            )
            self.assertEqual(result["successful"], 1, result)
            info = converter.inspector.inspect(result["results"][0]["output_path"])
            self.assertEqual(
                (info["sample_rate"], info["channels"], info["codec"]), (16000, 1, "flac")
            )

    def test_keep_original_supported_audio_containers(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source.wav"
            sf.write(source, np.ones((4800, 2)) * 0.1, 48000)
            converter = AudioConverter()
            for suffix in (".flac", ".mp3", ".aiff", ".m4a", ".aac", ".opus"):
                with self.subTest(container=suffix):
                    original = base / ("input" + suffix)
                    code, error = converter.convert(source, original)
                    self.assertEqual(code, 0, error)
                    result = converter.batch_convert(
                        [original], base / "out", output_format="Keep original"
                    )
                    self.assertEqual(result["successful"], 1, result)
                    output = result["results"][0]["output_path"]
                    self.assertEqual(output.suffix, suffix)
                    before, after = (
                        converter.inspector.inspect(original),
                        converter.inspector.inspect(output),
                    )
                    self.assertEqual(
                        (after["sample_rate"], after["channels"]),
                        (before["sample_rate"], before["channels"]),
                    )


if __name__ == "__main__":
    unittest.main()
