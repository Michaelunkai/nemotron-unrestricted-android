import contextlib
import io
import json
import pathlib
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
from nemotron_automation import AutomationState


def status_payload():
    return {
        "ok": True, "verified": False, "exitCode": 0,
        "companion": "CODEX_PC_BRIDGE_READY",
        "gateway": "CODEX_WINDOWS_AUTONOMY_GATEWAY_READY",
        "computer": "WORKSTATION", "user": "operator", "elevated": True,
        "port": 18767, "tailnetAddress": "100.64.0.2",
        "time": "2026-07-23T00:00:00Z",
        "policy": {
            "interactiveApprovalRequired": False,
            "readOnlyActions": ["status"],
            "stateChangingActions": ["powershell"],
        },
    }


class WindowsReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        self.state_root = pathlib.Path(self.temporary.name)
        self.broker = runpy.run_path(str(ROOT / "bin/codex-win"), run_name="codex_win_reliability_test")
        self.broker["main"].__globals__["AUTOMATION_ROOT"] = self.state_root

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *tail):
        output = io.StringIO()
        errors = io.StringIO()
        with mock.patch.object(sys, "argv", [str(ROOT / "bin/codex-win"), json.dumps({"action": "status"}), *tail]):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                code = self.broker["main"]()
        return code, output.getvalue(), errors.getvalue()

    def test_verified_status_is_cached_for_thirty_seconds(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps(status_payload()), "")
        with mock.patch.object(self.broker["subprocess"], "run", return_value=completed) as gateway:
            code, output, _ = self.invoke("--fresh")
        self.assertEqual(code, 0)
        self.assertEqual(gateway.call_count, 1)
        self.assertEqual(json.loads(output)["cacheStatus"], "live")

        with mock.patch.object(self.broker["subprocess"], "run", side_effect=AssertionError("gateway must not run")):
            code, output, _ = self.invoke()
        self.assertEqual(code, 0)
        cached = json.loads(output)
        self.assertEqual(cached["cacheStatus"], "verified-cache")
        self.assertLessEqual(cached["cacheAgeSeconds"], 30)

    def test_unverified_live_probe_invalidates_status_and_diagnostics(self):
        state = AutomationState(self.state_root)
        state.cache_set("pc_gateway", "status", status_payload(), 30)
        state.cache_set("pc_gateway", "diagnostics", {"ok": True}, 30)
        unverified = subprocess.CompletedProcess(
            [], 0, json.dumps({"ok": True, "verified": False, "exitCode": 0}), ""
        )
        with mock.patch.object(self.broker["subprocess"], "run", return_value=unverified):
            code, _, errors = self.invoke("--fresh")
        self.assertEqual(code, 5)
        self.assertIn("windows_gateway_unverified", errors)
        state = AutomationState(self.state_root)
        self.assertIsNone(state.cache_get("pc_gateway", "status"))
        self.assertIsNone(state.cache_get("pc_gateway", "diagnostics"))
        self.assertEqual(state.circuit_status("pc_gateway")["failures"], 1)

    def test_github_command_accepts_exact_execution_receipt_but_requires_readback(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps({
            "action": "shell",
            "ok": True,
            "verified": False,
            "status": "completed_unverified",
            "exitCode": 0,
            "timedOut": False,
            "elevated": True,
            "stdout": "published\n",
            "stderr": "",
            "startedAt": "2026-07-23T00:00:00Z",
            "finishedAt": "2026-07-23T00:00:01Z",
        }), "")
        payload = json.dumps({"action": "powershell_github", "command": "gh repo view owner/repo"})
        output = io.StringIO()
        errors = io.StringIO()
        with mock.patch.object(sys, "argv", [str(ROOT / "bin/codex-win"), payload]):
            with mock.patch.object(self.broker["subprocess"], "run", return_value=completed):
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = self.broker["main"]()
        self.assertEqual(code, 0, errors.getvalue())
        receipt = json.loads(output.getvalue())
        self.assertTrue(receipt["executionVerified"])
        self.assertFalse(receipt["verified"])
        self.assertEqual(receipt["status"], "completed_pending_postcondition")
        self.assertIn("separate readback", receipt["message"])

    def test_cleanup_accepts_only_complete_per_target_absence_receipt(self):
        inner = {
            "ok": True,
            "phases": ["inventory", "classify", "exclude", "manifest", "execute", "verify"],
            "requestedCount": 1,
            "manifest": [{"LiteralPath": r"C:\Temp\proof", "Classification": "temp"}],
            "receipts": [{"LiteralPath": r"C:\Temp\proof", "Removed": True}],
            "verification": [{"LiteralPath": r"C:\Temp\proof", "Removed": True}],
        }
        completed = subprocess.CompletedProcess([], 0, json.dumps({
            "action": "shell",
            "ok": True,
            "verified": False,
            "status": "completed_unverified",
            "exitCode": 0,
            "timedOut": False,
            "elevated": True,
            "stdout": json.dumps(inner),
            "stderr": "",
            "startedAt": "2026-07-23T00:00:00Z",
            "finishedAt": "2026-07-23T00:00:01Z",
        }), "")
        payload = json.dumps({
            "action": "powershell_cleanup",
            "targets": [{
                "path": r"C:\Users\Alice\AppData\Local\Temp\codex-disposable-proof",
                "classification": "temp",
            }],
        })
        output = io.StringIO()
        errors = io.StringIO()
        with mock.patch.object(sys, "argv", [str(ROOT / "bin/codex-win"), payload]):
            with mock.patch.object(self.broker["subprocess"], "run", return_value=completed):
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = self.broker["main"]()
        self.assertEqual(code, 0, errors.getvalue())
        receipt = json.loads(output.getvalue())
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["cleanupReceipt"], inner)
        self.assertIn("absence verification", receipt["message"])


if __name__ == "__main__":
    unittest.main()
