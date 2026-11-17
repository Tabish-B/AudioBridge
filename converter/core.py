"""
Audio Converter Core Module

Handles audio conversion using FFmpeg
"""

import subprocess
from pathlib import Path
from typing import Optional, Tuple
from .inspector import AudioInspector
from .verifier import ConversionVerifier
from .ffmpeg_utils import check_ffmpeg


class AudioConverter:
    def __init__(self):
        self.ffmpeg_path = check_ffmpeg()
        self.inspector = AudioInspector()
        self.verifier = ConversionVerifier()

    def convert(self, input_path: Path, output_path: Path, sample_rate: Optional[int] = None, mono: bool = False, bit_depth: int = 16) -> Tuple[int, str]:
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        metadata = self.inspector.inspect(input_path)
        if metadata.get("error"):
            return 1, f"Inspection failed: {metadata['error']}"

        if not metadata.get("codec") or metadata.get("codec") == "none":
            return 1, "This file does not contain an audio stream. Cannot convert to audio format."

        cmd = [str(self.ffmpeg_path), "-nostdin", "-hide_banner", "-i", str(input_path), "-map", "0:a?"]
        
        if bit_depth == 16:
            cmd.extend(["-acodec", "pcm_s16le"])
        elif bit_depth == 24:
            cmd.extend(["-acodec", "pcm_s24le"])
        else:
            return 1, f"Unsupported bit depth: {bit_depth}"

        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])
        if mono:
            cmd.extend(["-ac", "1"])

        cmd.append(str(output_path))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()

            if result.returncode != 0:
                error_msg = f"FFmpeg failed with exit code {result.returncode}"
                if stderr:
                    error_msg += f": {stderr}"
                if stdout:
                    error_msg += f" | stdout: {stdout}"
                return result.returncode, error_msg

            return result.returncode, stderr
        except subprocess.TimeoutExpired:
            return 1, "FFmpeg conversion timed out (file may be too large or corrupted)"
        except Exception as e:
            return 1, f"Conversion error: {str(e)}"

    def convert_with_verification(self, input_path: Path, output_path: Path, sample_rate: Optional[int] = None, mono: bool = False, bit_depth: int = 16) -> dict:
        if output_path.exists():
            return {"success": False, "output_path": output_path, "error": f"Output file already exists: {output_path}", "verification": None}

        exit_code, error_msg = self.convert(input_path, output_path, sample_rate, mono, bit_depth)
        verification = self.verifier.verify(output_path, exit_code)

        if not verification["success"]:
            return {"success": False, "output_path": output_path, "error": verification.get("error", error_msg), "verification": verification}

        warnings = []
        metadata = self.inspector.inspect(output_path)
        inspection_warnings = self.inspector.check_unusual_characteristics(metadata)
        if inspection_warnings:
            warnings.extend(inspection_warnings)

        try:
            input_size = input_path.stat().st_size
            output_size = output_path.stat().st_size
            if output_size > input_size * 2:
                warnings.append(f"Output file is {output_size / input_size:.1f}x larger than input (WAV is uncompressed)")
        except Exception:
            pass

        return {"success": True, "output_path": output_path, "error": None, "verification": verification, "warning": "; ".join(warnings) if warnings else None}

    def get_unique_output_path(self, output_dir: Path, base_name: str) -> Path:
        output_dir = Path(output_dir)
        base_name = Path(base_name)
        if base_name.suffix.lower() != ".wav":
            base_name = base_name.with_suffix(".wav")
        output_path = output_dir / base_name
        if not output_path.exists():
            return output_path
        counter = 1
        while True:
            new_name = f"{base_name.stem}_{counter}.wav"
            new_path = output_dir / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def batch_convert(self, input_files: list, output_dir: Path, sample_rate: Optional[int] = None, mono: bool = False, bit_depth: int = 16, progress_callback=None) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        successful = 0
        failed = 0

        for i, input_path in enumerate(input_files):
            input_path = Path(input_path)
            if not self.inspector.is_supported(input_path):
                result = {"success": False, "input_path": input_path, "output_path": None, "error": f"Unsupported file format: {input_path.suffix}"}
                results.append(result)
                failed += 1
                if progress_callback:
                    progress_callback(i + 1, len(input_files), input_path, result)
                continue

            output_path = self.get_unique_output_path(output_dir, input_path.stem)
            result = self.convert_with_verification(input_path, output_path, sample_rate, mono, bit_depth)
            result["input_path"] = input_path
            results.append(result)

            if result["success"]:
                successful += 1
            else:
                failed += 1

            if progress_callback:
                progress_callback(i + 1, len(input_files), input_path, result)

        return {"total": len(input_files), "successful": successful, "failed": failed, "results": results}
