"""
Audio Converter Core Module

Handles audio conversion using FFmpeg:
- Convert to WAV format
- Optional sample rate conversion
- Optional mono conversion
- Extract audio from video files
"""

import subprocess
from pathlib import Path
from typing import Optional, Tuple
from .inspector import AudioInspector
from .verifier import ConversionVerifier
from .ffmpeg_utils import check_ffmpeg


class AudioConverter:
    """Convert audio files to WAV format using FFmpeg."""

    def __init__(self):
        """Initialize the converter."""
        self.ffmpeg_path = check_ffmpeg()
        self.inspector = AudioInspector()
        self.verifier = ConversionVerifier()

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        sample_rate: Optional[int] = None,
        mono: bool = False,
        bit_depth: int = 16
    ) -> Tuple[int, str]:
        """
        Convert an audio/video file to WAV format.

        Args:
            input_path: Path to input file
            output_path: Path to output WAV file
            sample_rate: Target sample rate in Hz (None to preserve source)
            mono: Convert to mono if True
            bit_depth: PCM bit depth (16 or 24)

        Returns:
            Tuple of (exit_code, error_message)
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file has an audio stream
        metadata = self.inspector.inspect(input_path)
        if metadata.get("error"):
            return 1, f"Inspection failed: {metadata['error']}"

        # Check if file actually has audio
        if not metadata.get("codec") or metadata.get("codec") == "none":
            return 1, "This file does not contain an audio stream. Cannot convert to audio format."

        # Build FFmpeg command
        # Note: We use -nostdin to prevent FFmpeg from reading from stdin
        # We use -hide_banner to suppress version information
        # We do NOT use -y because we ensure output path is unique before conversion
        cmd = [
            str(self.ffmpeg_path),
            "-nostdin",
            "-hide_banner",
            "-i", str(input_path),
        ]

        # Map audio stream explicitly (important for video files with multiple streams)
        # The ? makes it optional - if no audio stream exists, conversion will fail gracefully
        cmd.extend(["-map", "0:a?"])

        # Audio codec: PCM signed 16-bit or 24-bit little-endian
        if bit_depth == 16:
            cmd.extend(["-acodec", "pcm_s16le"])
        elif bit_depth == 24:
            cmd.extend(["-acodec", "pcm_s24le"])
        else:
            return 1, f"Unsupported bit depth: {bit_depth}"

        # Sample rate conversion (if specified)
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])

        # Mono conversion (if requested)
        if mono:
            cmd.extend(["-ac", "1"])

        # Output file
        cmd.append(str(output_path))

        # Log the command for debugging
        import sys
        if getattr(sys, 'frozen', False):
            # Running as packaged app - print to console
            print(f"FFmpeg command: {' '.join(cmd)}")
        else:
            # Running as script - print to console
            print(f"FFmpeg command: {' '.join(cmd)}")

        try:
            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout per file
            )

            # Capture both stdout and stderr for debugging
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()

            # Print to console for debugging
            import sys
            if getattr(sys, 'frozen', False):
                print(f"FFmpeg exit code: {result.returncode}")
                print(f"FFmpeg stderr: {stderr}")
                print(f"FFmpeg stdout: {stdout}")

            # If FFmpeg failed, provide detailed error information
            if result.returncode != 0:
                error_msg = f"FFmpeg failed with exit code {result.returncode}"
                if stderr:
                    error_msg += f": {stderr}"
                if stdout:
                    error_msg += f" | stdout: {stdout}"
                # Add helpful context for common exit codes
                if result.returncode == 3221225781:  # 0xC0000005 - Access Violation
                    error_msg += " (Access Violation - FFmpeg crashed. This may be due to incompatible FFmpeg build or corrupted file. Try a different FFmpeg build.)"
                elif result.returncode == 4294967274:  # -22 - Invalid argument
                    error_msg += " (Invalid argument - Check file path and command)"
                return result.returncode, error_msg

            return result.returncode, stderr

        except subprocess.TimeoutExpired:
            return 1, "FFmpeg conversion timed out (file may be too large or corrupted)"
        except Exception as e:
            return 1, f"Conversion error: {str(e)}"

    def convert_with_verification(
        self,
        input_path: Path,
        output_path: Path,
        sample_rate: Optional[int] = None,
        mono: bool = False,
        bit_depth: int = 16
    ) -> dict:
        """
        Convert a file and verify the result.

        Returns:
            Dictionary with:
            - success: bool
            - output_path: Path
            - error: str (if failed)
            - verification: dict from verifier
            - warning: str (if conversion succeeded but with warnings)
        """
        # Double-check that output path doesn't exist
        if output_path.exists():
            return {
                "success": False,
                "output_path": output_path,
                "error": f"Output file already exists: {output_path}. This should not happen due to unique path generation.",
                "verification": None
            }

        # Run conversion
        exit_code, error_msg = self.convert(
            input_path, output_path, sample_rate, mono, bit_depth
        )

        # Verify result
        verification = self.verifier.verify(output_path, exit_code)

        if not verification["success"]:
            return {
                "success": False,
                "output_path": output_path,
                "error": verification.get("error", error_msg),
                "verification": verification
            }

        # Check for warnings (unusual characteristics)
        warnings = []
        metadata = self.inspector.inspect(output_path)
        inspection_warnings = self.inspector.check_unusual_characteristics(metadata)
        if inspection_warnings:
            warnings.extend(inspection_warnings)

        # Warn about file size increase (WAV is typically larger than lossy formats)
        try:
            input_size = input_path.stat().st_size
            output_size = output_path.stat().st_size
            if output_size > input_size * 2:
                warnings.append(f"Output file is {output_size / input_size:.1f}x larger than input (WAV is uncompressed)")
        except Exception:
            pass

        return {
            "success": True,
            "output_path": output_path,
            "error": None,
            "verification": verification,
            "warning": "; ".join(warnings) if warnings else None
        }

    def get_unique_output_path(self, output_dir: Path, base_name: str) -> Path:
        """
        Generate a unique output path to avoid overwriting existing files.

        If the file already exists, appends a number (e.g., file_1.wav, file_2.wav).

        Args:
            output_dir: Output directory
            base_name: Base filename (with or without extension)

        Returns:
            Unique Path object
        """
        output_dir = Path(output_dir)
        base_name = Path(base_name)

        # Ensure we have .wav extension
        if base_name.suffix.lower() != ".wav":
            base_name = base_name.with_suffix(".wav")

        output_path = output_dir / base_name

        # If file doesn't exist, return as-is
        if not output_path.exists():
            return output_path

        # Otherwise, find a unique name by appending numbers
        counter = 1
        while True:
            new_name = f"{base_name.stem}_{counter}.wav"
            new_path = output_dir / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def batch_convert(
        self,
        input_files: list,
        output_dir: Path,
        sample_rate: Optional[int] = None,
        mono: bool = False,
        bit_depth: int = 16,
        progress_callback=None
    ) -> dict:
        """
        Convert multiple files in batch.

        Args:
            input_files: List of input file paths
            output_dir: Output directory
            sample_rate: Target sample rate (None to preserve source)
            mono: Convert to mono if True
            bit_depth: PCM bit depth
            progress_callback: Optional callback(current, total, file_path, result)

        Returns:
            Dictionary with:
            - total: int
            - successful: int
            - failed: int
            - results: list of conversion results
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        successful = 0
        failed = 0

        for i, input_path in enumerate(input_files):
            input_path = Path(input_path)

            # Skip unsupported files
            if not self.inspector.is_supported(input_path):
                result = {
                    "success": False,
                    "input_path": input_path,
                    "output_path": None,
                    "error": f"Unsupported file format: {input_path.suffix}"
                }
                results.append(result)
                failed += 1

                if progress_callback:
                    progress_callback(i + 1, len(input_files), input_path, result)

                continue

            # Generate unique output path
            output_path = self.get_unique_output_path(output_dir, input_path.stem)

            # Convert with verification
            result = self.convert_with_verification(
                input_path, output_path, sample_rate, mono, bit_depth
            )
            result["input_path"] = input_path

            results.append(result)

            if result["success"]:
                successful += 1
            else:
                failed += 1

            if progress_callback:
                progress_callback(i + 1, len(input_files), input_path, result)

        return {
            "total": len(input_files),
            "successful": successful,
            "failed": failed,
            "results": results
        }
