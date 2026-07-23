import hashlib
import pathlib
import subprocess
import unittest
import xml.etree.ElementTree as ET

from PIL import Image


ROOT = pathlib.Path(__file__).resolve().parents[1]
ICONS = ROOT / "vendor/codexapp-native-npm/node_modules/codexapp/dist/icons"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class IconAssetTests(unittest.TestCase):
    def test_android_adaptive_icons_have_background_foreground_and_monochrome(self):
        for version in ("mipmap-anydpi-v26", "mipmap-anydpi-v33"):
            for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
                root = ET.parse(ROOT / "res" / version / name).getroot()
                self.assertEqual(root.tag, "adaptive-icon")
                tags = [child.tag for child in root]
                self.assertIn("background", tags)
                self.assertIn("foreground", tags)
                if version.endswith("v33"):
                    self.assertIn("monochrome", tags)

    def test_vector_foreground_and_monochrome_are_valid_and_distinct(self):
        foreground = ET.parse(ROOT / "res/drawable/ic_nemotron_unrestricted_foreground.xml").getroot()
        monochrome = ET.parse(ROOT / "res/drawable/ic_nemotron_unrestricted_monochrome.xml").getroot()
        self.assertEqual(foreground.tag, "vector")
        self.assertEqual(monochrome.tag, "vector")
        self.assertGreaterEqual(len(foreground.findall("path")), 6)
        self.assertGreaterEqual(len(monochrome.findall("path")), 3)
        self.assertNotEqual(
            hashlib.sha256(ET.tostring(foreground)).digest(),
            hashlib.sha256(ET.tostring(monochrome)).digest(),
        )

    def test_pwa_icons_match_the_maintained_vector_and_expected_sizes(self):
        svg = (ROOT / "artwork/icon.svg").read_bytes()
        for name in ("codexui-icon.svg", "pwa-icon.svg", "pwa-maskable.svg"):
            self.assertEqual((ICONS / name).read_bytes(), svg)
        for name, size in (
            ("apple-touch-icon.png", 180),
            ("pwa-192x192.png", 192),
            ("pwa-512x512.png", 512),
            ("maskable-512x512.png", 512),
        ):
            with Image.open(ICONS / name) as image:
                self.assertEqual(image.size, (size, size))
                self.assertEqual(image.mode, "RGB")

    def test_icon_renderer_is_deterministic(self):
        before = hashlib.sha256((ICONS / "pwa-512x512.png").read_bytes()).hexdigest()
        completed = subprocess.run(
            ["python", "tools/render-icon.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        after = hashlib.sha256((ICONS / "pwa-512x512.png").read_bytes()).hexdigest()
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
