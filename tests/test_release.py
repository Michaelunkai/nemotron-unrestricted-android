import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "codex-release"


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / "AndroidManifest.xml").write_text(
            '<manifest android:versionCode="2" android:versionName="1.1.0"></manifest>\n', encoding="utf-8"
        )
        (self.root / "build-nemotron-unrestricted.sh").write_text(
            'VERSION_CODE="2"\nVERSION_NAME="1.1.0"\n', encoding="utf-8"
        )
        (self.root / "release-nemotron-gate.sh").write_text(
            'APK="$APP_HOME/dist/Nemotron-Unrestricted-1.1.0.apk"\n'
            "aapt dump badging \"$APK\" | grep \"versionCode='2' versionName='1.1.0'\"\n",
            encoding="utf-8",
        )
        os.chmod(self.root / "build-nemotron-unrestricted.sh", 0o755)
        os.chmod(self.root / "release-nemotron-gate.sh", 0o755)
        self.env = dict(os.environ, NEMOTRON_RELEASE_ROOT=str(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        result = subprocess.run([str(COMMAND), *args], cwd=ROOT, env=self.env, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def test_plan_prepare_readback_and_exact_rollback(self):
        common = ("--version", "1.2.0", "--version-code", "3", "--change", "Added verified automation")
        result, plan = self.invoke("plan", *common)
        self.assertEqual(result.returncode, 0, result.stderr)
        result, prepared = self.invoke("prepare", *common, "--plan-sha256", plan["planSha256"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('versionName="1.2.0"', (self.root / "AndroidManifest.xml").read_text())
        self.assertFalse((self.root / "CHANGELOG.md").read_text().endswith("\n\n"))
        self.assertTrue((self.root / "release-notes/1.2.0.md").is_file())
        self.assertEqual((self.root / "build-nemotron-unrestricted.sh").stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.root / "release-nemotron-gate.sh").stat().st_mode & 0o777, 0o755)
        result, _ = self.invoke("rollback", prepared["receipt"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('versionName="1.1.0"', (self.root / "AndroidManifest.xml").read_text())
        self.assertFalse((self.root / "release-notes/1.2.0.md").exists())
        self.assertEqual((self.root / "build-nemotron-unrestricted.sh").stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.root / "release-nemotron-gate.sh").stat().st_mode & 0o777, 0o755)

    def test_non_increasing_hash_mismatch_and_changed_release_fail_closed(self):
        result, receipt = self.invoke("plan", "--version", "1.0.0", "--version-code", "3", "--change", "x")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "version_not_increasing")
        common = ("--version", "1.2.0", "--version-code", "3", "--change", "x")
        self.assertEqual(self.invoke("prepare", *common, "--plan-sha256", "bad")[0].returncode, 2)
        _, plan = self.invoke("plan", *common)
        _, prepared = self.invoke("prepare", *common, "--plan-sha256", plan["planSha256"])
        (self.root / "CHANGELOG.md").write_text("user change", encoding="utf-8")
        result, receipt = self.invoke("rollback", prepared["receipt"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "release_files_changed")


if __name__ == "__main__":
    unittest.main()
