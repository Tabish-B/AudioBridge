# Using AudioBridge V4

[← Project overview](../README.md) · [Spectral methods](METHODS.md)

## Conversion studio

Add files, import the supported files directly inside a folder, or drag files onto the window. Import notices identify duplicate, missing, and unsupported files. Decode errors identify the recording that failed; they don't remove other queued files.

Choose the output format separately from processing settings:

| Format | Encoding |
| --- | --- |
| WAV | Uncompressed 16-bit or 24-bit PCM |
| FLAC | Lossless 16-bit or 24-bit |
| MP3 | LAME quality level 2 |
| AIFF | Uncompressed 16-bit or 24-bit PCM |
| Keep original | Re-encode into WAV, FLAC, MP3, M4A, AAC, AIFF/AIF, or Opus, matching the source container |

**Keep source settings** preserves sample rate and channels; PCM depth is selected separately for WAV, FLAC, and AIFF. The settings summary shows the selected depth. For MP3 and other lossy outputs, PCM depth is disabled because those codecs don't use PCM bit depth. **ASR input** sets 16 kHz, mono, and 16-bit PCM where applicable. **Archive** sets 48 kHz and 24-bit while keeping source channels. Resampling does not recover lost information. Lossy exports are re-encoded; a preserved container is not a byte-for-byte copy.

Exports default to `~/Downloads/AudioBridge`. Existing batch outputs receive numbered names. If the destination is unavailable, choose another folder and retry; the queue is retained. FFmpeg codecs depend on your installation. OGG is accepted as input but isn't offered as an export in this build.

## Audio editor

Use the sidebar or the compact page picker, or click **Advanced editor** in the studio. The editor and studio share one selected recording, playback state, and plot.

- **Navigate:** Full recording shows the whole file. Choose a time window to reveal the horizontal scrollbar. Use + / − or Ctrl/Command + mouse wheel for continuous zoom.
- **Inspect close up:** waveform windows of 30 seconds or less are decoded separately after a short debounce. Longer views use the whole-file envelope.
- **Select:** drag in either direction across the plot. The highlight and start/end fields stay in sync. A single click moves the cursor.
- **Enter times:** start/end fields use seconds with six displayed decimals. Export rounds those timestamps to source sample boundaries.
- **Play selection:** prepares a temporary 24-bit PCM clip containing only the selected samples. The full recording stays loaded separately. The main Play button and Space pause/resume the clip; seeking or clearing the selection returns to the full source.
- **Export selection:** writes the highlighted region using the current export settings. Choose a new filename; existing files are rejected.
- **Split at cursor:** writes two files into the selected folder. Existing names receive a numbered split suffix. Both halves are prepared before publication; the original is untouched.

Lossless exports preserve the selected sample boundaries before any requested resampling. Lossy encoders can add padding. Selection playback uses temporary disk space and can take a moment to prepare for large regions. There is no destructive delete, overwrite-source operation, undo stack, or automatic session recovery in V4.

## Spectral views

Choose **Spectrogram**, **Mel spectrogram**, or **MFCC**. Open **Spectral settings**, then **Apply analysis settings**. **Export view PNG** saves the full-recording image with time and frequency/coefficient axes; the PNG metadata includes source name, duration, and analysis settings. The PNG contains the rendered color image, not a numeric feature matrix.

| Control | Effect |
| --- | --- |
| FFT size | 256–8192 samples; changes frequency/time resolution |
| Hop length | 64 samples through FFT size; sets spacing between frames |
| Window | Hann, Hamming, Blackman, or Rectangular |
| Min/max frequency | Restricts the analyzed/displayed band; max 0 follows display Nyquist |
| dB bounds | Controls color mapping in spectrogram and Mel views |
| Linear/log frequency | Controls the standard spectrogram axis; logarithmic view excludes DC |
| Mel bands | 8–128 triangular filters |
| MFCC count | Number of coefficients, including coefficient 0; cannot exceed Mel bands |

Mel has its own frequency spacing. MFCC uses a coefficient axis and a signed coefficient color scale, so linear/log and dB controls are disabled when they don't apply. If Mel bands are narrower than the available FFT bins, increase FFT size, reduce the band count, or widen the frequency range.

Parameter changes are applied together in a background worker. An older result cannot replace a newer request. The visible legend describes the last applied analysis, not un-applied edits in the controls. See [Methods](METHODS.md) before comparing these views with another feature extractor.

## Measurements and dataset tools

**Signal checks** measures duration, rate, channels, peak/RMS in dBFS, crest factor, near-full-scale samples, and quiet-window percentage. Choose the selected recording or full queue; export the same results as CSV. Flags use explicit screening thresholds and are not speech detection or an ASR quality score.

After conversion, the footer lists the verified output codec, sample rate, and channel count for each successful file.
