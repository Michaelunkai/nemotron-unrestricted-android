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
        SUPERVISOR.PROGRESS_PATH = SUPERVISOR.EVENTS_PATH.with_name("progress-events.jsonl")
        SUPERVISOR.SEQUENCE = 0
        SUPERVISOR.PROGRESS_SEQUENCE = 0
        SUPERVISOR.SEEN_COMPLETIONS.clear()
        SUPERVISOR.SEEN_PROGRESS_EVENTS.clear()
        SUPERVISOR.TURN_PROGRESS_SEQUENCES.clear()
        SUPERVISOR.LAST_PROGRESS_BY_TURN.clear()
        SUPERVISOR.LAST_PROGRESS_MONOTONIC.clear()
        SUPERVISOR.HEARTBEAT_COUNTS.clear()
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

    def test_direct_terminal_event_removes_matching_active_turn(self):
        SUPERVISOR.register_active_turn({
            "turnId": "turn-direct",
            "threadId": "thread-direct",
            "effort": "max",
            "startedAt": 123,
        })
        result = SUPERVISOR.record_event(self.event(
            turnId="turn-direct",
            threadId="thread-direct",
            outcome="stopped",
        ))
        self.assertFalse(result["duplicate"])
        self.assertNotIn("turn-direct", SUPERVISOR.ACTIVE_TURNS)
        self.assertEqual(json.loads(SUPERVISOR.ACTIVE_TURNS_PATH.read_text()), {})

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
            "notification": "terminal-ringtone",
            "receivedAt": rows[0]["receivedAt"],
            "relativeVolume": 50,
            "sampleRateHz": 48000,
            "sequence": event["sequence"],
            "waveform": "nemotron-six-note-v1",
        }])
        with self.assertRaises(ValueError):
            SUPERVISOR.record_notification_ack({"sequence": event["sequence"] + 1})

    def test_progress_is_active_bound_monotonic_durable_and_metadata_only(self):
        SUPERVISOR.register_active_turn({
            "turnId": "turn-progress",
            "threadId": "thread-progress",
            "effort": "high",
            "startedAt": 123,
        })
        payload = {
            "schemaVersion": 1,
            "eventId": "progress-event-1",
            "sequence": 1,
            "turnId": "turn-progress",
            "threadId": "thread-progress",
            "actionId": "command-1",
            "state": "working",
            "message": "Checking the local runtime health",
            "verifiedResult": "",
            "nextAction": "Read the health response",
            "technicalCategory": "command",
            "prompt": "must not persist",
            "rawCommand": "curl http://127.0.0.1:18774/vault-health",
            "rawOutput": "must not persist",
        }
        first = SUPERVISOR.record_progress(payload)
        second = SUPERVISOR.record_progress(payload)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        rows = [json.loads(line) for line in SUPERVISOR.PROGRESS_PATH.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message"], "Checking the local runtime health")
        self.assertEqual(rows[0]["sourceSequence"], 1)
        self.assertNotIn("prompt", rows[0])
        self.assertNotIn("rawCommand", rows[0])
        self.assertNotIn("rawOutput", rows[0])

    def test_progress_rejects_foreign_regressing_late_and_raw_command_messages(self):
        SUPERVISOR.register_active_turn({
            "turnId": "turn-progress",
            "threadId": "thread-progress",
            "startedAt": 123,
        })
        base = {
            "schemaVersion": 1,
            "eventId": "progress-event-1",
            "sequence": 2,
            "turnId": "turn-progress",
            "threadId": "thread-progress",
            "actionId": "command-1",
            "state": "working",
            "message": "Checking the signed package",
            "verifiedResult": "",
            "nextAction": "Verify its signer",
            "technicalCategory": "verification",
        }
        SUPERVISOR.record_progress(base)
        with self.assertRaises(ValueError):
            SUPERVISOR.record_progress({**base, "eventId": "foreign", "threadId": "other"})
        with self.assertRaises(ValueError):
            SUPERVISOR.record_progress({**base, "eventId": "regressing", "sequence": 1})
        with self.assertRaises(ValueError):
            SUPERVISOR.record_progress({
                **base,
                "eventId": "raw-command",
                "sequence": 3,
                "message": "curl http://127.0.0.1:18774/vault-health",
            })
        SUPERVISOR.record_event(self.event(
            turnId="turn-progress",
            threadId="thread-progress",
        ))
        with self.assertRaises(ValueError):
            SUPERVISOR.record_progress({**base, "eventId": "late", "sequence": 3})

    def test_progress_state_reloads_for_ordered_readback(self):
        SUPERVISOR.register_active_turn({
            "turnId": "turn-progress",
            "threadId": "thread-progress",
            "startedAt": 123,
        })
        SUPERVISOR.record_progress({
            "schemaVersion": 1,
            "eventId": "progress-event-7",
            "sequence": 7,
            "turnId": "turn-progress",
            "threadId": "thread-progress",
            "actionId": "tool-7",
            "state": "completed",
            "message": "Verified the runtime health response",
            "verifiedResult": "The runtime reports healthy",
            "nextAction": "Continue with package verification",
            "technicalCategory": "verification",
        })
        SUPERVISOR.PROGRESS_SEQUENCE = 0
        SUPERVISOR.SEEN_PROGRESS_EVENTS.clear()
        SUPERVISOR.TURN_PROGRESS_SEQUENCES.clear()
        SUPERVISOR.load_progress_state()
        self.assertEqual(SUPERVISOR.PROGRESS_SEQUENCE, 1)
        self.assertEqual(SUPERVISOR.SEEN_PROGRESS_EVENTS["progress-event-7"], 1)
        self.assertEqual(SUPERVISOR.TURN_PROGRESS_SEQUENCES["turn-progress"], 7)

    def test_active_turn_gets_factual_english_heartbeat_before_two_minutes(self):
        SUPERVISOR.register_active_turn({
            "turnId": "turn-heartbeat",
            "threadId": "thread-heartbeat",
            "startedAt": 123,
        })
        SUPERVISOR.record_progress({
            "schemaVersion": 1,
            "eventId": "progress-before-wait",
            "sequence": 4,
            "turnId": "turn-heartbeat",
            "threadId": "thread-heartbeat",
            "actionId": "trip-research",
            "state": "working",
            "message": "Verified the destination and travel dates",
            "verifiedResult": "The trip inputs are complete",
            "nextAction": "Compare current transport options",
            "technicalCategory": "verification",
        })
        last = SUPERVISOR.LAST_PROGRESS_MONOTONIC["turn-heartbeat"]
        self.assertEqual(
            SUPERVISOR.record_supervisor_heartbeats_once(
                last + SUPERVISOR.PROGRESS_HEARTBEAT_SECONDS - 1
            ),
            0,
        )
        self.assertEqual(
            SUPERVISOR.record_supervisor_heartbeats_once(
                last + SUPERVISOR.PROGRESS_HEARTBEAT_SECONDS
            ),
            1,
        )
        rows = [json.loads(line) for line in SUPERVISOR.PROGRESS_PATH.read_text().splitlines()]
        heartbeat = rows[-1]
        self.assertEqual(heartbeat["sourceSequence"], 5)
        self.assertEqual(heartbeat["technicalCategory"], "runtime")
        self.assertIn("Compare current transport options", heartbeat["message"])
        self.assertNotIn("curl", heartbeat["message"])
        self.assertLess(SUPERVISOR.PROGRESS_HEARTBEAT_SECONDS, 120)

    def test_heartbeat_without_prior_progress_reports_exact_wait_state(self):
        SUPERVISOR.register_active_turn({
            "turnId": "turn-first-result",
            "threadId": "thread-first-result",
            "startedAt": 123,
        })
        last = SUPERVISOR.LAST_PROGRESS_MONOTONIC["turn-first-result"]
        self.assertEqual(
            SUPERVISOR.record_supervisor_heartbeats_once(
                last + SUPERVISOR.PROGRESS_HEARTBEAT_SECONDS
            ),
            1,
        )
        heartbeat = json.loads(SUPERVISOR.PROGRESS_PATH.read_text().splitlines()[-1])
        self.assertIn("waiting for its first recorded result", heartbeat["message"])
        self.assertEqual(heartbeat["sourceSequence"], 1)


if __name__ == "__main__":
    unittest.main()
