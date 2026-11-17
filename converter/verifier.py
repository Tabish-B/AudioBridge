"""
Conversion Verifier Module

Verifies that audio conversions completed successfully:
- Check process exit code
- Confirm output exists and is not empty
- Confirm output can be decoded
"""

import subprocess
from pathlib import Path
from typing import Dict

from .ffmpeg_utils import check_ffmpeg, check_ffprobe


class ConversionVerifier:
    """Verify audio conversion success."""

    def __init__(self):
        """Initialize the verifier."""
        self.ffmpeg_path = check_ffmpeg()
        self.ffprobe_path = check_ffprobe()

    def verify(self, output_path: Path, exit_code: int) -> Dict:
        """
        Verify that a conversion completed successfully.

        Args:
            output_path: Path to the output file
            exit_code: Exit code from the conversion process

        Returns:
            Dictionary with:
            - success: bool
            - error: str (if verification failed)
            - checks: dict with individual check results
        """
        checks = {}

        # Check 1: Exit code
        checks["exit_code"] = exit_code == 0
        if exit_code != 0:
            return {
                "success": False,
                "error": f"Conversion process failed with exit code {exit_code}",
                "checks": checks,
            }

        # Check 2: Output file exists
        output_path = Path(output_path)
        checks["file_exists"] = output_path.exists()
        if not output_path.exists():
            return {
                "success": False,
                "error": f"Output file does not exist: {output_path}",
                "checks": checks,
            }

        # Check 3: Output file is not empty
        file_size = output_path.stat().st_size
        checks["file_not_empty"] = file_size > 0
        if file_size == 0:
            return {
                "success": False,
                "error": f"Output file is empty: {output_path}",
                "checks": checks,
            }

        # Check 4: Output can be decoded (using FFprobe)
        checks["can_decode"] = self._can_decode(output_path)
        if not checks["can_decode"]:
            return {
                "success": False,
                "error": f"Output file cannot be decoded: {output_path}",
                "checks": checks,
            }

        # All checks passed
        return {"success": True, "error": None, "checks": checks}

    def _can_decode(self, path: Path) -> bool:
        """
        Check if a file can be decoded using FFprobe.

        Returns True if FFprobe can successfully read the file.
        """
        try:
            cmd = [
                str(self.ffprobe_path),
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                str(path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            # Success if exit code is 0 and we can parse JSON
            if result.returncode == 0:
                import json

                json.loads(result.stdout)
                return True

            return False

        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def verify_batch(self, results: list) -> Dict:
        """
        Verify a batch of conversion results.

        Args:
            results: List of (output_path, exit_code) tuples

        Returns:
            Dictionary with:
            - total: int
            - successful: int
            - failed: int
            - details: list of verification results
        """
        total = len(results)
        successful = 0
        failed = 0
        details = []

        for output_path, exit_code in results:
            verification = self.verify(output_path, exit_code)
            details.append({"path": str(output_path), "verification": verification})

            if verification["success"]:
                successful += 1
            else:
                failed += 1

        return {"total": total, "successful": successful, "failed": failed, "details": details}
