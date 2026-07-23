import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "codex-command"


class CommandTests(unittest.TestCase):
    def invoke(self, *args):
        result = subprocess.run([str(COMMAND), *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def task(self, path, mutation=False, rollback=True):
        step = {
            "id": "check", "purpose": "Return a verified JSON receipt",
            "program": "/data/data/com.termux/files/usr/bin/printf",
            "args": ['{\"ok\":true,\"verified\":true}\\n'],
            "verify": {"type": "json-stdout", "required": {"ok": True, "verified": True}},
            "mutation": mutation, "requiresConsent": mutation,
        }
        if mutation and rollback:
            step["rollback"] = {
                "purpose": "Verify the rollback path", "program": "/data/data/com.termux/files/usr/bin/printf",
                "args": ['{\"ok\":true,\"verified\":true}\\n'],
                "verify": {"type": "json-stdout", "required": {"ok": True, "verified": True}},
            }
        path.write_text(json.dumps({
            "schemaVersion": 1, "id": "template-task", "title": "Template task", "steps": [step],
        }), encoding="utf-8")

    def test_register_plan_run_and_idempotent_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            task = pathlib.Path(temp) / "task.json"
            self.task(task)
            name = "proof-" + os.urandom(3).hex()
            self.assertEqual(self.invoke("register", name, str(task), "--consent", "read")[0].returncode, 0)
            self.assertEqual(self.invoke("plan", name)[0].returncode, 0)
            result, receipt = self.invoke("run", name, "--idempotency-key", "one")
            self.assertEqual(result.returncode, 0, result.stderr)
            result, replay = self.invoke("run", name, "--idempotency-key", "one")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(replay["idempotentReplay"])

    def test_consent_and_rollback_contract_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            task = pathlib.Path(temp) / "task.json"
            self.task(task, mutation=True, rollback=False)
            result, receipt = self.invoke("register", "bad-" + os.urandom(3).hex(), str(task), "--consent", "mutation")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(receipt["error"], "mutation_rollback_required")


if __name__ == "__main__":
    unittest.main()
