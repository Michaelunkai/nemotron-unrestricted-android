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
    center_x, center_y = 307, 205
    maximum = ((CANVAS - center_x) ** 2 + (CANVAS - center_y) ** 2) ** 0.5
    for y in range(CANVAS):
        for x in range(CANVAS):
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5 / maximum
            if distance < 0.38:
                color = lerp((38, 60, 120), (16, 24, 61), distance / 0.38)
            elif distance < 0.74:
                color = lerp((16, 24, 61), (8, 13, 36), (distance - 0.38) / 0.36)
            else:
                color = lerp((8, 13, 36), (3, 5, 14), min(1, (distance - 0.74) / 0.26))
            pixels[x, y] = color
    draw = ImageDraw.Draw(image)
    for x, y, radius in ((242, 264, 6), (780, 232, 5), (842, 708, 6), (216, 772, 4)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(182, 216, 255))
    box = (158, 158, 866, 866)
    draw.ellipse(box, outline=(21, 47, 75), width=52)
    draw.ellipse(box, outline=(215, 255, 117), width=26)
    draw.arc(box, 38, 190, fill=(98, 246, 208), width=26)
    draw.arc(box, 190, 305, fill=(54, 200, 255), width=26)
    draw.arc(box, 305, 398, fill=(139, 124, 255), width=26)
    draw.arc((202, 158, 880, 882), 28, 210, fill=(111, 247, 211), width=10)
    draw.arc((166, 156, 858, 858), 218, 318, fill=(255, 255, 255), width=7)
    hexagon = [(302, 512), (406, 328), (618, 328), (722, 512), (618, 696), (406, 696)]
    draw.polygon(hexagon, fill=(11, 27, 49))
    draw.line(hexagon + [hexagon[0]], fill=(24, 47, 73), width=40, joint="curve")
    draw.line(hexagon + [hexagon[0]], fill=(98, 246, 208), width=16, joint="curve")
    n_path = [(414, 632), (414, 392), (610, 632), (610, 392)]
    draw.line(n_path, fill=(240, 255, 249), width=56, joint="curve")
    draw.line((414, 392, 610, 632), fill=(207, 255, 112), width=18)
    nodes = (
        (512, 158, (215, 255, 117)), (866, 512, (82, 238, 208)),
        (512, 866, (54, 200, 255)), (158, 512, (156, 140, 255)),
    )
    for x, y, color in nodes:
        draw.ellipse((x - 26, y - 26, x + 26, y + 26), fill=color)
    for line in ((512, 204, 512, 252), (820, 512, 772, 512), (512, 820, 512, 772), (204, 512, 252, 512)):
        draw.line(line, fill=(244, 255, 249), width=14)
    draw.line((772, 184, 772, 244), fill=(215, 255, 117), width=14)
    draw.line((742, 214, 802, 214), fill=(215, 255, 117), width=14)
    draw.line((772, 196, 772, 232), fill=(255, 255, 255), width=6)
    draw.line((754, 214, 790, 214), fill=(255, 255, 255), width=6)
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
