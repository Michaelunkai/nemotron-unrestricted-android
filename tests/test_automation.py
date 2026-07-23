import json
import contextlib
import pathlib
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "bin"))
from nemotron_automation import AutomationState, redact, retry


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "build")
        self.state = AutomationState(pathlib.Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_ttl_cache_expires_and_prunes(self):
        self.state.cache_set("pc", "identity", {"verified": True}, 1)
        self.assertTrue(self.state.cache_get("pc", "identity")["value"]["verified"])
        with contextlib.closing(self.state.connect()) as connection, connection:
            connection.execute("UPDATE cache SET expires_at=?", (int(time.time()) - 1,))
        self.assertIsNone(self.state.cache_get("pc", "identity"))

    def test_circuit_opens_half_opens_and_closes(self):
        self.state.circuit_failure("pc", "offline", threshold=2, cool_down_seconds=1)
        opened = self.state.circuit_failure("pc", "offline", threshold=2, cool_down_seconds=1)
        self.assertEqual(opened["state"], "open")
        self.assertFalse(opened["allow"])
        with contextlib.closing(self.state.connect()) as connection, connection:
            connection.execute("UPDATE circuits SET opened_at=?", (int(time.time()) - 2,))
        self.assertEqual(self.state.circuit_status("pc")["state"], "half-open")
        self.state.circuit_success("pc")
        self.assertEqual(self.state.circuit_status("pc")["state"], "closed")

    def test_retry_requires_safety_and_uses_jittered_backoff(self):
        with self.assertRaisesRegex(ValueError, "retry_safety_required"):
            retry(lambda: None, attempts=2, retry_safe=False, retryable=lambda _error: True)
        calls = []
        sleeps = []
        def operation():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("temporary")
            return "done"
        result = retry(
            operation, attempts=3, retry_safe=True,
            retryable=lambda error: str(error) == "temporary",
            sleeper=sleeps.append, random_source=lambda: 0.5,
        )
        self.assertEqual(result, "done")
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_logs_redact_and_metrics_exclude_sensitive_fields(self):
        self.state.log("info", "pc", "Authorization: Bearer abc", token="secret", latencyMs=12)
        payload = self.state.log_path.read_text(encoding="utf-8")
        self.assertNotIn("abc", payload)
        self.assertNotIn("secret", payload)
        self.state.increment("pc_success_total")
        metrics = self.state.metrics_path.read_text(encoding="utf-8")
        self.assertIn("pc_success_total", metrics)
        self.assertNotIn("Authorization", metrics)

    def test_recursive_redaction(self):
        value = redact({"nested": [{"apiKey": "abc"}, "password=xyz"]})
        self.assertEqual(value["nested"][0]["apiKey"], "<redacted>")
        self.assertNotIn("xyz", value["nested"][1])

    def test_operation_correlation_and_latency_gauge(self):
        with self.state.operation("scheduler", "dispatch") as correlation:
            self.assertRegex(correlation, r"^[0-9a-f]{32}$")
        log = self.state.log_path.read_text(encoding="utf-8")
        self.assertIn(correlation, log)
        self.assertIn("Operation completed.", log)
        metrics = self.state.metrics_path.read_text(encoding="utf-8")
        self.assertIn('name="scheduler_success"', metrics)
        self.assertIn('name="scheduler_latency_ms"', metrics)


if __name__ == "__main__":
    unittest.main()
