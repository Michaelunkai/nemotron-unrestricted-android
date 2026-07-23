import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "codex-secrets"


class SecretTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.temp.name) / "state"
        self.env = dict(
            os.environ, NEMOTRON_SECRET_STATE=str(self.state),
            CODEX_RUNTIME_TEST_MODE="1", NEMOTRON_SECRET_TEST_KEY="test-only-key-material-that-is-long",
        )

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args, stdin=""):
        result = subprocess.run(
            [str(COMMAND), *args], cwd=ROOT, env=self.env, input=stdin,
            capture_output=True, text=True, check=False,
        )
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def test_set_status_run_redaction_rotate_delete_restore(self):
        secret = "super-private-value"
        result, receipt = self.invoke(
            "set", "api.token", "--scope", "web", "--allow-executable", "env", stdin=secret,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record_text = (self.state / "active/api.token.json").read_text()
        self.assertNotIn(secret, record_text)
        self.assertEqual((self.state / "active/api.token.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.invoke("status", "api.token")[0].returncode, 0)
        result, run = self.invoke("run", "api.token", "--scope", "web", "--env", "TOKEN", "env")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(secret, json.dumps(run))
        self.assertIn("TOKEN=[REDACTED]", run["stdout"])
        result, rotated = self.invoke("rotate", "api.token", stdin="new-private-value")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rotated["secret"]["version"], 2)
        self.assertTrue((self.state / "archive/api.token/v1.json").is_file())
        self.assertEqual(self.invoke("delete", "api.token", "--yes")[0].returncode, 0)
        self.assertEqual(self.invoke("restore", "api.token")[0].returncode, 0)

    def test_scope_executable_authentication_and_confirmation_fail_closed(self):
        self.assertEqual(self.invoke(
            "set", "api.token", "--scope", "web", "--allow-executable", "env", stdin="secret",
        )[0].returncode, 0)
        for args, error in (
            (("run", "api.token", "--scope", "pc", "--env", "TOKEN", "env"), "secret_scope_denied"),
            (("run", "api.token", "--scope", "web", "--env", "TOKEN", "printenv"), "secret_executable_denied"),
            (("delete", "api.token"), "secret_delete_confirmation_required"),
        ):
            result, receipt = self.invoke(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(receipt["error"], error)
        record = json.loads((self.state / "active/api.token.json").read_text())
        record["ciphertext"] = record["ciphertext"][:-2] + "AA"
        (self.state / "active/api.token.json").write_text(json.dumps(record))
        result, receipt = self.invoke("status", "api.token")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["error"], "secret_authentication_failed")


if __name__ == "__main__":
    unittest.main()
