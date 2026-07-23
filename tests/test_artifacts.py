import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "codex-artifacts"


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.env = dict(os.environ, NEMOTRON_ARTIFACT_STATE=str(self.root / "state"))

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        result = subprocess.run([str(COMMAND), *args], cwd=ROOT, env=self.env, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def add(self, value=b"new"):
        source = self.root / "artifact.bin"
        source.write_bytes(value)
        result, receipt = self.invoke("add", str(source), "--source-url", "https://example.com/artifact.bin")
        self.assertEqual(result.returncode, 0, result.stderr)
        return source, receipt["artifact"]["id"], receipt

    def test_add_deduplicate_inspect_quarantine_restore(self):
        source, artifact_id, receipt = self.add()
        self.assertFalse(receipt["deduplicated"])
        result, inspected = self.invoke("inspect", artifact_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(inspected["taskVerified"])
        result, receipt = self.invoke("add", str(source))
        self.assertTrue(receipt["deduplicated"])
        self.assertTrue(source.exists())
        self.assertEqual(self.invoke("quarantine", artifact_id)[0].returncode, 0)
        self.assertTrue(source.exists())
        self.assertEqual(self.invoke("restore", artifact_id)[0].returncode, 0)

    def test_promote_and_rollback_existing_and_new_targets(self):
        _, artifact_id, _ = self.add(b"replacement")
        existing = self.root / "existing.bin"
        existing.write_bytes(b"original")
        result, receipt = self.invoke("promote", artifact_id, "--target", str(existing))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(existing.read_bytes(), b"replacement")
        result, receipt = self.invoke("rollback", artifact_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(existing.read_bytes(), b"original")
        created = self.root / "new.bin"
        self.assertEqual(self.invoke("promote", artifact_id, "--target", str(created))[0].returncode, 0)
        self.assertTrue(created.exists())
        self.assertEqual(self.invoke("rollback", artifact_id)[0].returncode, 0)
        self.assertFalse(created.exists())

    def test_changed_target_and_retention_apply_fail_closed(self):
        _, artifact_id, _ = self.add()
        target = self.root / "target"
        self.assertEqual(self.invoke("promote", artifact_id, "--target", str(target))[0].returncode, 0)
        target.write_bytes(b"user-change")
        result, receipt = self.invoke("rollback", artifact_id)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "rollback_target_changed")
        result, receipt = self.invoke("prune", "--days", "30", "--apply", "bad")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "retention_plan_hash_mismatch")

    def test_source_url_credentials_and_checksum_rejected(self):
        source = self.root / "bad"
        source.write_bytes(b"x")
        result, receipt = self.invoke("add", str(source), "--source-url", "https://u:p@example.com/x")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "source_url_credentials_forbidden")
        result, receipt = self.invoke("add", str(source), "--expected-sha256", "0" * 64)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "checksum_mismatch")


if __name__ == "__main__":
    unittest.main()
