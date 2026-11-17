"""
Audio Conversion Helper Package

A lightweight tool for converting audio files to WAV format for JRF annotators.
"""

from .core import AudioConverter
from .inspector import AudioInspector
from .verifier import ConversionVerifier
from .ffmpeg_utils import get_executable_path, check_ffmpeg, check_ffprobe

__all__ = ['AudioConverter', 'AudioInspector', 'ConversionVerifier',
           'get_executable_path', 'check_ffmpeg', 'check_ffprobe']
