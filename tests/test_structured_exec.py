import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXEC = ROOT / "bin/codex-exec"


class StructuredExecTests(unittest.TestCase):
    def run_exec(self, *arguments):
        return subprocess.run(
            [str(EXEC), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_direct_argv_does_not_invoke_a_shell(self):
        result = self.run_exec("--", "/data/data/com.termux/files/usr/bin/printf", "%s", "a;$(false)")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["stdout"], "a;$(false)")
        self.assertTrue(receipt["processCompleted"])
        self.assertFalse(receipt["taskVerified"])
        self.assertNotIn("arguments", receipt)

    def test_invalid_request_is_blocked_before_execution(self):
        result = self.run_exec("--request", "missing-request.json")
        self.assertEqual(result.returncode, 64)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["status"], "blocked")
        self.assertFalse(receipt["processCompleted"])

    def test_script_is_syntax_checked_before_execution(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as temporary:
            script = pathlib.Path(temporary) / "malformed.sh"
            marker = pathlib.Path(temporary) / "must-not-exist"
            script.write_text("printf touched > " + str(marker) + "\necho '\n", encoding="utf-8")
            script.chmod(0o700)
            result = self.run_exec("--script", str(script))
            self.assertEqual(result.returncode, 2)
            receipt = json.loads(result.stdout)
            self.assertFalse(receipt["ok"])
            self.assertFalse(receipt["taskVerified"])
            self.assertFalse(marker.exists())
            self.assertIn("unexpected EOF", receipt["stderr"])

    def test_json_stdout_postcondition_is_independently_verified(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as temporary:
            request = pathlib.Path(temporary) / "request.json"
            request.write_text(json.dumps({
                "schemaVersion": 1,
                "purpose": "Verify a structured test receipt",
                "program": "/data/data/com.termux/files/usr/bin/printf",
                "args": ["%s", '{"ok":true,"verified":true}'],
                "timeoutSeconds": 5,
                "verify": {
                    "type": "json-stdout",
                    "required": {"ok": True, "verified": True},
                },
            }), encoding="utf-8")
            result = self.run_exec("--request", str(request))
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt["ok"])
            self.assertTrue(receipt["taskVerified"])
            self.assertIn("matched", receipt["verification"])

    def test_retries_require_an_explicit_retry_safe_declaration(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as temporary:
            request = pathlib.Path(temporary) / "request.json"
            request.write_text(json.dumps({
                "schemaVersion": 1,
                "purpose": "Reject unsafe retries",
                "program": "/data/data/com.termux/files/usr/bin/true",
                "args": [],
                "retries": 1,
            }), encoding="utf-8")
            result = self.run_exec("--request", str(request))
            self.assertEqual(result.returncode, 64)
            self.assertEqual(json.loads(result.stdout)["error"], "retry_safety")

    def test_wake_lock_is_released_after_success(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as temporary:
            directory = pathlib.Path(temporary)
            marker = directory / "events"
            acquire = directory / "acquire"
            release = directory / "release"
            acquire.write_text(f"#!/bin/sh\nprintf 'acquire\\n' >> '{marker}'\n", encoding="utf-8")
            release.write_text(f"#!/bin/sh\nprintf 'release\\n' >> '{marker}'\n", encoding="utf-8")
            acquire.chmod(0o700)
            release.chmod(0o700)
            request = directory / "request.json"
            request.write_text(json.dumps({
                "schemaVersion": 1,
                "purpose": "Exercise guaranteed wake lock cleanup",
                "program": "/data/data/com.termux/files/usr/bin/true",
                "args": [],
                "wakeLock": True,
            }), encoding="utf-8")
            result = subprocess.run(
                [str(EXEC), "--request", str(request)],
                cwd=ROOT,
                env={
                    **os.environ,
                    "NEMOTRON_WAKE_LOCK_COMMAND": str(acquire),
                    "NEMOTRON_WAKE_UNLOCK_COMMAND": str(release),
                },
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "acquire\nrelease\n")
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt["wakeLockRequested"])
            self.assertTrue(receipt["wakeLockReleased"])


if __name__ == "__main__":
    unittest.main()
