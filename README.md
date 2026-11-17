# AudioBridge

A professional cross-platform audio conversion tool designed for researchers, annotators, and audio professionals. Convert any audio or video file to WAV format with customizable settings for sample rate, channels, and bit depth.

## Features

- **Cross-Platform Support**: Works on Windows, macOS, and Linux
- **Wide Format Support**: Converts MP3, M4A, AAC, FLAC, OGG, OPUS, MP4, MKV, AVI, MOV, MTS, and more
- **Non-Destructive**: Original files are never modified
- **Batch Processing**: Convert multiple files at once
- **Customizable Settings**: Resample to 16 kHz, convert to mono, choose bit depth
- **Verification**: Ensures conversions complete successfully
- **Professional GUI**: Clean, intuitive interface for ease of use

## Installation

### Prerequisites

- Python 3.8 or higher
- FFmpeg (for audio conversion)

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

## Project Structure

```
AudioBridge/
├── audio_converter.py          # Main GUI application
├── converter/
│   ├── __init__.py
│   ├── core.py                  # Conversion logic
│   ├── inspector.py             # Audio inspection
│   ├── verifier.py              # Conversion verification
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
- **Sample Rate**: Preserve source or convert to 16 kHz
- **Channels**: Preserve source or convert to mono
- **Default Behavior**: Preserves original quality unless explicitly changed

## License

MIT License - see [LICENSE](LICENSE) file for details.

## FFmpeg License

This application uses FFmpeg, which is licensed under the GNU General Public License version 2.0 (or later).

## Author

Tabish Butt

## Contact

- GitHub: [Tabish-B](https://github.com/Tabish-B)
- Email: tabishbutt700@gmail.com
