import json
import pathlib
import subprocess
import unittest

from PIL import Image


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "offdevice-ui"
MANIFEST = OUTPUT / "manifest.json"
EXACT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
EFFORTS = ["None", "Minimal", "Low", "Medium", "High", "Extra high", "Max"]


class OffDeviceUiGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_renderer_reproduces_all_goldens_without_device_interaction(self):
        completed = subprocess.run(
            ["python", "tools/render-offdevice-ui.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("states=4", completed.stdout)
        self.assertIn("device_interaction=false", completed.stdout)
        self.assertIs(self.manifest["deviceInteraction"], False)
        self.assertEqual(self.manifest["referenceCanvas"], {"width": 945, "height": 2048})
        self.assertEqual(set(self.manifest["states"]), {
            "settings", "model-selector", "effort-menu", "command-progress",
        })

    def test_png_dimensions_hashes_and_rectangles_are_bounded(self):
        width = self.manifest["referenceCanvas"]["width"]
        height = self.manifest["referenceCanvas"]["height"]
        for name, state in self.manifest["states"].items():
            with self.subTest(state=name):
                path = OUTPUT / state["file"]
                with Image.open(path) as image:
                    self.assertEqual(image.size, (width, height))
                self.assertRegex(state["sha256"], r"^[0-9a-f]{64}$")
                for item in state["elements"]:
                    left, top, right, bottom = item["rect"]
                    self.assertGreaterEqual(left, 0)
                    self.assertGreaterEqual(top, 0)
                    self.assertLessEqual(right, width)
                    self.assertLessEqual(bottom, height)
                    self.assertGreater(right, left)
                    self.assertGreater(bottom, top)
                    if "minTouchHeight" in item:
                        self.assertGreaterEqual(bottom - top, 88)

    def test_settings_card_hierarchy_and_destructive_contract(self):
        elements = {item["id"]: item for item in self.manifest["states"]["settings"]["elements"]}
        card = elements["nemotron-session-cleanup-card"]
        button = elements["nemotron-session-cleanup-open"]
        self.assertEqual(card["role"], "region")
        self.assertEqual(button["role"], "button")
        self.assertTrue(button["destructive"])
        self.assertEqual(button["label"], "Delete all sessions and threads now")
        self.assertGreaterEqual(button["rect"][0], card["rect"][0])
        self.assertLessEqual(button["rect"][2], card["rect"][2])
        self.assertEqual(self.manifest["colors"]["danger"], "#db0038")

    def test_exact_model_is_visible_selected_and_not_clipped(self):
        items = self.manifest["states"]["model-selector"]["elements"]
        selected = [item for item in items if item.get("selected")]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["label"], EXACT_MODEL)
        self.assertEqual(self.manifest["exactModel"], EXACT_MODEL)
        self.assertLessEqual(selected[0]["rect"][2], 945 - 40)
        self.assertGreaterEqual(selected[0]["minTouchHeight"], 88)

    def test_effort_menu_order_wording_selection_and_touch_targets(self):
        items = self.manifest["states"]["effort-menu"]["elements"]
        self.assertEqual([item["label"] for item in items], EFFORTS)
        self.assertEqual(self.manifest["efforts"], EFFORTS)
        self.assertEqual([item["label"] for item in items if item.get("selected")], ["Max"])
        self.assertTrue(all(item["minTouchHeight"] >= 88 for item in items))

    def test_command_progress_is_english_first_with_collapsed_technical_details(self):
        items = {
            item["id"]: item
            for item in self.manifest["states"]["command-progress"]["elements"]
        }
        card = items["command-progress-card"]
        result = items["command-verified-result"]
        details = items["command-technical-details"]
        self.assertEqual(card["role"], "status")
        self.assertEqual(card["live"], "polite")
        self.assertIn("verifying the exact Windows result", card["label"])
        self.assertTrue(result["verified"])
        self.assertIn("available and verified", result["label"])
        self.assertFalse(details["expanded"])
        self.assertIn("Technical command", details["label"])

    def test_manifest_contract_matches_maintained_web_source(self):
        source = (ROOT / "web" / "nemotron-autonomy-progress.js").read_text(encoding="utf-8")
        self.assertIn(EXACT_MODEL, (ROOT / "nemotron_unrestricted_proxy.py").read_text(encoding="utf-8"))
        self.assertNotIn("nemotron-cleanup-confirmation", source)
        self.assertIn("One click immediately backs up, deletes, and verifies", source)
        self.assertIn("background:#db0038", source)
        for effort in EFFORTS:
            self.assertIn(effort, source if effort == "Max" else (ROOT / "tools/patch-codexapp-ui.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
