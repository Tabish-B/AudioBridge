# AudioBridge

A professional cross-platform audio conversion and analysis tool designed for researchers, audio engineers, and ML practitioners. Convert any audio or video file to WAV format with customizable settings, visualize waveforms, and analyze audio quality metrics.

## Features

- **Modern GUI**: Figma-inspired dark theme with 3-column layout
- **File Queue**: Upload and manage multiple files for batch conversion
- **Waveform Preview**: Embedded waveform visualization for quick quality inspection
- **Audio Analysis**: Built-in quality metrics (SNR, dynamic range, RMS, peak level)
- **Cross-Platform Support**: Works on Windows, macOS, and Linux
- **Wide Format Support**: Converts MP3, M4A, AAC, FLAC, OGG, OPUS, MP4, MKV, AVI, MOV, MTS, and more
- **Non-Destructive**: Original files are never modified
- **Batch Processing**: Convert multiple files at once
- **Customizable Settings**: Sample rate, channels, bit depth
- **Verification**: Ensures conversions complete successfully

## Installation

### Prerequisites

- Python 3.8 or higher
- FFmpeg (for audio conversion)
- numpy, matplotlib, scipy (for audio analysis)

#### Installing FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.

### Installing Python Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### GUI Application

```bash
python audio_converter.py
```

## Audio Analysis Features

AudioBridge provides the following analysis capabilities useful for ASR and audio repair work:

- **Waveform Visualization**: Visualize audio waveform for quality inspection
- **Quality Metrics**:
  - SNR (Signal-to-Noise Ratio) estimation
  - Dynamic range measurement
  - RMS (Root Mean Square) level
  - Peak level detection
  - Duration and sample rate information
  - Channel count

These metrics are essential for:
- Pre-processing decisions for ASR models
- Audio quality assessment before repair
- Comparing audio source quality
- Validating audio after restoration work

## Project Structure

```
AudioBridge/
├── audio_converter.py          # Main GUI application
├── converter/
│   ├── __init__.py
│   ├── core.py                  # Conversion logic
│   ├── inspector.py             # Audio inspection
│   ├── verifier.py              # Conversion verification
│   ├── analyzer.py              # Audio analysis module
│   └── ffmpeg_utils.py          # FFmpeg detection
├── requirements.txt              # Python dependencies
├── README.md                    # This file
└── LICENSE                      # MIT License
```

## Supported Formats

### Audio Formats
WAV, MP3, M4A, AAC, FLAC, OGG, OPUS, AMR, WMA, AIFF, AU, AC3, DTS, MP2, and more

### Video Formats
MP4, MKV, AVI, MOV, WMV, FLV, WEBM, MTS, M2TS, TS, MPG, MPEG, 3GP, ASF, RM, VOB, MXF, and more

## Conversion Settings

- **Output Format**: WAV (PCM 16-bit or 24-bit)
- **Sample Rate**: Keep original, 16 kHz, 22.05 kHz, or 44.1 kHz
- **Channels**: Keep original, mono, or stereo
- **Bit Depth**: 16-bit or 24-bit

## Repository

GitHub: https://github.com/Tabish-B/AudioBridge

## License

MIT License - see [LICENSE](LICENSE) file for details.

## FFmpeg License

This application uses FFmpeg, which is licensed under the GNU General Public License version 2.0 (or later).

## Author

Tabish Butt

## Contact

- GitHub: [Tabish-B](https://github.com/Tabish-B)
- Email: tabishbutt700@gmail.com
