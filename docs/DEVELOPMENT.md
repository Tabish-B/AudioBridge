# Development

## Local checks

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
```

Qt playback tests are muted and need an available media backend. macOS uses the native AVFoundation backend. Other platforms use Qt's default backend; headless Linux tests use the offscreen platform. macOS is the validated platform for this release.

## Responsibilities

| Module | Responsibility |
| --- | --- |
| `converter/spectral.py` | Validated parameters, streaming STFT, Mel filters, MFCC, raster mapping |
| `converter/annotations.py` | Versioned, path-safe JSON annotation document |
| `converter/preview.py` | Bounded whole-file decode and display summaries |
| `converter/waveform.py` | Close-up waveform decode |
| `converter/regions.py` | Sample bounds, staged export, exclusive publication, two-part split |
| `ui/editor_panel.py` | Editor view and signals |
| `ui/audio_plot.py` | Painting, selection gestures, zoom gestures |
| `ui/annotation_timeline.py` | Clickable, time-aligned annotation tier overview |
| `ui/spectral_export.py` | Full-recording spectral PNG with axes and analysis metadata |
| `ui/spectral_controls.py`, `ui/region_controls.py` | Input controls and validation boundaries |
| `ui/region_playback.py` | Temporary selection clips and media lifecycle |
| `ui/studio.py` | Application layout, queued work, player coordination, and dataset workflows |

Numeric processing doesn't import Qt. Workers return data through queued Qt signals; UI changes stay on the main thread. Preview requests include immutable settings so stale work cannot replace a newer parameter choice. Detail requests are debounced. The window still coordinates several workflows; separating the existing audit and annotation pages further is reasonable future cleanup, not a claim of a finished plugin architecture.

## Validation

Tests cover numerical STFT agreement across arbitrary chunks, known-tone PSD scaling, Mel and MFCC conventions, invalid settings, content beyond two minutes, exact lossless trims and splits, collision protection, codec round trips, region playback, drag selection, reflow at 420–1400 px, and editor/worker interactions. Linting checks undefined/unused names, import order, and common error-prone Python patterns. They don't establish platform compatibility or replace user testing.

## Screenshots

```bash
python examples/capture_studio.py
```

Screenshots render the actual Qt widgets offscreen with generated audio; they do not contain private recordings or model results. App version is defined in `version.py`.

## Branding assets

`assets/icons/AppIcon.appiconset` retains the supplied square macOS icon catalog; macOS applies its own mask when it displays a bundled app icon. Qt masks the runtime icon with the rounded silhouette from `assets/audiobridge.png`, which is also used in the sidebar and README. `assets/icons/AudioBridge.ico` provides Windows icon sizes for executable packaging. The selected supplied splash art is `assets/splash.png`, center-cropped at display time for a desktop startup panel. It closes when the workspace is ready, with no forced delay. `ui/resources.py` resolves these paths for source and bundled runtimes.
