#!/data/data/com.termux/files/usr/bin/python
"""Deterministic no-device raster contracts for the Nemotron WebView UI."""

import argparse
import hashlib
import io
import json
import pathlib
import tempfile

from PIL import Image, ImageDraw, ImageFont


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "offdevice-ui"
WIDTH, HEIGHT = 945, 2048
EXACT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
EFFORTS = ("None", "Minimal", "Low", "Medium", "High", "Extra high", "Max")
COLORS = {
    "background": "#08090b",
    "surface": "#17181c",
    "surfaceRaised": "#24262c",
    "text": "#f7f7f8",
    "muted": "#a7a9b2",
    "border": "#3b3d45",
    "green": "#76b900",
    "danger": "#db0038",
    "dangerSurface": "#370a19",
    "safe": "#39e6c5",
}


def font(size, bold=False):
    candidates = (
        "/data/data/com.termux/files/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/data/data/com.termux/files/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def wrap(draw, value, text_font, max_width):
    lines, current = [], ""
    for word in value.split():
        candidate = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def paragraph(draw, value, x, y, max_width, text_font, fill, spacing=10):
    line_height = text_font.size + spacing
    for line in wrap(draw, value, text_font, max_width):
        draw.text((x, y), line, font=text_font, fill=fill)
        y += line_height
    return y


def base_screen(title):
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 90), fill="#050607")
    draw.text((32, 24), "13:58", font=font(34, True), fill=COLORS["text"])
    draw.text((48, 125), "‹", font=font(52), fill=COLORS["text"])
    draw.text((118, 132), title, font=font(38, True), fill=COLORS["text"])
    return image, draw, []


def element(elements, element_id, role, label, rect, **extra):
    item = {"id": element_id, "role": role, "label": label, "rect": list(rect)}
    item.update(extra)
    elements.append(item)


def checkmark(draw, x, y):
    draw.line((x, y + 13, x + 10, y + 23), fill=COLORS["green"], width=5)
    draw.line((x + 10, y + 23, x + 28, y), fill=COLORS["green"], width=5)


def render_settings():
    image, draw, elements = base_screen("Settings")
    draw.rounded_rectangle((28, 215, 917, 500), radius=24, fill=COLORS["surface"], outline=COLORS["border"], width=2)
    draw.text((62, 250), "Runtime identity", font=font(31, True), fill=COLORS["text"])
    y = paragraph(draw, f"Requested: OpenRouter · {EXACT_MODEL} · Max", 62, 305, 810, font(23), COLORS["muted"])
    paragraph(draw, "Effective: Together · provider-confirmed model · effective effort unknown", 62, y + 8, 810, font(23), COLORS["safe"])
    draw.rounded_rectangle((28, 550, 917, 1120), radius=26, fill=COLORS["dangerSurface"], outline="#ff436e", width=3)
    draw.text((62, 592), "Clean sessions and threads", font=font(34, True), fill=COLORS["text"])
    copy = (
        "Deletes inactive chat sessions and threads only after a complete, SHA-256-verified origin-private browser backup. "
        "Running work and approval-bearing sessions are always preserved. Projects, project files, plugins, skills, "
        "accounts, settings, models, memories, and project automations stay intact."
    )
    y = paragraph(draw, copy, 62, 655, 810, font(25), "#f0cbd5", 13)
    button = (62, max(930, y + 28), 883, max(930, y + 28) + 94)
    draw.rounded_rectangle(button, radius=20, fill=COLORS["danger"])
    label = "Delete all sessions and threads now"
    bbox = draw.textbbox((0, 0), label, font=font(27, True))
    draw.text(((button[0] + button[2] - bbox[2]) / 2, button[1] + 28), label, font=font(27, True), fill="white")
    element(elements, "nemotron-session-cleanup-card", "region", "Clean sessions and threads", (28, 550, 917, 1120))
    element(elements, "nemotron-session-cleanup-open", "button", label, button, destructive=True, minTouchHeight=94)
    return image, elements


def menu_base(title, subtitle):
    image, draw, elements = base_screen("New thread")
    draw.rounded_rectangle((24, 1480, 921, 1965), radius=38, fill=COLORS["surfaceRaised"], outline=COLORS["border"], width=2)
    draw.text((60, 1525), "Continue the same task without losing state", font=font(27), fill=COLORS["text"])
    draw.rounded_rectangle((35, 190, 910, 1435), radius=30, fill=COLORS["surface"], outline=COLORS["border"], width=2)
    draw.text((72, 230), title, font=font(36, True), fill=COLORS["text"])
    draw.text((72, 285), subtitle, font=font(22), fill=COLORS["muted"])
    return image, draw, elements


def render_models():
    image, draw, elements = menu_base("Select model", "Exact provider identifiers; no aliases")
    models = (
        EXACT_MODEL,
        "nousresearch/hermes-4-405b",
        "dphn/Dolphin-X1-Llama-3.1-405B",
        "meta-llama/llama-3.3-70b-instruct",
    )
    y = 355
    for index, model in enumerate(models):
        rect = (58, y, 887, y + 132)
        selected = index == 0
        draw.rounded_rectangle(rect, radius=18, fill="#242a22" if selected else COLORS["surfaceRaised"], outline=COLORS["green"] if selected else COLORS["border"], width=3 if selected else 1)
        draw.text((84, y + 28), model, font=font(24, selected), fill=COLORS["text"])
        draw.text((84, y + 72), "Verified exact selection" if selected else "Available model", font=font(19), fill=COLORS["green"] if selected else COLORS["muted"])
        if selected:
            checkmark(draw, 825, y + 45)
        element(elements, f"model-{index}", "option", model, rect, selected=selected, minTouchHeight=132)
        y += 150
    return image, elements


def render_efforts():
    image, draw, elements = menu_base("Thinking effort", "Applies to the next provider continuation")
    y = 350
    for label in EFFORTS:
        rect = (58, y, 887, y + 105)
        selected = label == "Max"
        draw.rounded_rectangle(rect, radius=16, fill="#242a22" if selected else COLORS["surfaceRaised"], outline=COLORS["green"] if selected else COLORS["border"], width=3 if selected else 1)
        draw.text((84, y + 32), label, font=font(27, selected), fill=COLORS["text"])
        if selected:
            checkmark(draw, 825, y + 34)
        element(elements, f"effort-{label.lower().replace(' ', '-')}", "option", label, rect, selected=selected, minTouchHeight=105)
        y += 120
    return image, elements


def render_command_progress():
    image, draw, elements = base_screen("Connect to my PC")
    draw.rounded_rectangle(
        (28, 230, 917, 790), radius=26, fill=COLORS["surface"],
        outline=COLORS["border"], width=2,
    )
    draw.ellipse((62, 278, 86, 302), fill=COLORS["green"])
    draw.text((112, 268), "Working", font=font(30, True), fill=COLORS["text"])
    y = paragraph(
        draw,
        "Connecting to the paired PC and verifying the exact Windows result",
        62, 335, 805, font(26), COLORS["text"], 13,
    )
    draw.rounded_rectangle(
        (62, y + 25, 883, y + 220), radius=18, fill="#09251e",
        outline=COLORS["safe"], width=2,
    )
    draw.text((88, y + 55), "Verified result", font=font(24, True), fill=COLORS["safe"])
    paragraph(
        draw,
        "The paired PC route, listener, and process identity are available and verified.",
        88, y + 100, 760, font(22), COLORS["text"], 10,
    )
    details = (62, y + 255, 883, y + 343)
    draw.rounded_rectangle(details, radius=14, fill=COLORS["surfaceRaised"], outline=COLORS["border"], width=1)
    draw.text((86, y + 278), "› Technical command and raw receipt (collapsed)", font=font(20), fill=COLORS["muted"])
    element(
        elements, "command-progress-card", "status",
        "Connecting to the paired PC and verifying the exact Windows result",
        (28, 230, 917, 790), live="polite",
    )
    element(
        elements, "command-verified-result", "status",
        "The paired PC route, listener, and process identity are available and verified.",
        (62, y + 25, 883, y + 220), verified=True,
    )
    element(
        elements, "command-technical-details", "button",
        "Technical command and raw receipt (collapsed)", details, expanded=False,
        minTouchHeight=88,
    )
    return image, elements


RENDERERS = {
    "settings": render_settings,
    "model-selector": render_models,
    "effort-menu": render_efforts,
    "command-progress": render_command_progress,
}


def encode_png(image):
    stream = io.BytesIO()
    image.save(stream, "PNG", optimize=False, compress_level=9)
    return stream.getvalue()


def build_manifest():
    manifest = {
        "schemaVersion": 1,
        "renderer": "Pillow deterministic structural raster",
        "deviceInteraction": False,
        "referenceCanvas": {"width": WIDTH, "height": HEIGHT},
        "exactModel": EXACT_MODEL,
        "efforts": list(EFFORTS),
        "colors": COLORS,
        "states": {},
    }
    images = {}
    for name, renderer in RENDERERS.items():
        image, elements = renderer()
        encoded = encode_png(image)
        images[name] = encoded
        manifest["states"][name] = {
            "file": f"{name}.png",
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "elements": elements,
        }
    return manifest, images


def write_outputs(manifest, images):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, encoded in images.items():
        target = OUTPUT / f"{name}.png"
        with tempfile.NamedTemporaryFile(dir=OUTPUT, prefix=f".{name}.", delete=False) as stream:
            stream.write(encoded)
            temporary = pathlib.Path(stream.name)
        temporary.replace(target)
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_outputs(manifest, images):
    stored = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))
    if stored != manifest:
        raise SystemExit("OFFDEVICE_UI_MANIFEST_MISMATCH")
    for name, encoded in images.items():
        if (OUTPUT / f"{name}.png").read_bytes() != encoded:
            raise SystemExit(f"OFFDEVICE_UI_GOLDEN_MISMATCH state={name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest, images = build_manifest()
    if args.check:
        check_outputs(manifest, images)
        print("OFFDEVICE_UI_GOLDENS_OK states=4 canvas=945x2048 device_interaction=false")
    else:
        write_outputs(manifest, images)
        print("OFFDEVICE_UI_GOLDENS_WRITTEN states=4 canvas=945x2048 device_interaction=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
