<p align="center">
  <img src="assets/audiobridge.png" width="72" alt="AudioBridge logo">
</p>

# AudioBridge

I built AudioBridge to make audio preparation easier: convert recordings to WAV, listen back, and check the signal before sending it to an ASR model or an audio repair pipeline. Everything runs locally with Python, Qt, and FFmpeg.

![AudioBridge conversion studio with a synthetic test recording](docs/audiobridge.png)

The screenshot uses a generated test signal, not a speech recording or an ML repair result.

## What it does

- Batch conversion from audio and video to PCM WAV
- A speech / ASR preset: 16 kHz, mono, 16-bit PCM
- A built-in player with play/pause, seek, restart, speed, and volume controls
- Waveform and spectrogram previews, with a playhead and click-to-seek
- Full-file checks for peak and RMS levels, crest factor, samples near full scale, and quiet sections
- JSON analysis reports
- File selection, folder import, and drag and drop

Decoding, analysis, and conversion run in background workers. Previews are prepared once, cached for up to four files, and reused when switching views. The queue and player use Qt widgets; plotting doesn't run Matplotlib on the UI thread.

## Run it

Use Python 3.9–3.12 and install FFmpeg, including FFprobe. On macOS, the Qt version used here requires macOS 12 or newer.

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

On Windows, install an FFmpeg build linked from [ffmpeg.org](https://ffmpeg.org/download.html) and add its `bin` directory to PATH.

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python audio_converter.py
```

The desktop interface needs a display and an audio output device. On macOS, playback uses Qt's native AVFoundation backend; other platforms use Qt's default media backend. Codec availability depends on that backend. Conversion and previews use the installed FFmpeg.

## Using the studio

1. Add files, import a folder, or drop recordings onto the window. Folder import includes supported files directly inside that folder.
2. Select a file to load its preview. Click **Play** or press Space to listen. Use the timeline to seek through the whole recording, or click the waveform to seek within the preview.
3. Choose **Waveform** or **Spectrogram**. Both show up to the first 120 seconds, downmixed and resampled to 16 kHz for display. The spectrogram covers 0–8 kHz; use the original sample rate from the analysis report when assessing the source.
4. Click **Analyze file** for measurements, then **Export JSON** to save them.
5. Pick export settings and an output folder, then convert the queue.

Exports default to `Downloads/AudioBridge`. Source files stay intact, and existing output filenames get a numbered suffix. Use **Remove**, Delete/Backspace, or **Clear all** to edit the queue. Queue changes are paused during conversion.

The speech preset is a starting point. Check your model's expected sample rate and channel count before exporting. **Keep source** preserves sample rate and channels but still writes 16-bit PCM WAV; choose 24-bit explicitly if needed.

## What the measurements mean

| Measurement | How it is calculated |
| --- | --- |
| Peak | Highest absolute sample value, reported in dBFS |
| RMS | Energy across all samples and channels, reported in dBFS |
| Crest factor | Peak level minus RMS level, in dB |
| Near full scale | Percentage of channel samples with absolute value ≥ 0.999 |
| Quiet audio | Percentage of time in 20 ms windows whose RMS is below −40 dBFS |

Analysis scans the full recording in small blocks. SoundFile handles analysis decoding; if it cannot read a format, convert the file to WAV first. The player and FFmpeg preview can support formats that the analyzer cannot read directly.

Quiet sections are measured by level, so they aren't voice activity detection. Samples near full scale can suggest clipping, but this check can't prove that a recording was clipped earlier in the chain. Crest factor isn't a measurement of a recording's complete dynamic range. Digital silence is displayed at a numerical floor of −240 dBFS.

AudioBridge doesn't estimate true SNR, transcribe speech, or run an ML repair model. It helps inspect and prepare recordings for those steps.

## Try a test recording

The demo generator makes a deterministic synthetic signal with quiet sections and a short full-scale segment. It is useful for checking the controls and measurements without using a private recording.

```bash
python examples/make_demo.py /tmp/audiobridge-demo.wav
python audio_converter.py /tmp/audiobridge-demo.wav
```

You can also pass one or more recordings as command-line arguments. To regenerate the README screenshot with synthetic audio, run `python examples/capture_studio.py`.

## Checks

```bash
python -m unittest discover -s tests -v
```

The regression suite checks single-click play/pause, seeking, speed and volume changes, UI responsiveness during slow decoding, stale preview results, analysis, queue changes, and conversion without overwriting existing exports. Playback tests are muted and need an available media backend. On Linux without a display, tests use Qt's offscreen platform.

## Project layout

```text
AudioBridge/
├── audio_converter.py       # Desktop entry point
├── ui/
│   ├── studio.py            # Workspace, player, and background jobs
│   └── theme.qss            # Styles based on the supplied HTML/CSS design
├── converter/
│   ├── core.py              # FFmpeg conversion
│   ├── inspector.py         # FFprobe metadata
│   ├── verifier.py          # Export verification
│   ├── analyzer.py          # Full-file level checks
│   ├── preview.py           # Bounded waveform / spectrogram preparation
│   └── ffmpeg_utils.py      # Executable discovery
├── assets/audiobridge.png   # App logo
├── docs/audiobridge.png     # GUI screenshot
├── examples/                # Demo signal and screenshot generator
└── tests/
```

## License and dependencies

The project code is licensed under MIT; see [LICENSE](LICENSE). Third-party libraries keep their own licenses. PySide6 is distributed under Qt's [open-source and commercial licensing options](https://doc.qt.io/qtforpython-6/licenses.html). FFmpeg is installed separately, and its license depends on the build; see [FFmpeg's license information](https://ffmpeg.org/legal.html).

Built by [Tabish Butt](https://github.com/Tabish-B). [Repository](https://github.com/Tabish-B/AudioBridge).
