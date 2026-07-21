import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_HOME = pathlib.Path(tempfile.mkdtemp(prefix="nemotron-supervisor-test-"))
os.environ["CODEX_HOME"] = str(TEST_HOME)
SPEC = importlib.util.spec_from_file_location("nemotron_session_supervisor_test", ROOT / "nemotron_session_supervisor.py")
SUPERVISOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPERVISOR)


class SessionSupervisorTests(unittest.TestCase):
    def setUp(self):
        SUPERVISOR.EVENTS_PATH = TEST_HOME / self.id().replace(".", "_") / "completion-events.jsonl"
        SUPERVISOR.LESSONS_PATH = SUPERVISOR.EVENTS_PATH.with_name("lessons.jsonl")
        SUPERVISOR.ACTIVE_TURNS_PATH = SUPERVISOR.EVENTS_PATH.with_name("active-turns.json")
        SUPERVISOR.ACKS_PATH = SUPERVISOR.EVENTS_PATH.with_name("completion-notification-acks.jsonl")
        SUPERVISOR.SEQUENCE = 0
        SUPERVISOR.SEEN_COMPLETIONS.clear()
        SUPERVISOR.ACTIVE_TURNS.clear()
        SUPERVISOR.NOTIFICATION_ACKS.clear()

    def event(self, **changes):
        value = {
            "turnId": "turn-1",
            "threadId": "thread-1",
            "outcome": "completed",
            "durationMs": 1234,
            "effort": "high",
            "actionCount": 3,
            "completedActions": 3,
            "failureCount": 0,
            "plannedSteps": 4,
            "prompt": "must not be persisted",
            "rawOutput": "must not be persisted",
        }
        value.update(changes)
        return value

    def test_record_is_metadata_only_durable_and_deduplicated(self):
        first = SUPERVISOR.record_event(self.event())
        second = SUPERVISOR.record_event(self.event())
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        records = [json.loads(line) for line in SUPERVISOR.EVENTS_PATH.read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["app"], SUPERVISOR.APP_ID)
        self.assertNotIn("prompt", records[0])
        self.assertNotIn("rawOutput", records[0])
        self.assertTrue(SUPERVISOR.LESSONS_PATH.exists())

    def test_sequence_and_dedupe_state_resume_from_existing_ledger(self):
        SUPERVISOR.record_event(self.event())
        SUPERVISOR.SEQUENCE = 0
        SUPERVISOR.SEEN_COMPLETIONS.clear()
        SUPERVISOR.load_ledger_state()
        result = SUPERVISOR.record_event(self.event())
        self.assertTrue(result["duplicate"])
        next_result = SUPERVISOR.record_event(self.event(turnId="turn-2"))
        self.assertEqual(next_result["sequence"], 2)

    def test_invalid_or_unbounded_values_are_rejected_or_bounded(self):
        with self.assertRaises(ValueError):
            SUPERVISOR.sanitize_event({"turnId": "x", "outcome": "unknown"})
        sanitized = SUPERVISOR.sanitize_event(self.event(durationMs=-1, actionCount=10**20))
        self.assertEqual(sanitized["durationMs"], 0)
        self.assertEqual(sanitized["actionCount"], 1_000_000)
        self.assertLessEqual(len(SUPERVISOR.SOURCE_SHA256), 64)

    def test_active_turn_is_durable_and_only_substantive_completion_is_recorded(self):
        SUPERVISOR.register_active_turn({
            "turnId": "turn-bg",
            "threadId": "thread-bg",
            "effort": "xhigh",
            "startedAt": 123,
        })
        self.assertIn("turn-bg", SUPERVISOR.ACTIVE_TURNS)
        self.assertTrue(SUPERVISOR.ACTIVE_TURNS_PATH.is_file())
        empty = {"thread": {"turns": [{"id": "turn-bg", "status": "completed", "items": []}]}}
        with mock.patch.object(SUPERVISOR, "rpc", return_value=empty):
            self.assertEqual(SUPERVISOR.monitor_active_turns_once(), 0)
        self.assertIn("turn-bg", SUPERVISOR.ACTIVE_TURNS)
        complete = {"thread": {"turns": [{
            "id": "turn-bg",
            "status": "completed",
            "items": [{"type": "agentMessage", "text": "Verified background answer"}],
        }]}}
        with mock.patch.object(SUPERVISOR, "rpc", return_value=complete):
            self.assertEqual(SUPERVISOR.monitor_active_turns_once(), 1)
        self.assertNotIn("turn-bg", SUPERVISOR.ACTIVE_TURNS)
        records = [json.loads(line) for line in SUPERVISOR.EVENTS_PATH.read_text().splitlines()]
        self.assertEqual(records[-1]["outcome"], "completed")

    def test_substantive_message_parser_handles_nested_output_text(self):
        self.assertTrue(SUPERVISOR.substantive_agent_message({
            "items": [{"type": "agentMessage", "content": [{"output_text": "done"}]}],
        }))
        self.assertFalse(SUPERVISOR.substantive_agent_message({"items": [{"type": "agentMessage", "text": ""}]}))

    def test_completion_tone_ack_is_bounded_durable_and_deduplicated(self):
        event = SUPERVISOR.record_event(self.event())
        first = SUPERVISOR.record_notification_ack({"sequence": event["sequence"], "ignored": "raw data"})
        second = SUPERVISOR.record_notification_ack({"sequence": event["sequence"]})
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        rows = [json.loads(line) for line in SUPERVISOR.ACKS_PATH.read_text().splitlines()]
        self.assertEqual(rows, [{
            "app": SUPERVISOR.APP_ID,
            "durationMs": 3000,
            "notification": "completion-tone",
            "receivedAt": rows[0]["receivedAt"],
            "relativeVolume": 50,
            "sequence": event["sequence"],
        }])
        with self.assertRaises(ValueError):
            SUPERVISOR.record_notification_ack({"sequence": event["sequence"] + 1})


if __name__ == "__main__":
    unittest.main()
