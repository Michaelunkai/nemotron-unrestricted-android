import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "codex-scaffold"


class ScaffoldTests(unittest.TestCase):
    def invoke(self, *args):
        result = subprocess.run([str(COMMAND), *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def test_list_and_dry_run(self):
        result, receipt = self.invoke("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("python-app", receipt["templates"])
        result, receipt = self.invoke("create", "python-app", "dry-proof", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(receipt["dryRun"])
        self.assertFalse(pathlib.Path(receipt["target"]).exists())

    def test_create_verify_and_exact_rollback(self):
        name = "scaffold-proof-" + os.urandom(3).hex()
        result, receipt = self.invoke("create", "python-app", name)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = pathlib.Path(receipt["project"]["target"])
        receipt_path = receipt["receipt"]
        try:
            self.assertTrue((target / ".git").is_dir())
            self.assertEqual(self.invoke("verify", receipt_path)[0].returncode, 0)
            self.assertEqual(self.invoke("rollback", receipt_path)[0].returncode, 0)
            self.assertFalse(target.exists())
        finally:
            if target.exists():
                subprocess.run(["find", str(target), "-depth", "-delete"], check=False)

    def test_changed_project_and_outside_target_fail_closed(self):
        name = "scaffold-changed-" + os.urandom(3).hex()
        result, receipt = self.invoke("create", "shell-tool", name)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = pathlib.Path(receipt["project"]["target"])
        try:
            (target / "user.txt").write_text("keep", encoding="utf-8")
            result, failure = self.invoke("rollback", receipt["receipt"])
            self.assertEqual(result.returncode, 2)
            self.assertEqual(failure["error"], "project_changed_since_scaffold")
            self.assertTrue((target / "user.txt").exists())
        finally:
            subprocess.run(["find", str(target), "-depth", "-delete"], check=False)
        with tempfile.TemporaryDirectory() as outside:
            result, failure = self.invoke("create", "python-app", "outside-proof", "--output", str(pathlib.Path(outside) / "x"))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(failure["error"], "target_outside_workspace")


if __name__ == "__main__":
    unittest.main()
