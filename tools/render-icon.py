#!/data/data/com.termux/files/usr/bin/python
"""Render deterministic PWA PNGs from the maintained Nemotron vector design."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile

from PIL import Image, ImageDraw


ROOT = pathlib.Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "vendor/codexapp-native-npm/node_modules/codexapp/dist/icons"
SVG_SOURCE = ROOT / "artwork/icon.svg"
CANVAS = 1024


def lerp(first, second, amount):
    return tuple(round(first[index] + (second[index] - first[index]) * amount) for index in range(3))


def render():
    image = Image.new("RGB", (CANVAS, CANVAS))
    pixels = image.load()
    center_x, center_y = 348, 246
    maximum = ((CANVAS - center_x) ** 2 + (CANVAS - center_y) ** 2) ** 0.5
    for y in range(CANVAS):
        for x in range(CANVAS):
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5 / maximum
            if distance < 0.52:
                color = lerp((24, 37, 83), (10, 16, 40), distance / 0.52)
            else:
                color = lerp((10, 16, 40), (4, 7, 17), min(1, (distance - 0.52) / 0.48))
            pixels[x, y] = color
    draw = ImageDraw.Draw(image)
    box = (160, 160, 864, 864)
    draw.ellipse(box, outline=(184, 255, 106), width=36)
    draw.arc(box, 35, 220, fill=(57, 230, 197), width=36)
    draw.arc(box, 220, 395, fill=(50, 183, 255), width=36)
    draw.ellipse((222, 222, 802, 802), outline=(255, 255, 255, 46), width=6)
    hexagon = [(300, 512), (408, 324), (616, 324), (724, 512), (616, 700), (408, 700)]
    draw.polygon(hexagon, fill=(16, 34, 53), outline=(57, 230, 197))
    draw.line(hexagon + [hexagon[0]], fill=(57, 230, 197), width=20, joint="curve")
    n_path = [(408, 630), (408, 394), (616, 630), (616, 394)]
    draw.line(n_path, fill=(245, 255, 248), width=60, joint="curve")
    draw.line((408, 394, 616, 630), fill=(184, 255, 106), width=24)
    nodes = (
        (512, 160, (184, 255, 106)), (864, 512, (184, 255, 106)),
        (512, 864, (57, 230, 197)), (160, 512, (57, 230, 197)),
    )
    for x, y, color in nodes:
        draw.ellipse((x - 36, y - 36, x + 36, y + 36), fill=color)
    for line in ((512, 196, 512, 252), (828, 512, 772, 512), (512, 828, 512, 772), (196, 512, 252, 512)):
        draw.line(line, fill=(245, 255, 248), width=18)
    return image


def atomic_save(image, target, size):
    resized = image.resize((size, size), Image.Resampling.LANCZOS)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as stream:
        temporary = pathlib.Path(stream.name)
    try:
        resized.save(temporary, format="PNG", optimize=True, compress_level=9)
        temporary.chmod(0o644)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    source = render()
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for name, size in (
        ("apple-touch-icon.png", 180),
        ("pwa-192x192.png", 192),
        ("pwa-512x512.png", 512),
        ("maskable-512x512.png", 512),
    ):
        atomic_save(source, ICON_DIR / name, size)
    svg = SVG_SOURCE.read_bytes()
    for name in ("codexui-icon.svg", "pwa-icon.svg", "pwa-maskable.svg"):
        target = ICON_DIR / name
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{name}.", delete=False) as stream:
            stream.write(svg)
            temporary = pathlib.Path(stream.name)
        temporary.chmod(0o644)
        temporary.replace(target)
    digest = hashlib.sha256((ICON_DIR / "pwa-512x512.png").read_bytes()).hexdigest()
    print(f"NEMOTRON_ICON_RENDERED pwa512_sha256={digest}")


if __name__ == "__main__":
    main()
