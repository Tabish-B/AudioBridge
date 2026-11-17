# Changelog

## Unreleased

- Made PCM bit-depth state visible in the output summary and clarified when a selected codec doesn't use PCM depth.
- Added full-recording PNG export for spectrogram, Mel, and MFCC views, with time/value axes and analysis metadata.
- Kept playback and file shortcuts available when dropdowns or time controls have focus; text entry keeps its normal key behavior.
- Reworked annotations around waveform intervals and named tiers, with segment editing/playback and a versioned AudioBridge JSON export.
- Replaced the private macOS system-font alias with explicit UI and Indic fallback fonts.
- Regenerated app icons at native sizes to remove the soft color fringe around their edges.

## 4.0.0 — 2026-11-17

- Added a dedicated audio editor with configurable FFT size, hop length, window, frequency and dB ranges, and linear/logarithmic frequency display.
- Added Mel spectrogram and MFCC views with explicit processing conventions and appropriate axes/legends.
- Added continuous zoom, decoded close-up waveform windows, drag selection, and editable selection timestamps.
- Added exact-region playback through temporary PCM clips, selected-region export, and two-file splitting at the cursor.
- Added staged region exports and exclusive destination creation; sources and existing outputs are preserved.
- Used the supplied analysis and edge-case designs for source properties, import notices, destination errors, empty-state controls, and offline help.
- Separated the editor view, plot, controls, playback, and numeric processing into focused modules.
- Added numerical reference tests, editing/interaction tests, expanded-control reflow tests, and reproducible lint/format checks.
- Replaced the long README with a concise overview, fresh screenshots, and separate usage, methods, and development guides.

## 3.0.0 — 2026-11-17

- Added a separate output-format selector for WAV, FLAC, MP3, AIFF, and supported original audio containers.
- Made ASR settings optional; the default keeps source sample rate and channels.
- Replaced the two-minute preview cutoff with streamed whole-recording waveform and spectrogram summaries.
- Added zoomed time windows, horizontal scrolling, absolute time labels, and playback following.
- Added spectrogram frequency labels and an explicit power-density color legend.
- Made the studio reflow at smaller widths, with a compact page picker and vertical scrolling.
- Replaced duplicate sidebar actions with dataset audits and manual segment annotations, including CSV export.
- Added a shared version string, updated screenshots and documentation, and regression coverage for these changes.

## Earlier development

Earlier GUI work was committed directly to the repository without release tags or GitHub release entries.
