import contextlib
import importlib.machinery
import importlib.util
import io
import json
import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("codex_runtime_status", str(ROOT / "bin/codex-runtime-status"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
STATUS = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(STATUS)


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.body


class RuntimeStatusTests(unittest.TestCase):
    def run_status(self, payload):
        output = io.StringIO()
        with mock.patch.object(STATUS.urllib.request, "urlopen", return_value=FakeResponse(payload)), \
             mock.patch.object(sys, "argv", [str(ROOT / "bin/codex-runtime-status")]), \
             contextlib.redirect_stdout(output):
            code = STATUS.main()
        return code, json.loads(output.getvalue())

    def test_pending_max_is_not_reported_as_effective(self):
        code, value = self.run_status({
            "status": "ok", "app": "nemotron-unrestricted",
            "verificationStatus": "dispatched",
            "requestedProvider": "OpenRouter",
            "requestedModel": "nvidia/nemotron-3-ultra-550b-a55b",
            "requestedEffort": "max", "requestedReasoningBudget": 128000,
            "effectiveGateway": "OpenRouter", "effectiveProvider": "Together",
            "effectiveModel": "nvidia/nemotron-3-ultra-550b-a55b",
            "effectiveEffort": "low", "effectiveReasoningTokens": 12,
            "identityVerified": False, "effortVerified": False, "verified": False,
            "modelSubstitution": False, "activeTurnCount": 1,
        })
        self.assertEqual(code, 0)
        self.assertTrue(value["ok"])
        self.assertEqual(value["verificationStatus"], "dispatched")
        self.assertEqual(value["requestedEffort"], "max")
        self.assertEqual(value["requestedReasoningBudget"], 128000)
        self.assertFalse(value["identityVerified"])
        self.assertFalse(value["effortVerified"])
        self.assertFalse(value["verified"])

    def test_confirmed_identity_can_truthfully_leave_effort_unknown(self):
        code, value = self.run_status({
            "status": "ok", "app": "nemotron-unrestricted",
            "verificationStatus": "confirmed",
            "requestedProvider": "OpenRouter", "requestedModel": "nvidia/nemotron-3-ultra-550b-a55b",
            "requestedEffort": "max", "requestedReasoningBudget": 128000,
            "effectiveGateway": "OpenRouter", "effectiveProvider": "Together",
            "effectiveModel": "nvidia/nemotron-3-ultra-550b-a55b", "effectiveEffort": None,
            "effectiveReasoningTokens": 16, "identityVerified": True,
            "effortVerified": False, "verified": False, "modelSubstitution": False,
            "requestId": "request-1", "responseId": "response-1",
        })
        self.assertEqual(code, 0)
        self.assertTrue(value["identityVerified"])
        self.assertIsNone(value["effectiveEffort"])
        self.assertEqual(value["effectiveProvider"], "Together")
        self.assertFalse(value["verified"])

    def test_unavailable_endpoint_fails_without_fabricated_identity(self):
        output = io.StringIO()
        with mock.patch.object(STATUS.urllib.request, "urlopen", side_effect=OSError("offline")), \
             mock.patch.object(sys, "argv", [str(ROOT / "bin/codex-runtime-status")]), \
             contextlib.redirect_stdout(output):
            code = STATUS.main()
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(output.getvalue()), {
            "ok": False, "error": "runtime_identity_unavailable", "verified": False,
        })


if __name__ == "__main__":
    unittest.main()
