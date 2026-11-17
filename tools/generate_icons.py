"""Render AudioBridge's rounded logo at native icon sizes."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ICON_SET = ROOT / "assets" / "icons" / "AppIcon.appiconset"
SIZES = {
    "icon-16.png": 16,
    "icon-16@2x.png": 32,
    "icon-32.png": 32,
    "icon-32@2x.png": 64,
    "icon-128.png": 128,
    "icon-128@2x.png": 256,
    "icon-256.png": 256,
    "icon-256@2x.png": 512,
    "icon-512.png": 512,
    "icon-512@2x.png": 1024,
}
BACKGROUND = (184, 245, 154, 255)
WAVEFORM = (23, 50, 31, 255)
SUPERSAMPLE = 4


def render_icon(size: int) -> Image.Image:
    """Draw once at high resolution, then downsample to a clean antialiased PNG."""
    scale = SUPERSAMPLE
    canvas_size = size * scale
    unit = canvas_size / 128
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
        return tuple(round(value * unit) for value in (x0, y0, x1, y1))

    draw.rounded_rectangle(box(0, 0, 128, 128), radius=round(32 * unit), fill=BACKGROUND)
    for x, top, bottom in (
        (32, 48, 80),
        (48, 32, 96),
        (64, 40, 88),
        (80, 16, 112),
        (96, 44, 84),
    ):
        draw.rounded_rectangle(
            box(x - 4, top, x + 4, bottom),
            radius=round(4 * unit),
            fill=WAVEFORM,
        )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    ICON_SET.mkdir(parents=True, exist_ok=True)
    for filename, size in SIZES.items():
        render_icon(size).save(ICON_SET / filename)

    logo = render_icon(512)
    logo.save(ROOT / "assets" / "audiobridge.png", optimize=True)
    logo.save(
        ROOT / "assets" / "icons" / "AudioBridge.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
