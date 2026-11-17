"""Sample-aligned region export. All edits write new files."""

import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg_utils import check_ffmpeg
from .formats import codec_options, output_suffix
from .inspector import AudioInspector


@dataclass(frozen=True)
class AudioRegion:
    start: float
    end: float

    def sample_bounds(self, rate, duration):
        if not all(math.isfinite(value) for value in (self.start, self.end)):
            raise ValueError("Selection timestamps must be finite.")
        if not 0 <= self.start < self.end <= duration + 0.000001:
            raise ValueError("Choose a start before the end, within the recording.")
        first, last = round(self.start * rate), round(self.end * rate)
        if last <= first:
            raise ValueError("Select at least one source sample.")
        return first, last


def check_destination(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=directory):
        pass
    return directory


def _publish(staged, destination):
    # Exclusive creation protects existing files even if another export races us.
    created = False
    try:
        with destination.open("xb") as target:
            created = True
            with staged.open("rb") as source:
                shutil.copyfileobj(source, target, 1024 * 1024)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def export_region(source, destination, region, *, sample_rate=None, mono=False, bit_depth=16):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Choose a new output file; the source recording cannot be replaced.")
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination.name}. Choose another name.")
    info = AudioInspector().inspect(source)
    if info.get("error"):
        raise ValueError(info["error"])
    first, last = region.sample_bounds(info["sample_rate"], info["duration"])
    check_destination(destination.parent)
    with tempfile.TemporaryDirectory(prefix=".audiobridge-", dir=destination.parent) as folder:
        staged = Path(folder) / ("region" + destination.suffix)
        command = [
            str(check_ffmpeg()),
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-af",
            f"atrim=start_sample={first}:end_sample={last},asetpts=PTS-STARTPTS",
        ]
        command += codec_options(destination.suffix.lower(), bit_depth)
        if sample_rate:
            command += ["-ar", str(sample_rate)]
        if mono:
            command += ["-ac", "1"]
        result = subprocess.run(
            command + [str(staged)], capture_output=True, text=True, timeout=600
        )
        if result.returncode:
            raise ValueError(result.stderr.strip() or "Region export failed.")
        _publish(staged, destination)
    return destination


def split_recording(source, directory, cursor, *, output_format="WAV", **options):
    source = Path(source)
    info = AudioInspector().inspect(source)
    if info.get("error"):
        raise ValueError(info["error"])
    if not math.isfinite(cursor) or not 0 < cursor < info["duration"]:
        raise ValueError("Place the cursor inside the recording before splitting.")
    directory = check_destination(directory)
    suffix = output_suffix(source, output_format)
    pair = [directory / f"{source.stem}_part{index}{suffix}" for index in (1, 2)]
    counter = 1
    while any(path.exists() for path in pair):
        pair = [directory / f"{source.stem}_split{counter}_part{index}{suffix}" for index in (1, 2)]
        counter += 1
    published = []
    with tempfile.TemporaryDirectory(prefix=".audiobridge-split-", dir=directory) as folder:
        staged = [Path(folder) / path.name for path in pair]
        for destination, region in zip(
            staged, [AudioRegion(0, cursor), AudioRegion(cursor, info["duration"])]
        ):
            export_region(source, destination, region, **options)
        try:
            for temporary, destination in zip(staged, pair):
                _publish(temporary, destination)
                published.append(destination)
        except Exception:
            for destination in published:
                destination.unlink(missing_ok=True)
            raise
    return pair
