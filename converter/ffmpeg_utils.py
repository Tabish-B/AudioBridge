"""
FFmpeg/FFprobe Path Detection Utility

Handles detection of FFmpeg and FFprobe executables:
- Checks for bundled executables first (for packaged app)
- Falls back to system PATH
- Cross-platform support
- Clear error messages
"""

import shutil
import sys
from pathlib import Path
from typing import Optional


def get_executable_path(executable_name: str) -> Optional[Path]:
    """
    Find the path to an executable (ffmpeg or ffprobe).

    Search order:
    1. Bundled with the application (same directory as executable)
    2. System PATH

    Args:
        executable_name: Name of the executable (e.g., 'ffmpeg', 'ffprobe')

    Returns:
        Path to the executable if found, None otherwise
    """
    # Check for bundled executable first
    if getattr(sys, 'frozen', False):
        # Running as packaged executable (PyInstaller)
        app_dir = Path(sys.executable).parent
    else:
        # Running as script (development)
        app_dir = Path(__file__).parent.parent

    # Check for executable in app directory
    bundled_path = app_dir / f"{executable_name}.exe" if sys.platform == "win32" else app_dir / executable_name
    if bundled_path.exists() and bundled_path.is_file():
        return bundled_path

    # Fall back to system PATH
    system_path = shutil.which(executable_name)
    if system_path:
        return Path(system_path)

    return None


def check_ffmpeg() -> Path:
    """
    Check if FFmpeg is available and return its path.

    Returns:
        Path to FFmpeg executable

    Raises:
        RuntimeError: If FFmpeg is not found
    """
    ffmpeg_path = get_executable_path("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError(
            "FFmpeg not found. This application requires FFmpeg to run.\n\n"
            "If you downloaded the portable version, FFmpeg should be included.\n"
            "If you built from source, please install FFmpeg:\n"
            "  Windows: Download from https://ffmpeg.org/download.html\n"
            "  macOS: brew install ffmpeg\n"
            "  Linux: apt install ffmpeg"
        )
    return ffmpeg_path


def check_ffprobe() -> Path:
    """
    Check if FFprobe is available and return its path.

    Returns:
        Path to FFprobe executable

    Raises:
        RuntimeError: If FFprobe is not found
    """
    ffprobe_path = get_executable_path("ffprobe")
    if ffprobe_path is None:
        raise RuntimeError(
            "FFprobe not found. This application requires FFprobe to run.\n\n"
            "FFprobe is included with FFmpeg. Please ensure FFmpeg is installed:\n"
            "  Windows: Download from https://ffmpeg.org/download.html\n"
            "  macOS: brew install ffmpeg\n"
            "  Linux: apt install ffmpeg"
        )
    return ffprobe_path


def get_ffmpeg_version() -> Optional[str]:
    """
    Get the FFmpeg version string.

    Returns:
        Version string if FFmpeg is available, None otherwise
    """
    try:
        ffmpeg_path = check_ffmpeg()
        import subprocess
        result = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Extract version from first line
            first_line = result.stdout.split('\n')[0]
            return first_line
    except Exception:
        pass
    return None
