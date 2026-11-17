"""
Audio Inspector Module

Uses FFprobe to inspect audio files and extract metadata:
- Sample rate
- Channel count
- Duration
- Codec information
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from .ffmpeg_utils import check_ffprobe


class AudioInspector:
    """Inspect audio files using FFprobe."""

    SUPPORTED_AUDIO_EXTS = {
        ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".amr",
        ".wma", ".m4p", ".aiff", ".aif", ".au", ".ra", ".ac3", ".dts",
        ".mp2", ".mp1", ".m4b", ".m4r", ".gsm", ".dsd", ".dsf", ".dff"
    }
    SUPPORTED_VIDEO_EXTS = {
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".mts", ".m2ts", ".ts", ".mpg", ".mpeg", ".3gp", ".3g2",
        ".asf", ".rm", ".rmvb", ".vob", "divx", ".xvid", ".mxf",
        ".f4v", ".ogv", ".m4v", ".dv", ".swf"
    }

    def __init__(self):
        """Initialize the inspector."""
        self.ffprobe_path = check_ffprobe()

    def is_audio_file(self, path: Path) -> bool:
        """Check if a file is a supported audio format."""
        return path.suffix.lower() in self.SUPPORTED_AUDIO_EXTS

    def is_video_file(self, path: Path) -> bool:
        """Check if a file is a supported video format."""
        return path.suffix.lower() in self.SUPPORTED_VIDEO_EXTS

    def is_supported(self, path: Path) -> bool:
        """Check if a file is a supported audio or video format."""
        return self.is_audio_file(path) or self.is_video_file(path)

    def inspect(self, path: Path) -> Dict:
        """
        Inspect an audio/video file and return metadata.

        Returns a dictionary with:
        - sample_rate: int (Hz)
        - channels: int
        - duration: float (seconds)
        - codec: str
        - format: str
        - is_video: bool
        - error: str (if inspection failed)
        """
        path = Path(path)

        if not path.exists():
            return {"error": f"File not found: {path}"}

        if not self.is_supported(path):
            return {"error": f"Unsupported file format: {path.suffix}"}

        try:
            # Use FFprobe to get stream information
            cmd = [
                str(self.ffprobe_path),
                "-v", "error",
                "-show_entries", "stream=codec_type,codec_name,sample_rate,channels,duration:format=format_name,duration",
                "-of", "json",
                str(path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return {"error": f"FFprobe failed: {result.stderr.strip()}"}

            data = json.loads(result.stdout)

            # Find audio stream
            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                return {"error": "No audio stream found in file"}

            # Extract metadata
            sample_rate = int(audio_stream.get("sample_rate", 0))
            channels = int(audio_stream.get("channels", 0))
            codec = audio_stream.get("codec_name", "unknown")
            format_name = data.get("format", {}).get("format_name", "unknown")

            # Use duration from stream if available, otherwise from format
            duration = audio_stream.get("duration")
            if duration is None:
                duration = data.get("format", {}).get("duration")
            if duration:
                duration = float(duration)
            else:
                duration = 0.0

            is_video = any(
                s.get("codec_type") == "video"
                for s in data.get("streams", [])
            )

            return {
                "sample_rate": sample_rate,
                "channels": channels,
                "duration": duration,
                "codec": codec,
                "format": format_name,
                "is_video": is_video,
                "error": None
            }

        except subprocess.TimeoutExpired:
            return {"error": "FFprobe timed out"}
        except json.JSONDecodeError:
            return {"error": "Failed to parse FFprobe output"}
        except Exception as e:
            return {"error": f"Inspection error: {str(e)}"}

    def get_display_info(self, path: Path) -> Tuple[str, Optional[Dict]]:
        """
        Get human-readable display information for a file.

        Returns:
            Tuple of (display_string, metadata_dict)
        """
        metadata = self.inspect(path)

        if metadata.get("error"):
            return f"Error: {metadata['error']}", metadata

        parts = []
        parts.append(f"Format: {metadata['format']}")
        parts.append(f"Codec: {metadata['codec']}")
        parts.append(f"Sample Rate: {metadata['sample_rate']} Hz")
        parts.append(f"Channels: {metadata['channels']}")
        parts.append(f"Duration: {metadata['duration']:.2f}s")

        if metadata.get("is_video"):
            parts.append("(Video file - audio will be extracted)")

        return "\n".join(parts), metadata

    def check_unusual_characteristics(self, metadata: Dict) -> list:
        """
        Check for unusual audio characteristics and return warning messages.

        Returns a list of warning strings (empty if no issues).
        """
        warnings = []

        if metadata.get("error"):
            return [f"Inspection error: {metadata['error']}"]

        sample_rate = metadata.get("sample_rate", 0)
        channels = metadata.get("channels", 0)

        # Warn about unusual sample rates
        if sample_rate > 0 and sample_rate < 8000:
            warnings.append(f"Unusually low sample rate: {sample_rate} Hz")
        elif sample_rate > 96000:
            warnings.append(f"Unusually high sample rate: {sample_rate} Hz")

        # Warn about unusual channel counts
        if channels > 2:
            warnings.append(f"Unusual channel count: {channels} (mono or stereo recommended)")

        # Warn about very short duration
        duration = metadata.get("duration", 0)
        if duration > 0 and duration < 0.1:
            warnings.append(f"Very short duration: {duration:.2f}s")

        return warnings
