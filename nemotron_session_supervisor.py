#!/data/data/com.termux/files/usr/bin/python
"""Durable, metadata-only completion ledger for Nemotron Unrestricted."""

import hashlib
import json
import os
import pathlib
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


APP_ID = "nemotron-unrestricted"
VERSION = "3"
MAX_EVENT_BYTES = 64 * 1024


def configured_port(name, default):
    try:
        port = int(os.environ.get(name, str(default)))
        return port if 1 <= port <= 65535 else default
    except ValueError:
        return default


PORT = configured_port("NEMOTRON_SUPERVISOR_PORT", 18775)
CODEX_HOME = pathlib.Path(os.environ["CODEX_HOME"])
EVENTS_PATH = CODEX_HOME / "supervisor" / "completion-events.jsonl"
LESSONS_PATH = CODEX_HOME / "supervisor" / "lessons.jsonl"
ACKS_PATH = CODEX_HOME / "supervisor" / "completion-notification-acks.jsonl"
PROGRESS_PATH = CODEX_HOME / "supervisor" / "progress-events.jsonl"
SOURCE_SHA256 = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
EVENTS_LOCK = threading.RLock()
SEQUENCE = 0
PROGRESS_SEQUENCE = 0
SEEN_COMPLETIONS = {}
SEEN_PROGRESS_EVENTS = {}
TURN_PROGRESS_SEQUENCES = {}
ACTIVE_TURNS_PATH = CODEX_HOME / "supervisor" / "active-turns.json"
GUI_PORT = configured_port("NEMOTRON_GUI_PORT", 5903)
ACTIVE_TURNS = {}
NOTIFICATION_ACKS = set()
PROGRESS_STATES = {"working", "completed", "failed", "retry", "stopped"}
PROGRESS_CATEGORIES = {
    "command", "tool", "plan", "reasoning", "recovery", "turn", "verification", "runtime",
}
RAW_PROGRESS_PREFIX = re.compile(
    r"^\s*(?:[/~]|[A-Za-z]:[\\/]|(?:bash|sh|curl|wget|git|pm|python|node|java|adb|rish)\s)",
    re.IGNORECASE,
)


def bounded_text(value, limit=256):
    return str(value or "").strip()[:limit]


def bounded_count(value):
    try:
        return max(0, min(int(value), 1_000_000))
    except (TypeError, ValueError):
        return 0


def event_key(event):
    return (bounded_text(event.get("turnId")), bounded_text(event.get("outcome"), 32))


def sanitize_event(value):
    if not isinstance(value, dict):
        raise ValueError("event must be an object")
    outcome = bounded_text(value.get("outcome"), 32).lower()
    if outcome not in {"completed", "failed", "stopped"}:
        raise ValueError("invalid completion outcome")
    turn_id = bounded_text(value.get("turnId"))
    if not turn_id:
        raise ValueError("turnId is required")
    return {
        "turnId": turn_id,
        "threadId": bounded_text(value.get("threadId")),
        "outcome": outcome,
        "durationMs": bounded_count(value.get("durationMs")),
        "effort": bounded_text(value.get("effort"), 32),
        "actionCount": bounded_count(value.get("actionCount")),
        "completedActions": bounded_count(value.get("completedActions")),
        "failureCount": bounded_count(value.get("failureCount")),
        "plannedSteps": bounded_count(value.get("plannedSteps")),
    }


def sanitize_active_turn(value):
    if not isinstance(value, dict):
        raise ValueError("active turn must be an object")
    turn_id = bounded_text(value.get("turnId"))
    thread_id = bounded_text(value.get("threadId"))
    if not turn_id or not thread_id:
        raise ValueError("threadId and turnId are required")
    return {
        "turnId": turn_id,
        "threadId": thread_id,
        "effort": bounded_text(value.get("effort"), 32),
        "startedAt": bounded_count(value.get("startedAt")),
    }


def sanitize_progress(value):
    if not isinstance(value, dict):
        raise ValueError("progress must be an object")
    turn_id = bounded_text(value.get("turnId"))
    thread_id = bounded_text(value.get("threadId"))
    event_id = bounded_text(value.get("eventId"))
    action_id = bounded_text(value.get("actionId"))
    state = bounded_text(value.get("state"), 32).lower()
    category = bounded_text(value.get("technicalCategory"), 32).lower()
    message = bounded_text(value.get("message"), 320)
    if not turn_id or not thread_id or not event_id:
        raise ValueError("threadId, turnId, and eventId are required")
    if state not in PROGRESS_STATES:
        raise ValueError("invalid progress state")
    if category not in PROGRESS_CATEGORIES:
        raise ValueError("invalid progress category")
    if len(message) < 2:
        raise ValueError("progress message is required")
    if "\n" in str(value.get("message", "")) or "\r" in str(value.get("message", "")):
        raise ValueError("progress message must be a single English summary")
    if RAW_PROGRESS_PREFIX.search(message) or message.startswith(("{", "[", "$ ")):
        raise ValueError("raw commands and transcripts are not progress messages")
    try:
        source_sequence = int(value.get("sequence", 0))
        schema_version = int(value.get("schemaVersion", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("invalid progress sequence") from error
    if source_sequence < 1 or schema_version != 1:
        raise ValueError("invalid progress sequence or schema")
    return {
        "schemaVersion": schema_version,
        "eventId": event_id,
        "sourceSequence": source_sequence,
        "turnId": turn_id,
        "threadId": thread_id,
        "actionId": action_id,
        "state": state,
        "message": message,
        "verifiedResult": bounded_text(value.get("verifiedResult"), 320),
        "nextAction": bounded_text(value.get("nextAction"), 320),
        "technicalCategory": category,
    }


def persist_active_turns():
    ACTIVE_TURNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ACTIVE_TURNS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(ACTIVE_TURNS, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    os.replace(temporary, ACTIVE_TURNS_PATH)


def register_active_turn(value):
    active = sanitize_active_turn(value)
    with EVENTS_LOCK:
        ACTIVE_TURNS[active["turnId"]] = active
        persist_active_turns()
    return {"ok": True, "turnId": active["turnId"]}


def load_active_turns():
    if not ACTIVE_TURNS_PATH.is_file():
        return
    try:
        decoded = json.loads(ACTIVE_TURNS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(decoded, dict):
        return
    with EVENTS_LOCK:
        for value in decoded.values():
            try:
                active = sanitize_active_turn(value)
            except ValueError:
                continue
            ACTIVE_TURNS[active["turnId"]] = active


def rpc(method, params):
    body = json.dumps({"method": method, "params": params}, separators=(",", ":")).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{GUI_PORT}/codex-api/rpc",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=3) as response:
        if response.status != 200:
            raise OSError("GUI RPC returned non-200 status")
        decoded = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    if not isinstance(decoded, dict) or "result" not in decoded:
        raise OSError("GUI RPC response did not contain result")
    return decoded["result"]


def text_from_message(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(filter(None, (text_from_message(item) for item in value)))
    if isinstance(value, dict):
        return next((text for key in ("text", "content", "message", "output_text") if (text := text_from_message(value.get(key)))), "")
    return ""


def substantive_agent_message(turn):
    return any(
        str(item.get("type", "")).casefold() == "agentmessage"
        and len(text_from_message(item).strip()) >= 2
        for item in turn.get("items", []) if isinstance(item, dict)
    ) if isinstance(turn, dict) else False


def monitor_active_turns_once():
    with EVENTS_LOCK:
        candidates = list(ACTIVE_TURNS.values())
    completed = []
    for active in candidates:
        try:
            result = rpc("thread/read", {"threadId": active["threadId"], "includeTurns": True})
            thread = result.get("thread", {}) if isinstance(result, dict) else {}
            turns = thread.get("turns", []) if isinstance(thread, dict) else []
            turn = next((item for item in turns if isinstance(item, dict) and item.get("id") == active["turnId"]), None)
            if turn is None:
                continue
            status = str(turn.get("status", "")).casefold()
            if status in {"completed", "complete"} and substantive_agent_message(turn):
                record_event({**active, "outcome": "completed", "durationMs": 0})
                completed.append(active["turnId"])
            elif status in {"failed", "interrupted", "cancelled", "canceled"}:
                record_event({**active, "outcome": "failed", "durationMs": 0})
                completed.append(active["turnId"])
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    if completed:
        with EVENTS_LOCK:
            for turn_id in completed:
                ACTIVE_TURNS.pop(turn_id, None)
            persist_active_turns()
    return len(completed)


def active_turn_monitor():
    while True:
        monitor_active_turns_once()
        time.sleep(5)


def load_ledger_state():
    global SEQUENCE
    if not EVENTS_PATH.exists():
        return
    with EVENTS_LOCK:
        with EVENTS_PATH.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    sequence = int(event.get("sequence", 0))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
                SEQUENCE = max(SEQUENCE, sequence)
                key = event_key(event)
                if all(key):
                    SEEN_COMPLETIONS[key] = sequence
    if ACKS_PATH.is_file():
        with ACKS_PATH.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                    sequence = int(value.get("sequence", 0))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
                if sequence > 0:
                    NOTIFICATION_ACKS.add(sequence)


def load_progress_state():
    global PROGRESS_SEQUENCE
    if not PROGRESS_PATH.is_file():
        return
    with EVENTS_LOCK, PROGRESS_PATH.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                event = json.loads(line)
                sequence = int(event.get("sequence", 0))
                source_sequence = int(event.get("sourceSequence", 0))
                event_id = bounded_text(event.get("eventId"))
                turn_id = bounded_text(event.get("turnId"))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
            if sequence < 1 or source_sequence < 1 or not event_id or not turn_id:
                continue
            PROGRESS_SEQUENCE = max(PROGRESS_SEQUENCE, sequence)
            SEEN_PROGRESS_EVENTS[event_id] = sequence
            TURN_PROGRESS_SEQUENCES[turn_id] = max(
                TURN_PROGRESS_SEQUENCES.get(turn_id, 0), source_sequence,
            )


def classify(event):
    outcome = event.get("outcome")
    if outcome == "completed":
        return "completed"
    if outcome == "failed":
        return "failed"
    if outcome == "stopped":
        return "stopped"
    return "unknown"


def append_jsonl(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def learn(event, classification):
    lesson = {
        "timestamp": event["receivedAt"],
        "turnId": event.get("turnId") or str(uuid.uuid4()),
        "classification": classification,
        "effort": event.get("effort"),
        "durationMs": event.get("durationMs"),
        "actionCount": event.get("actionCount"),
        "completedActions": event.get("completedActions"),
        "failureCount": event.get("failureCount"),
    }
    append_jsonl(LESSONS_PATH, lesson)


def record_event(value):
    global SEQUENCE
    event = sanitize_event(value)
    key = event_key(event)
    with EVENTS_LOCK:
        existing = SEEN_COMPLETIONS.get(key)
        if existing is not None:
            if ACTIVE_TURNS.pop(event["turnId"], None) is not None:
                persist_active_turns()
            return {"ok": True, "duplicate": True, "sequence": existing}
        SEQUENCE += 1
        event.update({
            "app": APP_ID,
            "sequence": SEQUENCE,
            "receivedAt": datetime.now(timezone.utc).isoformat(),
            "classification": classify(event),
        })
        append_jsonl(EVENTS_PATH, event)
        if event["classification"] in {"completed", "failed"}:
            learn(event, event["classification"])
        SEEN_COMPLETIONS[key] = SEQUENCE
        if ACTIVE_TURNS.pop(event["turnId"], None) is not None:
            persist_active_turns()
        return {"ok": True, "duplicate": False, "sequence": SEQUENCE}


def record_progress(value):
    global PROGRESS_SEQUENCE
    event = sanitize_progress(value)
    with EVENTS_LOCK:
        active = ACTIVE_TURNS.get(event["turnId"])
        if active is None or active.get("threadId") != event["threadId"]:
            raise ValueError("progress does not belong to the active turn")
        existing = SEEN_PROGRESS_EVENTS.get(event["eventId"])
        if existing is not None:
            return {"ok": True, "duplicate": True, "sequence": existing}
        previous_source_sequence = TURN_PROGRESS_SEQUENCES.get(event["turnId"], 0)
        if event["sourceSequence"] <= previous_source_sequence:
            raise ValueError("progress sequence must increase for the active turn")
        PROGRESS_SEQUENCE += 1
        event.update({
            "app": APP_ID,
            "sequence": PROGRESS_SEQUENCE,
            "receivedAt": datetime.now(timezone.utc).isoformat(),
        })
        append_jsonl(PROGRESS_PATH, event)
        SEEN_PROGRESS_EVENTS[event["eventId"]] = PROGRESS_SEQUENCE
        TURN_PROGRESS_SEQUENCES[event["turnId"]] = event["sourceSequence"]
        return {"ok": True, "duplicate": False, "sequence": PROGRESS_SEQUENCE}


def read_progress(thread_id="", turn_id="", after=0):
    events = []
    if PROGRESS_PATH.is_file():
        with EVENTS_LOCK, PROGRESS_PATH.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    sequence = int(event.get("sequence", 0))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
                if sequence <= after:
                    continue
                if thread_id and event.get("threadId") != thread_id:
                    continue
                if turn_id and event.get("turnId") != turn_id:
                    continue
                events.append(event)
    return events[-200:]


def record_notification_ack(value):
    if not isinstance(value, dict):
        raise ValueError("ack must be an object")
    try:
        sequence = int(value.get("sequence", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("invalid ack sequence") from error
    if sequence < 1 or sequence > SEQUENCE:
        raise ValueError("invalid ack sequence")
    with EVENTS_LOCK:
        if sequence in NOTIFICATION_ACKS:
            return {"ok": True, "duplicate": True, "sequence": sequence}
        record = {
            "app": APP_ID,
            "sequence": sequence,
            "notification": "terminal-ringtone",
            "waveform": "nemotron-six-note-v1",
            "sampleRateHz": 48000,
            "durationMs": 3000,
            "relativeVolume": 50,
            "receivedAt": datetime.now(timezone.utc).isoformat(),
        }
        append_jsonl(ACKS_PATH, record)
        NOTIFICATION_ACKS.add(sequence)
        return {"ok": True, "duplicate": False, "sequence": sequence}


class Handler(BaseHTTPRequestHandler):
    def write_json(self, status, value):
        body = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {"/event", "/active", "/ack", "/progress"}:
            self.write_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.write_json(400, {"ok": False, "error": "invalid_content_length"})
            return
        if length < 1 or length > MAX_EVENT_BYTES:
            self.write_json(413 if length > MAX_EVENT_BYTES else 400, {"ok": False, "error": "invalid_event_size"})
            return
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/active":
                result = register_active_turn(value)
            elif path == "/ack":
                result = record_notification_ack(value)
            elif path == "/progress":
                result = record_progress(value)
            else:
                result = record_event(value)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self.write_json(400, {"ok": False, "error": bounded_text(error, 120)})
            return
        self.write_json(200, result)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            with EVENTS_LOCK:
                payload = {
                    "status": "ok",
                    "app": APP_ID,
                    "version": VERSION,
                    "port": PORT,
                    "sourceSha256": SOURCE_SHA256,
                    "sequence": SEQUENCE,
                    "completionCount": len(SEEN_COMPLETIONS),
                    "progressSequence": PROGRESS_SEQUENCE,
                    "progressEventCount": len(SEEN_PROGRESS_EVENTS),
                    "activeTurnCount": len(ACTIVE_TURNS),
                    "notificationAckCount": len(NOTIFICATION_ACKS),
                    "lastNotificationSequence": max(NOTIFICATION_ACKS, default=0),
                    "guiPort": GUI_PORT,
                }
            self.write_json(200, payload)
        elif path == "/events":
            try:
                after = max(0, int(dict(
                    pair.split("=", 1) for pair in urlsplit(self.path).query.split("&") if "=" in pair
                ).get("after", "0")))
            except ValueError:
                after = 0
            events = []
            if EVENTS_PATH.is_file():
                with EVENTS_LOCK, EVENTS_PATH.open("r", encoding="utf-8", errors="replace") as stream:
                    for line in stream:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if int(event.get("sequence", 0)) > after:
                            events.append(event)
            with EVENTS_LOCK:
                active_turn_count = len(ACTIVE_TURNS)
            self.write_json(200, {
                "ok": True,
                "events": events[-100:],
                "sequence": SEQUENCE,
                "activeTurnCount": active_turn_count,
            })
        elif path == "/progress":
            query = parse_qs(urlsplit(self.path).query)
            try:
                after = max(0, int(query.get("after", ["0"])[0]))
            except (TypeError, ValueError):
                after = 0
            events = read_progress(
                bounded_text(query.get("threadId", [""])[0]),
                bounded_text(query.get("turnId", [""])[0]),
                after,
            )
            self.write_json(200, {
                "ok": True,
                "events": events,
                "sequence": PROGRESS_SEQUENCE,
            })
        else:
            self.write_json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format, *args):
        pass


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def serve():
    load_ledger_state()
    load_progress_state()
    load_active_turns()
    threading.Thread(target=active_turn_monitor, name="nemotron-active-turn-monitor", daemon=True).start()
    Server(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    serve()
