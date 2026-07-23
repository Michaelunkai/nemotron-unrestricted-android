import json
import os
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "bin" / "codex-doctor"


class DoctorTests(unittest.TestCase):
    def run_doctor(self, *arguments):
        return subprocess.run(
            [str(DOCTOR), *arguments, "--json"],
            cwd=ROOT,
            env={**os.environ, "HOME": str(ROOT / "runtime" / "home"), "CODEX_HOME": str(ROOT / "runtime" / ".codex")},
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_environment_is_read_only_and_structured(self):
        result = self.run_doctor("environment")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["processCompleted"])
        self.assertTrue(receipt["taskVerified"])
        self.assertEqual(receipt["scope"], "environment")
        self.assertIn("environment", receipt)
        self.assertNotIn("toolchain", receipt)
        labels = {row["label"] for row in receipt["environment"]["paths"]}
        self.assertIn("runtimeHome", labels)
        self.assertIn("codexHome", labels)

    def test_toolchain_reports_installed_and_missing_without_installing(self):
        result = self.run_doctor("toolchain")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        groups = receipt["toolchain"]["groups"]
        python = next(row for row in groups["languages"] if row["command"] == "python")
        self.assertTrue(python["installed"])
        self.assertTrue(python["path"])
        self.assertIn("not installed or advertised automatically", receipt["toolchain"]["note"])

    def test_performance_uses_read_only_kernel_and_filesystem_data(self):
        result = self.run_doctor("performance")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        report = receipt["performance"]
        self.assertGreater(report["cpuCount"], 0)
        self.assertGreater(report["projectFilesystem"]["totalBytes"], 0)
        self.assertIn("No memory", report["recommendation"])

    def test_freshness_uses_current_index_and_hashes_project_tools(self):
        result = self.run_doctor("freshness")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        report = receipt["freshness"]
        self.assertFalse(report["packageIndexRefreshed"])
        self.assertIn("does not refresh", report["rule"])
        doctor = next(row for row in report["projectTools"] if row["command"] == "codex-doctor")
        self.assertRegex(doctor["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(any(row["command"] == "python" and row["installed"] for row in report["runtimeVersions"]))

    def test_help_describes_read_only_behavior(self):
        result = subprocess.run(
            [str(DOCTOR), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Read-only", result.stdout)


if __name__ == "__main__":
    unittest.main()
