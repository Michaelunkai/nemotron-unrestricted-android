import json
import pathlib
import runpy
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


class BootTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        self.root = pathlib.Path(self.temporary.name)
        self.module = runpy.run_path(str(ROOT / "bin/codex-boot"), run_name="codex_boot_test")
        globals_ = self.module["main"].__globals__
        globals_["STATE"] = self.root / "state"
        globals_["GENERATED"] = self.root / "state" / "nemotron-runtime.sh"
        globals_["MANIFEST"] = self.root / "state" / "manifest.json"
        globals_["ACTIVE"] = self.root / "active" / "nemotron-runtime.sh"

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *args):
        with mock.patch.object(sys, "argv", ["codex-boot", *args]):
            with mock.patch("builtins.print") as output:
                code = self.module["main"]()
        return code, json.loads(output.call_args.args[0])

    def test_generation_is_inert_and_hash_bound(self):
        code, receipt = self.invoke("generate", "--profile", "ssh-agent", "--profile", "pc-monitor")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "active" / "nemotron-runtime.sh").exists())
        generated = self.root / "state" / "nemotron-runtime.sh"
        self.assertEqual(len(receipt["sha256"]), 64)
        text = generated.read_text(encoding="utf-8")
        self.assertIn("managed-by: nemotron-unrestricted", text)
        self.assertNotIn("termux-wake-lock", text)

    def test_enable_and_disable_touch_only_exact_owned_script(self):
        _, generated = self.invoke("generate", "--profile", "ssh-agent")
        code, enabled = self.invoke("enable", "--confirm-sha256", generated["sha256"])
        self.assertEqual(code, 0)
        self.assertTrue(enabled["activeMatchesGenerated"])
        code, disabled = self.invoke("disable", "--confirm-sha256", generated["sha256"])
        self.assertEqual(code, 0)
        self.assertFalse(disabled["active"])

    def test_unrelated_active_script_is_never_overwritten(self):
        _, generated = self.invoke("generate", "--profile", "ssh-agent")
        active = self.root / "active" / "nemotron-runtime.sh"
        active.parent.mkdir()
        active.write_text("#!/bin/sh\nimportant-user-work\n", encoding="utf-8")
        code, error = self.invoke("enable", "--confirm-sha256", generated["sha256"])
        self.assertEqual(code, 2)
        self.assertEqual(error["error"], "unrelated_boot_script_exists")
        self.assertIn("important-user-work", active.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
