import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAINTAIN = ROOT / "bin" / "codex-maintain"


class MaintainTests(unittest.TestCase):
    def test_check_is_read_only(self):
        result = subprocess.run(
            [str(MAINTAIN), "check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["taskVerified"])
        self.assertFalse(receipt["freshness"]["packageIndexRefreshed"])

    def test_plan_is_hashable_and_has_no_removal_gate(self):
        name = f"maintenance-test-{os.getpid()}.json"
        path = ROOT / "workspace" / name
        try:
            result = subprocess.run(
                [str(MAINTAIN), "plan", "--output", name],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(receipt["taskVerified"])
            self.assertTrue(payload["safety"]["refusesPackageRemoval"])
            self.assertTrue(payload["safety"]["requiresExactPlanSha256"])
            self.assertEqual(len(receipt["sha256"]), 64)
        finally:
            if path.exists():
                path.unlink()

    def test_apply_requires_explicit_yes_before_any_execution(self):
        temporary = pathlib.Path(tempfile.mkdtemp(dir=ROOT / "workspace", prefix="maintain-refusal-"))
        plan = temporary / "plan.json"
        plan.write_text("{}\n", encoding="utf-8")
        try:
            result = subprocess.run(
                [str(MAINTAIN), "apply", "--plan", str(plan), "--confirm-sha256", "0" * 64],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("explicit_yes_required", result.stderr)
        finally:
            plan.unlink()
            temporary.rmdir()


if __name__ == "__main__":
    unittest.main()
