import io
import json
import pathlib
import runpy
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
MODULE = runpy.run_path(str(ROOT / "bin/codex-resilience"), run_name="resilience_test")


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "build")
        self.base = pathlib.Path(self.temp.name)
        self.source = self.base / "source"
        self.destination = self.base / "destination"
        self.state = self.base / "state"
        self.safe_file = self.state / "safe-mode.json"
        self.source.mkdir()
        self.destination.mkdir()
        (self.source / "new.txt").write_text("new", encoding="utf-8")
        (self.source / "conflict.txt").write_text("source", encoding="utf-8")
        (self.destination / "conflict.txt").write_text("destination", encoding="utf-8")
        self.globals = {
            "STATE": self.state,
            "SAFE_MODE_FILE": self.safe_file,
            "MANAGED_ROOTS": (self.base,),
        }

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, arguments):
        with (
            mock.patch("sys.argv", ["codex-resilience", *arguments]),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            mock.patch.dict(MODULE["main"].__globals__, self.globals),
        ):
            code = MODULE["main"]()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_safe_mode_requires_exact_hash_to_disable(self):
        code, stdout, _ = self.invoke(["safe-mode", "enable", "--reason", "verified offline"])
        self.assertEqual(code, 0)
        receipt = json.loads(stdout)
        code, _, stderr = self.invoke(["safe-mode", "disable", "--state-sha256", "0" * 64])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stderr)["error"], "safe_mode_state_changed")
        code, stdout, _ = self.invoke(
            ["safe-mode", "disable", "--state-sha256", receipt["stateSha256"]]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["mode"], "normal")

    def test_sync_preserves_destination_and_creates_conflict_copy(self):
        plan = self.base / "sync-plan.json"
        code, stdout, _ = self.invoke(
            ["sync-plan", str(self.source), str(self.destination), "--output", str(plan)]
        )
        self.assertEqual(code, 0)
        receipt = json.loads(stdout)
        self.assertEqual(receipt["conflictCount"], 1)
        code, stdout, _ = self.invoke(
            ["sync-apply", "--plan", str(plan), "--sha256", receipt["planSha256"]]
        )
        self.assertEqual(code, 0)
        self.assertEqual((self.destination / "conflict.txt").read_text(encoding="utf-8"), "destination")
        conflicts = list(self.destination.glob("conflict.txt.conflict-*"))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].read_text(encoding="utf-8"), "source")
        self.assertEqual((self.destination / "new.txt").read_text(encoding="utf-8"), "new")

    def test_network_heavy_wrappers_enforce_safe_mode(self):
        for relative in (
            "bin/codex-research",
            "bin/codex-browser-safe",
            "bin/codex-download",
            "bin/codex-install",
            "bin/codex-pc",
            "bin/codex-win",
        ):
            self.assertIn(
                "safe_mode_status",
                (ROOT / relative).read_text(encoding="utf-8"),
                relative,
            )


if __name__ == "__main__":
    unittest.main()
