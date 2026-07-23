#!/data/data/com.termux/files/usr/bin/python
"""OpenRouter proxy for the isolated Nemotron Unrestricted runtime."""

import hashlib
import http.client
import json
import math
import os
import pathlib
import random
import re
import socket
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

UPSTREAM = "https://openrouter.ai/api/v1"
PUBLIC_CATALOG_URL = f"{UPSTREAM}/models"
OPENROUTER_USAGE_URL = f"{UPSTREAM}/key"

def configured_port(name, default):
    try:
        port = int(os.environ.get(name, str(default)))
        return port if 1 <= port <= 65535 else default
    except ValueError:
        return default

def configured_seconds(name, default):
    try:
        seconds = float(os.environ.get(name, str(default)))
        return seconds if 0.05 <= seconds <= 60.0 else default
    except ValueError:
        return default

def configured_integer(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
        return value if minimum <= value <= maximum else default
    except (TypeError, ValueError):
        return default

PORT = configured_port("NEMOTRON_PROXY_PORT", 18774)
GUI_PORT = configured_port("NEMOTRON_GUI_PORT", 5903)
SUPERVISOR_PORT = configured_port("NEMOTRON_SUPERVISOR_PORT", 18775)
PROVIDER_BASE_URL = f"http://127.0.0.1:{PORT}/v1"
APP_ID = "nemotron-unrestricted"
DEFAULT_MODEL = "nousresearch/hermes-4-405b"
EXACT_NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
EXACT_NEMOTRON_FREE_MODEL = f"{EXACT_NEMOTRON_MODEL}:free"
EXACT_NEMOTRON_UPSTREAM_PROVIDER = "Together"
EXACT_NEMOTRON_ENDPOINTS_URL = (
    f"{PUBLIC_CATALOG_URL}/{EXACT_NEMOTRON_MODEL}/endpoints"
)
REQUESTED_DOLPHIN_MODEL = "cognitivecomputations/Dolphin-3.0-Llama-3.1-405B"
AVAILABLE_DOLPHIN_MODEL = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
DOLPHIN_X1_MODEL = "dphn/Dolphin-X1-Llama-3.1-405B"
DOLPHIN_X1_BASE_URL = os.environ.get("DOLPHIN_X1_BASE_URL", "").strip().rstrip("/")
DOLPHIN_X1_HEALTH_TTL_SECONDS = configured_seconds("DOLPHIN_X1_HEALTH_TTL_SECONDS", 5.0)
DOLPHIN_X1_HEALTH_TIMEOUT_SECONDS = configured_seconds("DOLPHIN_X1_HEALTH_TIMEOUT_SECONDS", 0.75)
DEFAULT_TOOL_MODEL = "cohere/north-mini-code:free"
TOOL_FALLBACK_MODEL = "poolside/laguna-xs-2.1:free"
PREFERRED_VISION_MODELS = (
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "openrouter/free",
)
CODEX_HOME = pathlib.Path(os.environ["CODEX_HOME"])
AUDIT_PATH = CODEX_HOME / "logs" / "openrouter-request-audit.jsonl"
COMPLETION_EVENTS = CODEX_HOME / "supervisor" / "completion-events.jsonl"
ACTIVE_TURNS_PATH = CODEX_HOME / "supervisor" / "active-turns.json"
RUNTIME_SELECTION_PATH = CODEX_HOME / "supervisor" / "runtime-selection.json"
AUDIT_LOCK = threading.Lock()
RUNTIME_SELECTION_LOCK = threading.RLock()
RUNTIME_SELECTION = {
    "generation": 0,
    "verificationStatus": "unverified",
    "requestedProvider": None,
    "requestedModel": None,
    "requestedEffort": None,
    "requestedReasoningBudget": None,
    "effectiveProvider": None,
    "effectiveGateway": None,
    "effectiveModel": None,
    "effectiveEffort": None,
    "effectiveReasoningTokens": None,
    "reasoningBudget": None,
    "threadId": None,
    "turnId": None,
    "requestedAt": None,
    "effectiveAt": None,
    "requestId": None,
    "responseId": None,
    "pendingRequestId": None,
    "dispatchedGeneration": None,
    "confirmedGeneration": None,
    "failureType": None,
    "modelSubstitution": False,
    "turns": {},
}
try:
    REQUEST_CONCURRENCY = max(1, min(int(os.environ.get("OPENROUTER_PROXY_CONCURRENCY", "8")), 64))
except ValueError:
    REQUEST_CONCURRENCY = 8
REQUEST_SLOTS = threading.BoundedSemaphore(REQUEST_CONCURRENCY)
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_RUNTIME_TURNS = 64
MAX_BUFFERED_RESPONSE = 32 * 1024 * 1024
MAX_CATALOG_RESPONSE = 8 * 1024 * 1024
RETRYABLE = {429, 500, 502, 503, 504}
REQUEST_DEADLINE_SECONDS = configured_integer("OPENROUTER_REQUEST_DEADLINE_SECONDS", 360, 30, 900)
DOLPHIN_X1_REQUEST_DEADLINE_SECONDS = configured_integer(
    "DOLPHIN_X1_REQUEST_DEADLINE_SECONDS", 900, 60, 3600
)
MAX_UPSTREAM_ATTEMPTS = 6
MAX_REASONING_BUDGET = 128_000
MAX_REASONING_BUDGETS = {EXACT_NEMOTRON_MODEL: MAX_REASONING_BUDGET}
SSE_HEARTBEAT_SECONDS = configured_seconds("NEMOTRON_SSE_HEARTBEAT_SECONDS", 3.0)
CATALOG_FETCH_TIMEOUT_SECONDS = configured_seconds("NEMOTRON_CATALOG_FETCH_TIMEOUT_SECONDS", 5.0)
CATALOG_TTL_SECONDS = configured_seconds("NEMOTRON_CATALOG_TTL_SECONDS", 300.0)
CATALOG_MAX_STALE_SECONDS = 24 * 60 * 60
CAPABILITY_FETCH_TIMEOUT_SECONDS = configured_seconds(
    "NEMOTRON_CAPABILITY_FETCH_TIMEOUT_SECONDS", 5.0
)
CAPABILITY_TTL_SECONDS = configured_seconds("NEMOTRON_CAPABILITY_TTL_SECONDS", 60.0)
MAX_CAPABILITY_RESPONSE = 512 * 1024
SCHEMA_MAX_DEPTH = 64
COMPACTION_MARKER = "OPENROUTER_INTERNAL_CONTEXT_CHECKPOINT"
POST_COMPACTION_PREFIX = "Another language model started to solve this problem"
SOURCE_SHA256 = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
SUPERVISOR_SOURCE = pathlib.Path(__file__).with_name("nemotron_session_supervisor.py")
SUPERVISOR_SOURCE_SHA256 = hashlib.sha256(SUPERVISOR_SOURCE.read_bytes()).hexdigest()
CAPABILITY_CONTRACT_PATH = pathlib.Path(__file__).with_name("capabilities") / "NEMOTRON_AGENT_CONTRACT.md"
CAPABILITY_MATRIX_PATH = pathlib.Path(__file__).with_name("capabilities") / "capability-matrix.json"
MODEL_CAPABILITY_CONTRACT_SHA256 = hashlib.sha256(
    CAPABILITY_CONTRACT_PATH.read_bytes() + b"\0" + CAPABILITY_MATRIX_PATH.read_bytes()
).hexdigest()

CONFIGURED_MODELS = [
    "nousresearch/hermes-4-405b",
    "nousresearch/hermes-3-llama-3.1-405b",
    AVAILABLE_DOLPHIN_MODEL,
    "microsoft/wizardlm-2-8x22b",
    "nousresearch/hermes-3-llama-3.1-70b",
    "mistralai/mistral-large",
    "meta-llama/llama-3.3-70b-instruct",
    EXACT_NEMOTRON_MODEL,
    EXACT_NEMOTRON_FREE_MODEL,
    "nvidia/nemotron-3-super-120b-a12b:free",
    "cohere/north-mini-code:free",
    "poolside/laguna-xs-2.1:free",
    *PREFERRED_VISION_MODELS,
]
LIVE_GATED_MODELS = frozenset((EXACT_NEMOTRON_MODEL, EXACT_NEMOTRON_FREE_MODEL))
TOOL_CAPABLE_MODELS = {DEFAULT_TOOL_MODEL, TOOL_FALLBACK_MODEL}

DOLPHIN_X1_HEALTH_LOCK = threading.Lock()
DOLPHIN_X1_HEALTH_CACHE = {"available": False, "checkedAt": 0.0, "error": "not_configured"}

CATALOG_LOCK = threading.Lock()
CATALOG_REFRESH_CONDITION = threading.Condition(CATALOG_LOCK)
CATALOG_CACHE = {"models": {}, "loadedAt": 0.0}
CATALOG_REFRESHING = False

EXACT_CAPABILITY_LOCK = threading.Lock()
EXACT_CAPABILITY_CONDITION = threading.Condition(EXACT_CAPABILITY_LOCK)
EXACT_CAPABILITY_CACHE = {
    "fingerprint": None,
    "checkedAt": 0.0,
    "result": None,
}
EXACT_CAPABILITY_REFRESHING = False

class CatalogUnavailableError(RuntimeError):
    """The public catalog had no currently eligible free tool model."""

class InvalidReasoningEffortError(ValueError):
    """The request contained an unknown or contradictory effort value."""

class ModelUnavailableError(ValueError):
    """The explicitly selected model is absent from the current provider catalog."""

def dolphin_x1_health(*, allow_network=False):
    """Return verified availability for the exact local Dolphin X1 405B route.

    The model is never advertised from configuration alone.  A fresh successful
    HTTP health response from the paired-PC llama.cpp server is required.
    """
    now = time.monotonic()
    with DOLPHIN_X1_HEALTH_LOCK:
        cached = dict(DOLPHIN_X1_HEALTH_CACHE)
        age = max(0.0, now - cached["checkedAt"]) if cached["checkedAt"] else None
        if age is not None and age <= DOLPHIN_X1_HEALTH_TTL_SECONDS:
            cached["ageSeconds"] = round(age, 3)
            return cached
    if not allow_network or not DOLPHIN_X1_BASE_URL.startswith(("http://", "https://")):
        cached["ageSeconds"] = round(age, 3) if age is not None else None
        return cached
    health_url = DOLPHIN_X1_BASE_URL.removesuffix("/v1") + "/health"
    request = urllib.request.Request(health_url, headers={"Accept": "application/json"}, method="GET")
    available = False
    error = "unreachable"
    try:
        with urllib.request.urlopen(request, timeout=DOLPHIN_X1_HEALTH_TIMEOUT_SECONDS) as response:
            body = response.read(1024 * 1024)
            available = response.getcode() == 200
            if available:
                try:
                    value = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    value = None
                available = isinstance(value, dict) and value.get("status") == "ok"
            error = None if available else "invalid_health_response"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        pass
    state = {"available": available, "checkedAt": time.monotonic(), "error": error, "ageSeconds": 0.0}
    with DOLPHIN_X1_HEALTH_LOCK:
        DOLPHIN_X1_HEALTH_CACHE.update(state)
    return state

def upstream_route(model):
    if model == DOLPHIN_X1_MODEL:
        return {
            "provider": "paired-pc-llama.cpp",
            "baseUrl": DOLPHIN_X1_BASE_URL,
            "apiKey": None,
        }
    return {"provider": "OpenRouter", "baseUrl": UPSTREAM, "apiKey": None}

REASONING_EFFORTS = frozenset(("none", "minimal", "low", "medium", "high", "xhigh", "max"))

def normalize_reasoning_effort(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidReasoningEffortError("Reasoning effort must be a string")
    compact = "".join(character for character in value.strip().casefold() if character not in " _-")
    aliases = {
        "none": "none", "minimal": "minimal", "low": "low", "medium": "medium",
        "high": "high", "xhigh": "xhigh", "extrahigh": "xhigh", "max": "max",
    }
    normalized = aliases.get(compact)
    if normalized not in REASONING_EFFORTS:
        raise InvalidReasoningEffortError("Unsupported reasoning effort")
    return normalized


def bounded_selection_text(value, limit=256):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("selection fields must be strings")
    result = value.strip()
    if not result or len(result) > limit or any(ord(character) < 32 for character in result):
        raise ValueError("selection field is invalid")
    return result


def runtime_turn_key(thread_id, turn_id):
    thread = bounded_selection_text(thread_id)
    turn = bounded_selection_text(turn_id)
    return hashlib.sha256(f"{thread}\0{turn}".encode("utf-8")).hexdigest()[:32]


def update_runtime_turn(thread_id, turn_id, **values):
    if not thread_id or not turn_id:
        return None
    key = runtime_turn_key(thread_id, turn_id)
    allowed = {
        "generation", "verificationStatus", "requestedProvider", "requestedModel",
        "requestedEffort", "requestedReasoningBudget", "requestedAt",
        "dispatchedAt", "requestId", "effectiveGateway", "effectiveProvider",
        "effectiveModel", "effectiveEffort", "effectiveReasoningTokens",
        "reasoningBudget", "effectiveAt", "responseId", "failureType",
        "modelSubstitution",
    }
    with RUNTIME_SELECTION_LOCK:
        turns = RUNTIME_SELECTION.setdefault("turns", {})
        record = dict(turns.get(key, {}))
        record.update({"threadId": thread_id, "turnId": turn_id})
        for name, value in values.items():
            if name in allowed and (value is None or isinstance(value, (str, int, bool))):
                record[name] = value
        record["updatedAt"] = datetime.now(timezone.utc).isoformat()
        turns[key] = record
        if len(turns) > MAX_RUNTIME_TURNS:
            oldest = sorted(turns, key=lambda item: str(turns[item].get("updatedAt", "")))
            for stale_key in oldest[:len(turns) - MAX_RUNTIME_TURNS]:
                turns.pop(stale_key, None)
        return dict(record)


def read_active_turns():
    try:
        metadata = ACTIVE_TURNS_PATH.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or metadata.st_size > 256 * 1024:
            return []
        decoded = json.loads(ACTIVE_TURNS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, dict):
        return []
    result = []
    for value in decoded.values():
        if not isinstance(value, dict):
            continue
        thread_id = value.get("threadId")
        turn_id = value.get("turnId")
        if isinstance(thread_id, str) and thread_id and isinstance(turn_id, str) and turn_id:
            result.append({"threadId": thread_id[:256], "turnId": turn_id[:256]})
    return result


def persist_runtime_selection():
    RUNTIME_SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RUNTIME_SELECTION_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(RUNTIME_SELECTION, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, RUNTIME_SELECTION_PATH)


def runtime_selection_payload():
    with RUNTIME_SELECTION_LOCK:
        state = dict(RUNTIME_SELECTION)
        turns = dict(state.pop("turns", {}))
    current_turn = None
    if state.get("threadId") and state.get("turnId"):
        try:
            current_turn = turns.get(runtime_turn_key(state["threadId"], state["turnId"]))
        except ValueError:
            current_turn = None
    state.update({
        "status": "ok",
        "app": APP_ID,
        "provider": state.get("requestedProvider"),
        "model": state.get("requestedModel"),
        "effort": state.get("requestedEffort"),
        "activeTurnCount": len(read_active_turns()),
        "trackedTurnCount": len(turns),
        "currentTurn": dict(current_turn) if isinstance(current_turn, dict) else None,
        "identityVerified": bool(
            state.get("verificationStatus") == "confirmed"
            and state.get("confirmedGeneration") == state.get("generation")
            and state.get("effectiveProvider")
            and state.get("effectiveModel")
            and not state.get("modelSubstitution")
        ),
        "effortVerified": bool(
            state.get("verificationStatus") == "confirmed"
            and state.get("confirmedGeneration") == state.get("generation")
            and state.get("effectiveEffort")
        ),
    })
    state["verified"] = state["identityVerified"] and state["effortVerified"]
    return state


def update_runtime_selection(value):
    if not isinstance(value, dict):
        raise ValueError("selection must be an object")
    allowed = {"threadId", "turnId", "model", "effort"}
    if set(value) - allowed:
        raise ValueError("unknown selection field")
    model = bounded_selection_text(value.get("model")) if value.get("model") is not None else None
    effort = normalize_reasoning_effort(value.get("effort")) if value.get("effort") is not None else None
    thread_id = bounded_selection_text(value.get("threadId")) if value.get("threadId") is not None else None
    turn_id = bounded_selection_text(value.get("turnId")) if value.get("turnId") is not None else None
    if model is None and effort is None:
        raise ValueError("model or effort is required")
    snapshot = None
    if model is not None:
        snapshot = (
            current_exact_nemotron_snapshot()
            if model in LIVE_GATED_MODELS
            else catalog_snapshot(allow_network=True)
        )
        local_model = model == DOLPHIN_X1_MODEL and dolphin_x1_health(allow_network=True)["available"]
        if model not in snapshot["models"] and not local_model:
            if model in LIVE_GATED_MODELS:
                raise ModelUnavailableError(exact_nemotron_unavailable_message(snapshot))
            raise ModelUnavailableError("Selected model is unavailable from the current provider catalog")
        provider = upstream_route(model)["provider"]
    else:
        provider = None
    if effort == "max":
        with RUNTIME_SELECTION_LOCK:
            effort_model = model or RUNTIME_SELECTION.get("requestedModel")
        if not effort_model:
            raise InvalidReasoningEffortError("Max effort requires a verified selected model")
        if snapshot is None or effort_model != model:
            snapshot = (
                current_exact_nemotron_snapshot()
                if effort_model in LIVE_GATED_MODELS
                else current_tool_catalog_snapshot()
            )
        reasoning_budget_for(effort_model, snapshot)
    with RUNTIME_SELECTION_LOCK:
        RUNTIME_SELECTION["generation"] = int(RUNTIME_SELECTION.get("generation", 0)) + 1
        if model is not None:
            RUNTIME_SELECTION["requestedModel"] = model
            RUNTIME_SELECTION["requestedProvider"] = provider
        if effort is not None:
            RUNTIME_SELECTION["requestedEffort"] = effort
            RUNTIME_SELECTION["requestedReasoningBudget"] = (
                reasoning_budget_for(
                    model or RUNTIME_SELECTION.get("requestedModel"), snapshot
                ) if effort == "max" else None
            )
        RUNTIME_SELECTION["threadId"] = thread_id
        RUNTIME_SELECTION["turnId"] = turn_id if turn_id and not turn_id.startswith("pending-") else None
        RUNTIME_SELECTION["requestedAt"] = datetime.now(timezone.utc).isoformat()
        RUNTIME_SELECTION["verificationStatus"] = "selected"
        RUNTIME_SELECTION["pendingRequestId"] = None
        RUNTIME_SELECTION["failureType"] = None
        RUNTIME_SELECTION["modelSubstitution"] = False
        if RUNTIME_SELECTION.get("threadId") and RUNTIME_SELECTION.get("turnId"):
            update_runtime_turn(
                RUNTIME_SELECTION["threadId"],
                RUNTIME_SELECTION["turnId"],
                generation=RUNTIME_SELECTION["generation"],
                verificationStatus="selected",
                requestedProvider=RUNTIME_SELECTION.get("requestedProvider"),
                requestedModel=RUNTIME_SELECTION.get("requestedModel"),
                requestedEffort=RUNTIME_SELECTION.get("requestedEffort"),
                requestedReasoningBudget=RUNTIME_SELECTION.get("requestedReasoningBudget"),
                requestedAt=RUNTIME_SELECTION.get("requestedAt"),
                modelSubstitution=False,
            )
        persist_runtime_selection()
    return runtime_selection_payload()


def runtime_override_for_request(payload):
    with RUNTIME_SELECTION_LOCK:
        selection = dict(RUNTIME_SELECTION)
    thread_id = selection.get("threadId")
    if not thread_id:
        return payload, None
    deadline = time.monotonic() + 1.0
    matching = []
    while True:
        active = read_active_turns()
        matching = [item for item in active if item["threadId"] == thread_id]
        if len(matching) == 1:
            break
        if time.monotonic() >= deadline:
            return payload, None
        time.sleep(0.05)
    requested_turn = selection.get("turnId")
    if requested_turn and matching[0]["turnId"] != requested_turn:
        return payload, None
    result = dict(payload)
    model = selection.get("requestedModel")
    effort = selection.get("requestedEffort")
    if model:
        result["model"] = model
    if effort:
        result.pop("reasoning_effort", None)
        reasoning = dict(result["reasoning"]) if isinstance(result.get("reasoning"), dict) else {}
        reasoning["effort"] = effort
        result["reasoning"] = reasoning
    with RUNTIME_SELECTION_LOCK:
        RUNTIME_SELECTION["turnId"] = matching[0]["turnId"]
        update_runtime_turn(
            thread_id,
            matching[0]["turnId"],
            generation=selection.get("generation"),
            verificationStatus=selection.get("verificationStatus") or "selected",
            requestedProvider=selection.get("requestedProvider"),
            requestedModel=model,
            requestedEffort=effort,
            requestedReasoningBudget=selection.get("requestedReasoningBudget"),
            requestedAt=selection.get("requestedAt"),
            modelSubstitution=False,
        )
        persist_runtime_selection()
    return result, {"generation": selection["generation"], "threadId": thread_id, "turnId": matching[0]["turnId"]}


def record_dispatched_runtime_selection(metadata, route, request_id):
    if not metadata.get("selectionApplied"):
        return False
    generation = metadata.get("selectionGeneration")
    with RUNTIME_SELECTION_LOCK:
        if generation is not None and generation != RUNTIME_SELECTION.get("generation"):
            return False
        RUNTIME_SELECTION.update({
            "verificationStatus": "dispatched",
            "requestedProvider": route.get("provider"),
            "requestedReasoningBudget": metadata.get("reasoningBudget"),
            "requestId": request_id,
            "pendingRequestId": request_id,
            "dispatchedGeneration": generation,
            "failureType": None,
            "modelSubstitution": False,
        })
        if metadata.get("selectionApplied"):
            RUNTIME_SELECTION["requestedModel"] = metadata.get("requestedModel")
            RUNTIME_SELECTION["requestedEffort"] = metadata.get("transportEffort")
        update_runtime_turn(
            metadata.get("threadId"),
            metadata.get("turnId"),
            generation=generation,
            verificationStatus="dispatched",
            requestedProvider=route.get("provider"),
            requestedModel=metadata.get("requestedModel"),
            requestedEffort=metadata.get("transportEffort"),
            requestedReasoningBudget=metadata.get("reasoningBudget"),
            requestedAt=RUNTIME_SELECTION.get("requestedAt"),
            dispatchedAt=datetime.now(timezone.utc).isoformat(),
            requestId=request_id,
            modelSubstitution=False,
        )
        persist_runtime_selection()
    return True


def record_confirmed_runtime_selection(metadata, route, request_id, evidence):
    if not metadata.get("selectionApplied"):
        return False
    generation = metadata.get("selectionGeneration")
    model = evidence.get("model")
    provider = evidence.get("provider")
    substitution = bool(model and model != metadata.get("model"))
    with RUNTIME_SELECTION_LOCK:
        if generation is not None and generation != RUNTIME_SELECTION.get("generation"):
            return False
        RUNTIME_SELECTION.update({
            "verificationStatus": "confirmed",
            "effectiveGateway": route.get("provider"),
            "effectiveProvider": provider,
            "effectiveModel": model,
            "effectiveEffort": evidence.get("effort"),
            "effectiveReasoningTokens": evidence.get("reasoningTokens"),
            "reasoningBudget": evidence.get("reasoningBudget"),
            "effectiveAt": datetime.now(timezone.utc).isoformat(),
            "requestId": request_id,
            "responseId": evidence.get("responseId"),
            "pendingRequestId": None,
            "confirmedGeneration": generation,
            "failureType": None,
            "modelSubstitution": substitution,
        })
        update_runtime_turn(
            metadata.get("threadId"),
            metadata.get("turnId"),
            generation=generation,
            verificationStatus="confirmed",
            effectiveGateway=route.get("provider"),
            effectiveProvider=provider,
            effectiveModel=model,
            effectiveEffort=evidence.get("effort"),
            effectiveReasoningTokens=evidence.get("reasoningTokens"),
            reasoningBudget=evidence.get("reasoningBudget"),
            effectiveAt=RUNTIME_SELECTION.get("effectiveAt"),
            requestId=request_id,
            responseId=evidence.get("responseId"),
            failureType=None,
            modelSubstitution=substitution,
        )
        persist_runtime_selection()
    return True


def record_runtime_failure(request_id, error_type):
    with RUNTIME_SELECTION_LOCK:
        if request_id != RUNTIME_SELECTION.get("pendingRequestId"):
            return False
        RUNTIME_SELECTION["verificationStatus"] = "failed"
        RUNTIME_SELECTION["pendingRequestId"] = None
        RUNTIME_SELECTION["failureType"] = bounded_selection_text(error_type, 128)
        current_thread = RUNTIME_SELECTION.get("threadId")
        current_turn = RUNTIME_SELECTION.get("turnId")
        update_runtime_turn(
            current_thread,
            current_turn,
            generation=RUNTIME_SELECTION.get("generation"),
            verificationStatus="failed",
            failureType=RUNTIME_SELECTION["failureType"],
            requestId=request_id,
        )
        persist_runtime_selection()
    return True


def load_runtime_selection():
    try:
        metadata = RUNTIME_SELECTION_PATH.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or metadata.st_size > 64 * 1024:
            return
        decoded = json.loads(RUNTIME_SELECTION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(decoded, dict):
        return
    with RUNTIME_SELECTION_LOCK:
        for key in RUNTIME_SELECTION:
            value = decoded.get(key)
            if key == "generation" and isinstance(value, int) and 0 <= value <= 1_000_000_000:
                RUNTIME_SELECTION[key] = value
            elif key == "turns" and isinstance(value, dict):
                restored = {}
                for record_key, record in list(value.items())[-MAX_RUNTIME_TURNS:]:
                    if not isinstance(record_key, str) or not re.fullmatch(r"[a-f0-9]{32}", record_key):
                        continue
                    if not isinstance(record, dict):
                        continue
                    try:
                        if runtime_turn_key(record.get("threadId"), record.get("turnId")) != record_key:
                            continue
                    except ValueError:
                        continue
                    safe = {}
                    for name, item in record.items():
                        if item is None or isinstance(item, (str, int, bool)):
                            safe[name] = item
                    restored[record_key] = safe
                RUNTIME_SELECTION[key] = restored
            elif key == "modelSubstitution" and isinstance(value, bool):
                RUNTIME_SELECTION[key] = value
            elif key not in {"generation", "modelSubstitution", "turns"} and (value is None or isinstance(value, (str, int))):
                RUNTIME_SELECTION[key] = value


load_runtime_selection()

def price_is_zero(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return number.is_finite() and number == 0

def normalize_catalog_entry(value, *, static=False):
    if not isinstance(value, dict):
        return None
    model_id = value.get("id")
    if not isinstance(model_id, str) or not model_id or len(model_id) > 256:
        return None
    supported = value.get("supported_parameters", value.get("supportedParameters", []))
    if not isinstance(supported, list):
        supported = []
    supported = frozenset(item for item in supported if isinstance(item, str))
    architecture = value.get("architecture") if isinstance(value.get("architecture"), dict) else {}
    input_modalities = architecture.get("input_modalities", architecture.get("inputModalities", []))
    output_modalities = architecture.get("output_modalities", architecture.get("outputModalities", []))
    if not isinstance(input_modalities, list):
        input_modalities = []
    if not isinstance(output_modalities, list):
        output_modalities = []
    input_modalities = frozenset(
        item.casefold() for item in input_modalities if isinstance(item, str)
    )
    output_modalities = frozenset(
        item.casefold() for item in output_modalities if isinstance(item, str)
    )
    pricing = value.get("pricing") if isinstance(value.get("pricing"), dict) else {}
    reasoning = value.get("reasoning") if isinstance(value.get("reasoning"), dict) else {}
    zero_price = static or (
        price_is_zero(pricing.get("prompt")) and price_is_zero(pricing.get("completion"))
    )
    try:
        created = max(0, int(value.get("created", 0)))
    except (TypeError, ValueError):
        created = 0
    return {
        "id": model_id,
        "created": created,
        "owned_by": model_id.split("/", 1)[0],
        "supported": supported,
        "inputModalities": input_modalities,
        "outputModalities": output_modalities,
        "zeroPrice": zero_price,
        "supportsReasoningMaxTokens": reasoning.get("supports_max_tokens") is True,
        "supportedReasoningEfforts": tuple(
            effort for effort in reasoning.get("supported_efforts", [])
            if isinstance(effort, str) and effort in REASONING_EFFORTS
        ) if isinstance(reasoning.get("supported_efforts"), list) else (),
    }

def static_catalog_snapshot():
    models = {}
    for model_id in CONFIGURED_MODELS:
        entry = normalize_catalog_entry({
            "id": model_id,
            "supported_parameters": ["tools", "tool_choice"] if model_id in TOOL_CAPABLE_MODELS else [],
        }, static=model_id in TOOL_CAPABLE_MODELS)
        models[model_id] = entry
    return {"models": models, "source": "static", "ageSeconds": None}

def fetch_public_catalog():
    request = urllib.request.Request(
        PUBLIC_CATALOG_URL,
        headers={"Accept": "application/json", "User-Agent": "Nemotron-Unrestricted-Catalog/1.0"},
        method="GET",
    )
    response = None
    try:
        response = urllib.request.urlopen(request, timeout=CATALOG_FETCH_TIMEOUT_SECONDS)
        if response.getcode() != 200:
            raise CatalogUnavailableError("catalog status")
        content_type = str(response.headers.get("Content-Type", ""))
        if "json" not in content_type.lower():
            raise CatalogUnavailableError("catalog content type")
        body = response.read(MAX_CATALOG_RESPONSE + 1)
        if len(body) > MAX_CATALOG_RESPONSE:
            raise CatalogUnavailableError("catalog response limit")
    except (CatalogUnavailableError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise
    finally:
        if response is not None:
            response.close()
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogUnavailableError("catalog JSON") from error
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise CatalogUnavailableError("catalog schema")
    models = {}
    for row in rows:
        entry = normalize_catalog_entry(row)
        if entry is not None:
            models[entry["id"]] = entry
    if not models:
        raise CatalogUnavailableError("empty catalog")
    return models

def refresh_public_catalog_in_background():
    global CATALOG_REFRESHING
    try:
        try:
            models = fetch_public_catalog()
        except Exception:
            models = None
        with CATALOG_LOCK:
            if models:
                CATALOG_CACHE["models"] = dict(models)
                CATALOG_CACHE["loadedAt"] = time.monotonic()
    finally:
        with CATALOG_REFRESH_CONDITION:
            CATALOG_REFRESHING = False
            CATALOG_REFRESH_CONDITION.notify_all()

def catalog_snapshot(*, allow_network=False):
    global CATALOG_REFRESHING

    def cached_or_static(now):
        cached_models = CATALOG_CACHE["models"]
        loaded_at = CATALOG_CACHE["loadedAt"]
        age = max(0.0, now - loaded_at) if loaded_at else None
        if cached_models and age is not None and age <= CATALOG_MAX_STALE_SECONDS:
            return {"models": dict(cached_models), "source": "stale", "ageSeconds": round(age, 3)}
        return static_catalog_snapshot()

    start_refresh = False
    now = time.monotonic()
    with CATALOG_LOCK:
        cached_models = CATALOG_CACHE["models"]
        loaded_at = CATALOG_CACHE["loadedAt"]
        age = max(0.0, now - loaded_at) if loaded_at else None
        if cached_models and age is not None and age <= CATALOG_TTL_SECONDS:
            return {"models": dict(cached_models), "source": "live", "ageSeconds": round(age, 3)}
        continuity = cached_or_static(now)
        if allow_network and not CATALOG_REFRESHING:
            CATALOG_REFRESHING = True
            start_refresh = True

    if start_refresh:
        try:
            threading.Thread(
                target=refresh_public_catalog_in_background,
                name="nemotron-catalog-refresh",
                daemon=True,
            ).start()
        except (OSError, RuntimeError):
            with CATALOG_REFRESH_CONDITION:
                CATALOG_REFRESHING = False
                CATALOG_REFRESH_CONDITION.notify_all()
    return continuity

def current_tool_catalog_snapshot():
    """Return only a fresh public catalog for a tool-bearing request.

    Static candidates are useful for catalog display continuity, but they are not
    evidence that a currently free model still supports tools. A tool request
    therefore waits once, within the catalog timeout, for fresh metadata and
    fails clearly if the provider catalog cannot be verified.
    """
    global CATALOG_REFRESHING

    with CATALOG_REFRESH_CONDITION:
        now = time.monotonic()
        cached_models = CATALOG_CACHE["models"]
        loaded_at = CATALOG_CACHE["loadedAt"]
        age = max(0.0, now - loaded_at) if loaded_at else None
        if cached_models and age is not None and age <= CATALOG_TTL_SECONDS:
            return {"models": dict(cached_models), "source": "live", "ageSeconds": round(age, 3)}

        if CATALOG_REFRESHING:
            deadline = time.monotonic() + CATALOG_FETCH_TIMEOUT_SECONDS
            while CATALOG_REFRESHING:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CatalogUnavailableError("current tool catalog refresh timed out")
                CATALOG_REFRESH_CONDITION.wait(remaining)
            now = time.monotonic()
            cached_models = CATALOG_CACHE["models"]
            loaded_at = CATALOG_CACHE["loadedAt"]
            age = max(0.0, now - loaded_at) if loaded_at else None
            if cached_models and age is not None and age <= CATALOG_TTL_SECONDS:
                return {"models": dict(cached_models), "source": "live", "ageSeconds": round(age, 3)}

        CATALOG_REFRESHING = True

    try:
        models = fetch_public_catalog()
    except Exception as error:
        with CATALOG_REFRESH_CONDITION:
            CATALOG_REFRESHING = False
            CATALOG_REFRESH_CONDITION.notify_all()
        raise CatalogUnavailableError("current tool catalog is unavailable") from error

    with CATALOG_REFRESH_CONDITION:
        CATALOG_CACHE["models"] = dict(models)
        CATALOG_CACHE["loadedAt"] = time.monotonic()
        CATALOG_REFRESHING = False
        CATALOG_REFRESH_CONDITION.notify_all()
        return {"models": dict(models), "source": "live", "ageSeconds": 0.0}

def reasoning_budget_for(model, snapshot):
    entry = snapshot.get("models", {}).get(model) if isinstance(snapshot, dict) else None
    budget = MAX_REASONING_BUDGETS.get(model)
    if (
        snapshot.get("source") != "live"
        or not isinstance(entry, dict)
        or entry.get("supportsReasoningMaxTokens") is not True
        or (model == EXACT_NEMOTRON_MODEL and entry.get("exactProviderVerified") is not True)
        or not isinstance(budget, int)
    ):
        raise InvalidReasoningEffortError(
            "Max effort is unsupported for the selected model/provider"
        )
    return budget

def tool_model_preference(entry):
    model_id = entry["id"].casefold()
    verified_code_order = {
        "cohere/north-mini-code:free": 0,
        "poolside/laguna-xs-2.1:free": 1,
        "poolside/laguna-m.1:free": 2,
    }
    is_nvidia_nemotron = model_id.startswith("nvidia/") and "nemotron" in model_id
    if "ultra" in model_id:
        tier = 0
    elif "super" in model_id:
        tier = 1
    elif "nano" in model_id:
        tier = 2
    else:
        tier = 3
    return (
        verified_code_order.get(model_id, 3 if is_nvidia_nemotron else 4),
        tier,
        0 if model_id.endswith(":free") else 1,
        0 if "tool_choice" in entry["supported"] else 1,
        model_id,
    )

def tool_model_candidates(snapshot):
    eligible = [
        entry for entry in snapshot["models"].values()
        if entry["zeroPrice"] and "tools" in entry["supported"]
    ]
    eligible.sort(key=tool_model_preference)
    return [entry["id"] for entry in eligible]

def vision_model_preference(entry):
    model_id = entry["id"].casefold()
    preferred = {value.casefold(): index for index, value in enumerate(PREFERRED_VISION_MODELS)}
    return (
        preferred.get(model_id, len(preferred)),
        0 if "tools" in entry["supported"] else 1,
        0 if model_id.endswith(":free") else 1,
        model_id,
    )

def vision_model_candidates(snapshot, *, require_tools=False):
    eligible = [
        entry for entry in snapshot["models"].values()
        if entry["zeroPrice"]
        and "image" in entry["inputModalities"]
        and (not entry["outputModalities"] or "text" in entry["outputModalities"])
        and (not require_tools or "tools" in entry["supported"])
    ]
    eligible.sort(key=vision_model_preference)
    return [entry["id"] for entry in eligible]

def models_payload(snapshot=None, *, allow_local_network=False):
    snapshot = snapshot or catalog_snapshot(allow_network=False)
    current = snapshot["models"]
    dynamic_ids = []
    for model_id in CONFIGURED_MODELS:
        if model_id in LIVE_GATED_MODELS and snapshot["source"] != "live":
            continue
        if snapshot["source"] != "live" or model_id in current:
            dynamic_ids.append(model_id)
    for model_id in tool_model_candidates(snapshot):
        if model_id in LIVE_GATED_MODELS and snapshot["source"] != "live":
            continue
        if model_id not in dynamic_ids:
            dynamic_ids.append(model_id)
    for model_id in vision_model_candidates(snapshot):
        if model_id in LIVE_GATED_MODELS and snapshot["source"] != "live":
            continue
        if model_id not in dynamic_ids:
            dynamic_ids.append(model_id)
    local_dolphin = dolphin_x1_health(allow_network=allow_local_network)
    if local_dolphin["available"] and DOLPHIN_X1_MODEL not in dynamic_ids:
        dynamic_ids.append(DOLPHIN_X1_MODEL)
    return {
        "object": "list",
        "capability_contract": {
            "schema_version": 1,
            "sha256": MODEL_CAPABILITY_CONTRACT_SHA256,
            "applies_to_every_model": True,
            "tool_route_preserves_instructions": True,
            "english_progress_required": True,
            "ordered_progress_required": True,
            "progress_metadata_only": True,
            "external_content_is_untrusted_data": True,
            "authority_bound_to_active_request_and_turn": True,
        },
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": current.get(model_id, {}).get("created", 0),
                "owned_by": model_id.split("/", 1)[0],
                "capability_contract_sha256": MODEL_CAPABILITY_CONTRACT_SHA256,
            }
            for model_id in dynamic_ids
        ],
        "catalog_source": snapshot["source"],
        "exact_nemotron_status": snapshot.get("exactNemotronCapability", {
            "available": EXACT_NEMOTRON_MODEL in dynamic_ids,
            "provider": None,
            "providerVerified": False,
            "supportsMax": False,
            "credentialUsable": False,
            "reason": "capability_unverified",
        }),
        "requested_model_status": {
            "id": REQUESTED_DOLPHIN_MODEL,
            "available": REQUESTED_DOLPHIN_MODEL in current,
            "substituted": False,
            "closest_selectable_dolphin": AVAILABLE_DOLPHIN_MODEL if AVAILABLE_DOLPHIN_MODEL in dynamic_ids else None,
            "exact_successor": DOLPHIN_X1_MODEL,
            "exact_successor_available": local_dolphin["available"],
            "exact_successor_provider": "paired-pc-llama.cpp" if local_dolphin["available"] else None,
        },
    }

def audit(**values):
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "provider": "OpenRouter", **values}
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOCK, AUDIT_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except OSError:
        return False

def credential_source_fingerprint(descriptor):
    return hashlib.sha256(descriptor.encode("utf-8")).hexdigest()[:24]

def bounded_credential(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 4096 or any(ord(character) < 33 for character in value):
        return None
    return value

def private_file_descriptor(label, path, metadata):
    return "%s:%s:%s:%s:%s:%s:%s:%s:%o" % (
        label,
        path,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_size,
        metadata.st_uid,
        stat.S_IMODE(metadata.st_mode),
    )

def read_private_text(path, label):
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return {
            "exists": False,
            "valid": True,
            "text": None,
            "fingerprint": credential_source_fingerprint(f"{label}:missing:{path}"),
        }
    except OSError as error:
        try:
            metadata = path.lstat()
            source = private_file_descriptor(label, path, metadata)
        except OSError:
            source = f"{label}:unopenable:{path}:{error.errno}"
        return {
            "exists": True,
            "valid": False,
            "text": None,
            "fingerprint": credential_source_fingerprint(source),
        }

    try:
        before = os.fstat(descriptor)
        source = private_file_descriptor(label, path, before)
        fingerprint = credential_source_fingerprint(source)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > 65536
        ):
            return {"exists": True, "valid": False, "text": None, "fingerprint": fingerprint}
        chunks = []
        size = 0
        while size <= 65536:
            chunk = os.read(descriptor, min(8192, 65537 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        after_source = private_file_descriptor(label, path, after)
        fingerprint = credential_source_fingerprint(after_source)
        stable = (
            before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_uid == after.st_uid
            and before.st_mode == after.st_mode
            and before.st_mtime_ns == after.st_mtime_ns
            and before.st_ctime_ns == after.st_ctime_ns
            and before.st_size == after.st_size
            and size == after.st_size
            and size <= 65536
        )
        if not stable:
            return {"exists": True, "valid": False, "text": None, "fingerprint": fingerprint}
        try:
            text = b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError:
            return {"exists": True, "valid": False, "text": None, "fingerprint": fingerprint}
        return {"exists": True, "valid": True, "text": text, "fingerprint": fingerprint}
    except OSError:
        return {
            "exists": True,
            "valid": False,
            "text": None,
            "fingerprint": credential_source_fingerprint(f"{label}:read-error:{path}"),
        }
    finally:
        os.close(descriptor)

def private_env_credential():
    path = CODEX_HOME / "openrouter.env"
    source = read_private_text(path, "private-env-file")
    fingerprint = source["fingerprint"]
    if not source["exists"] or not source["valid"]:
        return {**source, "key": None}
    values = [
        line.partition("=")[2]
        for line in source["text"].splitlines()
        if line.startswith("OPENROUTER_API_KEY=")
    ]
    if len(values) > 1:
        return {"exists": True, "valid": False, "key": None, "fingerprint": fingerprint}
    key = bounded_credential(values[0]) if values else None
    return {
        "exists": True,
        "valid": not values or key is not None,
        "key": key,
        "fingerprint": fingerprint,
    }

def private_broker_config():
    path = CODEX_HOME / "vault" / "broker.json"
    source = read_private_text(path, "vault-broker")
    if not source["exists"] or not source["valid"]:
        return {**source, "host": None, "port": None, "token": None}
    try:
        cfg = json.loads(source["text"])
    except json.JSONDecodeError:
        cfg = None
    host = cfg.get("host") if isinstance(cfg, dict) else None
    port = cfg.get("port") if isinstance(cfg, dict) else None
    token = bounded_credential(cfg.get("token")) if isinstance(cfg, dict) else None
    valid = (
        host in {"127.0.0.1", "::1", "localhost"}
        and not isinstance(port, bool)
        and isinstance(port, int)
        and 1 <= port <= 65535
        and token is not None
    )
    return {
        "exists": True,
        "valid": valid,
        "host": host if valid else None,
        "port": port if valid else None,
        "token": token if valid else None,
        "fingerprint": source["fingerprint"],
    }

def credential_state(*, resolve_broker=True):
    private = private_env_credential()
    if private["key"]:
        return {"key": private["key"], "configured": True, "fingerprint": private["fingerprint"]}
    if private["exists"] and not private["valid"]:
        return {"key": None, "configured": False, "fingerprint": private["fingerprint"]}
    if not private["exists"]:
        env_key = bounded_credential(os.environ.get("OPENROUTER_API_KEY", ""))
        if env_key:
            return {
                "key": env_key,
                "configured": True,
                "fingerprint": credential_source_fingerprint("process-environment:OPENROUTER_API_KEY"),
            }
    broker = private_broker_config()
    if not broker["exists"]:
        return {"key": None, "configured": False, "fingerprint": private["fingerprint"]}
    if not broker["valid"]:
        return {"key": None, "configured": False, "fingerprint": broker["fingerprint"]}
    if not resolve_broker:
        return {"key": None, "configured": True, "fingerprint": broker["fingerprint"]}
    try:
        request = {"token": broker["token"], "action": "get", "key": "openrouter-api-key"}
        with socket.create_connection((broker["host"], broker["port"]), timeout=4) as client:
            client.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode())
            with client.makefile("rb") as reader:
                response_bytes = reader.readline(65537)
        if len(response_bytes) > 65536 or not response_bytes.endswith(b"\n"):
            raise ValueError("invalid broker response")
        response = json.loads(response_bytes.decode("utf-8"))
        if not isinstance(response, dict):
            raise ValueError("invalid broker response")
        value = bounded_credential(response.get("value") if response.get("ok") is True else None)
        if value:
            return {"key": value, "configured": True, "fingerprint": broker["fingerprint"]}
    except Exception:
        pass
    return {"key": None, "configured": False, "fingerprint": broker["fingerprint"]}


def read_capability_json(response):
    if response.getcode() != 200:
        raise CatalogUnavailableError("capability status")
    content_type = str(response.headers.get("Content-Type", ""))
    if "json" not in content_type.casefold():
        raise CatalogUnavailableError("capability content type")
    body = response.read(MAX_CAPABILITY_RESPONSE + 1)
    if len(body) > MAX_CAPABILITY_RESPONSE:
        raise CatalogUnavailableError("capability response limit")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogUnavailableError("capability JSON") from error
    if not isinstance(value, dict):
        raise CatalogUnavailableError("capability schema")
    return value


def fetch_openrouter_key_capability(api_key):
    """Verify that the configured key can currently spend without retaining it."""
    key = bounded_credential(api_key)
    if key is None:
        return {"usable": False, "reason": "credential_unavailable"}
    request = urllib.request.Request(
        OPENROUTER_USAGE_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "Nemotron-Unrestricted-Capability/1.0",
        },
        method="GET",
    )
    response = None
    try:
        response = urllib.request.urlopen(request, timeout=CAPABILITY_FETCH_TIMEOUT_SECONDS)
        payload = read_capability_json(response)
    finally:
        if response is not None:
            response.close()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CatalogUnavailableError("credential capability schema")
    if data.get("disabled") is True:
        return {"usable": False, "reason": "credential_disabled"}
    limit = data.get("limit")
    remaining = data.get("limit_remaining")
    numeric_limit = isinstance(limit, (int, float)) and not isinstance(limit, bool) and math.isfinite(limit)
    numeric_remaining = (
        isinstance(remaining, (int, float))
        and not isinstance(remaining, bool)
        and math.isfinite(remaining)
    )
    if numeric_limit and limit <= 0:
        return {"usable": False, "reason": "credential_limit_exhausted"}
    if numeric_limit and numeric_remaining and remaining <= 0:
        return {"usable": False, "reason": "credential_limit_exhausted"}
    return {"usable": True, "reason": None}


def fetch_exact_nemotron_provider_capability():
    """Verify the pinned Together endpoint and required exact-route parameters."""
    request = urllib.request.Request(
        EXACT_NEMOTRON_ENDPOINTS_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "Nemotron-Unrestricted-Capability/1.0",
        },
        method="GET",
    )
    response = None
    try:
        response = urllib.request.urlopen(request, timeout=CAPABILITY_FETCH_TIMEOUT_SECONDS)
        payload = read_capability_json(response)
    finally:
        if response is not None:
            response.close()
    data = payload.get("data")
    rows = data.get("endpoints") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("id") != EXACT_NEMOTRON_MODEL or not isinstance(rows, list):
        raise CatalogUnavailableError("exact provider capability schema")
    required = {"reasoning", "max_tokens", "tools", "tool_choice"}
    provider_seen = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (
            row.get("provider_name") != EXACT_NEMOTRON_UPSTREAM_PROVIDER
            or row.get("model_id") != EXACT_NEMOTRON_MODEL
        ):
            continue
        provider_seen = True
        supported = row.get("supported_parameters")
        supported = {
            item for item in supported if isinstance(item, str)
        } if isinstance(supported, list) else set()
        if row.get("status") == 0 and required.issubset(supported):
            return {
                "verified": True,
                "supportsMax": True,
                "provider": EXACT_NEMOTRON_UPSTREAM_PROVIDER,
                "reason": None,
            }
    return {
        "verified": False,
        "supportsMax": False,
        "provider": EXACT_NEMOTRON_UPSTREAM_PROVIDER if provider_seen else None,
        "reason": "provider_capabilities_missing" if provider_seen else "provider_unavailable",
    }


def exact_nemotron_capability():
    """Return fresh credential plus pinned-provider proof, cached by key source."""
    global EXACT_CAPABILITY_REFRESHING
    credential = credential_state()
    fingerprint = credential.get("fingerprint")
    result = {
        "usable": False,
        "providerVerified": False,
        "supportsMax": False,
        "reason": "capability_verification_unavailable",
    }
    now = time.monotonic()
    with EXACT_CAPABILITY_CONDITION:
        while True:
            cached_result = EXACT_CAPABILITY_CACHE.get("result")
            checked_at = EXACT_CAPABILITY_CACHE.get("checkedAt", 0.0)
            if (
                isinstance(cached_result, dict)
                and EXACT_CAPABILITY_CACHE.get("fingerprint") == fingerprint
                and checked_at
                and now - checked_at <= CAPABILITY_TTL_SECONDS
            ):
                return dict(cached_result)
            if not EXACT_CAPABILITY_REFRESHING:
                EXACT_CAPABILITY_REFRESHING = True
                break
            EXACT_CAPABILITY_CONDITION.wait(CAPABILITY_FETCH_TIMEOUT_SECONDS)
            now = time.monotonic()
    try:
        if not credential.get("configured") or not credential.get("key"):
            result = {
                "usable": False,
                "providerVerified": False,
                "supportsMax": False,
                "reason": "credential_unavailable",
            }
        else:
            try:
                key_capability = fetch_openrouter_key_capability(credential["key"])
            except (CatalogUnavailableError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
                key_capability = {"usable": False, "reason": "credential_verification_unavailable"}
            if not key_capability["usable"]:
                result = {
                    "usable": False,
                    "providerVerified": False,
                    "supportsMax": False,
                    "reason": key_capability["reason"],
                }
            else:
                try:
                    provider = fetch_exact_nemotron_provider_capability()
                except (CatalogUnavailableError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
                    provider = {
                        "verified": False,
                        "supportsMax": False,
                        "reason": "provider_verification_unavailable",
                    }
                result = {
                    "usable": provider.get("verified") is True,
                    "providerVerified": provider.get("verified") is True,
                    "supportsMax": provider.get("supportsMax") is True,
                    "reason": provider.get("reason"),
                }
    finally:
        with EXACT_CAPABILITY_CONDITION:
            EXACT_CAPABILITY_CACHE.update({
                "fingerprint": fingerprint,
                "checkedAt": time.monotonic(),
                "result": dict(result),
            })
            EXACT_CAPABILITY_REFRESHING = False
            EXACT_CAPABILITY_CONDITION.notify_all()
    return dict(result)


def mark_exact_nemotron_unusable(reason):
    """Fail closed immediately after an authoritative credential rejection."""
    fingerprint = credential_state(resolve_broker=False).get("fingerprint")
    result = {
        "usable": False,
        "providerVerified": False,
        "supportsMax": False,
        "reason": reason,
    }
    with EXACT_CAPABILITY_CONDITION:
        EXACT_CAPABILITY_CACHE.update({
            "fingerprint": fingerprint,
            "checkedAt": time.monotonic(),
            "result": result,
        })
        EXACT_CAPABILITY_CONDITION.notify_all()
    return dict(result)


def gate_exact_nemotron_snapshot(snapshot, capability):
    """Remove the exact route unless catalog, credential, and Together all agree."""
    models = dict(snapshot.get("models", {})) if isinstance(snapshot, dict) else {}
    models.pop(EXACT_NEMOTRON_FREE_MODEL, None)
    allowed = (
        snapshot.get("source") == "live"
        and capability.get("usable") is True
        and capability.get("providerVerified") is True
    )
    entry = models.get(EXACT_NEMOTRON_MODEL)
    if not allowed or not isinstance(entry, dict):
        models.pop(EXACT_NEMOTRON_MODEL, None)
    else:
        verified = dict(entry)
        verified["exactProviderVerified"] = True
        verified["supportsReasoningMaxTokens"] = (
            verified.get("supportsReasoningMaxTokens") is True
            and capability.get("supportsMax") is True
        )
        models[EXACT_NEMOTRON_MODEL] = verified
    return {
        **snapshot,
        "models": models,
        "exactNemotronCapability": {
            "available": EXACT_NEMOTRON_MODEL in models,
            "provider": (
                EXACT_NEMOTRON_UPSTREAM_PROVIDER
                if capability.get("providerVerified") is True else None
            ),
            "providerVerified": capability.get("providerVerified") is True,
            "supportsMax": capability.get("supportsMax") is True,
            "credentialUsable": capability.get("usable") is True,
            "reason": capability.get("reason"),
        },
    }


def current_exact_nemotron_snapshot():
    return gate_exact_nemotron_snapshot(
        current_tool_catalog_snapshot(),
        exact_nemotron_capability(),
    )


def exact_nemotron_unavailable_message(snapshot):
    capability = snapshot.get("exactNemotronCapability", {}) if isinstance(snapshot, dict) else {}
    reason = capability.get("reason") if isinstance(capability, dict) else None
    messages = {
        "credential_unavailable": "Exact Nemotron requires a configured OpenRouter credential",
        "credential_disabled": "The configured OpenRouter credential is disabled",
        "credential_limit_exhausted": "The configured OpenRouter credential has no remaining usage limit",
        "credential_credit_unavailable": "The configured OpenRouter account has no available inference credit",
        "credential_verification_unavailable": "OpenRouter credential usability could not be verified",
        "provider_unavailable": "The exact Together route for Nemotron is currently unavailable",
        "provider_capabilities_missing": "The exact Together route no longer advertises every required reasoning and tool capability",
        "provider_verification_unavailable": "The exact Together route could not be verified",
        "capability_verification_unavailable": "Exact Nemotron capability verification is unavailable",
    }
    return messages.get(reason, "Selected model is unavailable from the current verified provider capability")

def get_api_key():
    return credential_state()["key"]

def payload_text(payload):
    output = []
    for message in payload.get("messages", []) if isinstance(payload, dict) else []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            output.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    output.append(item["text"])
    return "\n".join(output)

def compaction_phase(payload):
    text = payload_text(payload)
    if COMPACTION_MARKER in text:
        return "summary"
    if POST_COMPACTION_PREFIX in text:
        return "continuation"
    return "none"

def capability_verification_requested(payload):
    user_text = []
    for message in payload.get("messages", []) if isinstance(payload, dict) else []:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            user_text.append(content)
        elif isinstance(content, list):
            user_text.extend(
                item["text"] for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
    text = "\n".join(user_text[-2:]).casefold()
    return "command -v" in text or (
        any(word in text for word in ("capability", "capabilities", "toolchain", "inventory"))
        and any(word in text for word in ("verify", "verified", "available", "installed", "can you"))
    )

def autonomous_action_requested(payload):
    """Require one structured action before prose for explicit, tool-addressable work."""
    user_text = []
    for message in payload.get("messages", []) if isinstance(payload, dict) else []:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            user_text.append(content)
        elif isinstance(content, list):
            user_text.extend(
                item["text"] for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
    text = "\n".join(user_text[-2:]).casefold()
    if not text or compaction_phase(payload) != "none":
        return False
    action_words = (
        "search", "find", "look up", "research", "download", "install", "uninstall",
        "open", "launch", "create", "write", "edit", "update", "build", "compile",
        "test", "verify", "inspect", "scan", "list", "count", "move", "copy", "rename",
        "delete", "trash", "restore", "recover", "upload", "send", "post", "save",
        "connect", "automate", "run", "execute", "tap", "swipe", "type",
    )
    actionable_objects = (
        "app", "apk", "package", "file", "folder", "project", "repository", "repo",
        "website", "online", "web", "browser", "chrome", "android", "phone", "device",
        "gallery", "image", "photo", "video", "facebook", "spotify", "github", "pc",
        "command", "script", "code", "test", "build", "network", "url", "link",
    )
    return any(word in text for word in action_words) and any(word in text for word in actionable_objects)

def payload_has_tool_results(payload):
    if not isinstance(payload, dict):
        return False
    for key in ("messages", "input"):
        entries = payload.get(key, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("role") == "tool":
                return True
            if entry.get("type") in ("function_call_output", "tool_result", "computer_call_output"):
                return True
            content = entry.get("content")
            if isinstance(content, list) and any(
                isinstance(item, dict)
                and item.get("type") in ("function_call_output", "tool_result", "computer_call_output")
                for item in content
            ):
                return True
    return False

def payload_has_image(payload):
    """Recognize OpenAI chat/responses image parts without inspecting image bytes."""
    if not isinstance(payload, dict):
        return False
    pending = [(payload.get("messages"), 0), (payload.get("input"), 0)]
    visited = 0
    while pending and visited < 4096:
        value, depth = pending.pop()
        visited += 1
        if depth > 16:
            continue
        if isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
            continue
        if not isinstance(value, dict):
            continue
        part_type = value.get("type")
        if isinstance(part_type, str) and part_type.casefold() in {
            "image", "image_url", "input_image", "input_image_url",
        }:
            return True
        if "image_url" in value and isinstance(value.get("image_url"), (dict, str)):
            return True
        pending.extend((item, depth + 1) for item in value.values())
    return False

def normalize_payload(payload, catalog=None, *, locked_selection=False):
    if not isinstance(payload, dict):
        return payload, {"model": None, "requestedModel": None, "requestedEffort": None, "effectiveEffort": None, "toolCount": 0, "imageInput": False, "payloadRepairs": 0, "compactionPhase": "none"}
    result = dict(payload)
    if locked_selection:
        # Routing controls belong to the immutable selection snapshot, never to
        # replayed provider-specific fields from a previous continuation.
        result.pop("provider", None)
    repairs = 0
    requested_model = result.get("model")
    tool_count = len(result.get("tools", [])) if isinstance(result.get("tools"), list) else 0
    image_input = payload_has_image(result)
    snapshot = catalog or catalog_snapshot(allow_network=False)
    model_candidates = []
    if locked_selection and requested_model:
        entry = snapshot["models"].get(requested_model)
        local_model = requested_model == DOLPHIN_X1_MODEL
        if entry is None and not local_model:
            if requested_model in LIVE_GATED_MODELS:
                raise ModelUnavailableError(exact_nemotron_unavailable_message(snapshot))
            raise ModelUnavailableError("Selected model is unavailable from the current provider catalog")
        if image_input and (entry is None or "image" not in entry["inputModalities"]):
            raise ModelUnavailableError("Selected model does not support image input")
        if tool_count and (entry is None or "tools" not in entry["supported"]):
            raise ModelUnavailableError("Selected model does not support tools")
        effective_model = requested_model
        result["model"] = effective_model
        result.pop("models", None)
    elif image_input:
        model_candidates = vision_model_candidates(snapshot, require_tools=bool(tool_count))
        if not model_candidates:
            raise CatalogUnavailableError("No current zero-price image-capable model is available")
    elif tool_count:
        model_candidates = tool_model_candidates(snapshot)
        if not model_candidates:
            raise CatalogUnavailableError("No current zero-price tool-capable model is available")

    if locked_selection and requested_model:
        if (
            tool_count
            and (capability_verification_requested(payload) or autonomous_action_requested(payload))
            and not payload_has_tool_results(payload)
            and result.get("tool_choice") != "required"
        ):
            result["tool_choice"] = "required"
            repairs += 1
        elif payload_has_tool_results(payload) and result.get("tool_choice") == "required":
            result["tool_choice"] = "auto"
            repairs += 1
    elif image_input or tool_count:
        if requested_model in model_candidates:
            model_candidates = [requested_model, *[model for model in model_candidates if model != requested_model]]
        effective_model = model_candidates[0]
        if requested_model != effective_model:
            repairs += 1
        result["model"] = effective_model
        fallbacks = model_candidates[1:8]
        if fallbacks:
            result["models"] = fallbacks
        else:
            result.pop("models", None)
        if (
            tool_count
            and
            (capability_verification_requested(payload) or autonomous_action_requested(payload))
            and not payload_has_tool_results(payload)
            and result.get("tool_choice") != "required"
        ):
            result["tool_choice"] = "required"
            repairs += 1
        elif payload_has_tool_results(payload) and result.get("tool_choice") == "required":
            result["tool_choice"] = "auto"
            repairs += 1
    else:
        local_dolphin_selected = requested_model == DOLPHIN_X1_MODEL
        if local_dolphin_selected and not dolphin_x1_health(allow_network=True)["available"]:
            raise ModelUnavailableError(
                "Selected exact Dolphin X1 405B endpoint is not currently healthy"
            )
        if requested_model and requested_model not in snapshot["models"] and not local_dolphin_selected:
            if requested_model in LIVE_GATED_MODELS:
                raise ModelUnavailableError(exact_nemotron_unavailable_message(snapshot))
            raise ModelUnavailableError(f"Selected model is unavailable from the current provider catalog: {requested_model}")
        effective_model = result.get("model", DEFAULT_MODEL)
    if effective_model == EXACT_NEMOTRON_MODEL:
        result["provider"] = {
            "order": [EXACT_NEMOTRON_UPSTREAM_PROVIDER],
            "allow_fallbacks": False,
            "require_parameters": True,
        }
    top_level_effort = result.get("reasoning_effort")
    reasoning = dict(result["reasoning"]) if isinstance(result.get("reasoning"), dict) else None
    nested_effort = reasoning.get("effort") if reasoning is not None else None
    if top_level_effort is not None and nested_effort is not None:
        if normalize_reasoning_effort(top_level_effort) != normalize_reasoning_effort(nested_effort):
            raise InvalidReasoningEffortError("Conflicting reasoning effort values")
    requested_effort = top_level_effort if top_level_effort is not None else nested_effort
    effective_effort = normalize_reasoning_effort(requested_effort)
    reasoning_budget = None
    if effective_effort == "max":
        result.pop("reasoning_effort", None)
        reasoning = reasoning or {}
        reasoning.pop("effort", None)
        reasoning_budget = reasoning_budget_for(effective_model, snapshot)
        reasoning["max_tokens"] = reasoning_budget
        result["reasoning"] = reasoning
    else:
        if locked_selection and reasoning is not None:
            reasoning.pop("max_tokens", None)
        if top_level_effort is not None:
            result["reasoning_effort"] = effective_effort
        if reasoning is not None and nested_effort is not None:
            reasoning["effort"] = effective_effort
            result["reasoning"] = reasoning
    if requested_effort is not None and requested_effort != effective_effort:
        repairs += 1
    metadata = {
        "model": effective_model,
        "requestedModel": requested_model,
        "requestedEffort": requested_effort,
        "transportEffort": effective_effort or "provider-default",
        "effectiveEffort": None,
        "reasoningBudget": reasoning_budget,
        "toolCount": tool_count,
        "imageInput": image_input,
        "payloadRepairs": repairs,
        "compactionPhase": compaction_phase(payload),
        "toolFallbackUsed": False,
        "modelCandidates": model_candidates[:8],
        "catalogSource": snapshot["source"],
        "effectiveModel": effective_model,
        "selectionApplied": locked_selection,
        "exactRoute": effective_model == EXACT_NEMOTRON_MODEL,
    }
    return result, metadata

def select_tool_candidate(payload, metadata, index):
    candidates = metadata.get("modelCandidates", [])
    if not isinstance(index, int) or not 0 <= index < len(candidates):
        return False
    selected = candidates[index]
    remaining = candidates[index + 1:]
    payload["model"] = selected
    if remaining:
        payload["models"] = remaining
    else:
        payload.pop("models", None)
    metadata["model"] = selected
    metadata["effectiveModel"] = selected
    metadata["toolFallbackUsed"] = index > 0
    return True

def response_error_message(response_body):
    try:
        value = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(value, dict):
        return ""
    error = value.get("error")
    if isinstance(error, dict):
        return str(error.get("message", "")).casefold()
    return ""

def model_route_unavailable(status, response_body):
    if status not in {400, 403, 404, 410, 422}:
        return False
    message = response_error_message(response_body)
    markers = (
        "model", "provider", "endpoint", "not found", "no endpoints", "unavailable",
        "not supported", "does not support", "tool use", "tools",
    )
    return status in {404, 410} or any(marker in message for marker in markers)

def repair_tool_choice_validation(payload, error_body):
    try:
        error = json.loads(error_body.decode("utf-8", errors="replace"))
    except (UnicodeDecodeError, ValueError):
        return False
    message = str(error.get("error", {}).get("message", "")).lower()
    if "tool_choice" not in message and "tools must be set" not in message:
        return False
    if isinstance(payload, dict):
        payload["tool_choice"] = "auto"
        return True
    return False

def retry_delay(response, attempt):
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), 60.0))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(0.0, min((retry_at - datetime.now(timezone.utc)).total_seconds(), 60.0))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(8.0, (0.5 * (2 ** attempt)) + random.uniform(0.05, 0.35))

def recovery_delay(attempt):
    return min(8.0, (0.5 * (2 ** attempt)) + random.uniform(0.05, 0.35))

def tool_schema(payload, name):
    for tool in payload.get("tools", []) if isinstance(payload, dict) else []:
        function = tool.get("function", {}) if isinstance(tool, dict) else {}
        if function.get("name") == name and isinstance(function.get("parameters"), dict):
            return function["parameters"]
    return {}

def advertised_tool_names(payload):
    names = set()
    for tool in payload.get("tools", []) if isinstance(payload, dict) else []:
        function = tool.get("function", {}) if isinstance(tool, dict) else {}
        name = function.get("name") if isinstance(function, dict) else None
        if isinstance(name, str) and name:
            names.add(name)
    return names

class ToolArgumentValidationError(ValueError):
    """Sanitized failure raised when model-produced tool arguments are unsafe to dispatch."""

def schema_type_names(schema):
    raw_types = schema.get("type") if isinstance(schema, dict) else None
    if raw_types is None:
        return None
    if isinstance(raw_types, str):
        types = (raw_types,)
    elif isinstance(raw_types, list) and raw_types and all(isinstance(item, str) for item in raw_types):
        types = tuple(raw_types)
    else:
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    allowed = {"null", "boolean", "integer", "number", "string", "array", "object"}
    if any(item not in allowed for item in types):
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    return frozenset(types)

def is_json_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not (
        isinstance(value, float) and not math.isfinite(value)
    )

def value_matches_schema_type(value, expected):
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return is_json_number(value)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False

def json_values_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    if is_json_number(left) and is_json_number(right):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(json_values_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_values_equal(left[key], right[key]) for key in left)
    return left == right

def resolve_local_schema_ref(root_schema, reference):
    if not isinstance(reference, str) or not reference.startswith("#"):
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    fragment = urllib.parse.unquote(reference[1:])
    if fragment == "":
        return root_schema
    if not fragment.startswith("/"):
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    current = root_schema
    for raw_token in fragment[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    if not isinstance(current, (dict, bool)):
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    return current

def schema_branch_matches(value, schema, root_schema=None, ref_stack=(), depth=0):
    try:
        validate_schema_value(value, schema, root_schema, ref_stack, depth)
        return True
    except ToolArgumentValidationError:
        return False

def validate_schema_value(value, schema, root_schema=None, ref_stack=(), depth=0):
    """Validate the JSON-schema subset advertised by Codex tool definitions."""
    if depth > SCHEMA_MAX_DEPTH:
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    if root_schema is None:
        root_schema = schema
    if schema is True:
        return
    if schema is False or not isinstance(schema, dict):
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    if "$ref" in schema:
        reference = schema["$ref"]
        marker = (reference, id(value))
        if marker in ref_stack:
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        target = resolve_local_schema_ref(root_schema, reference)
        validate_schema_value(value, target, root_schema, (*ref_stack, marker), depth + 1)
        siblings = {key: item for key, item in schema.items() if key != "$ref"}
        if siblings:
            validate_schema_value(value, siblings, root_schema, ref_stack, depth + 1)
        return

    if "const" in schema and not json_values_equal(value, schema["const"]):
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, list) or not any(json_values_equal(value, option) for option in enum):
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")

    types = schema_type_names(schema)
    if types is not None and not any(value_matches_schema_type(value, expected) for expected in types):
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")

    all_of = schema.get("allOf")
    if all_of is not None:
        if not isinstance(all_of, list) or not all_of:
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        for branch in all_of:
            validate_schema_value(value, branch, root_schema, ref_stack, depth + 1)
    any_of = schema.get("anyOf")
    if any_of is not None:
        if not isinstance(any_of, list) or not any_of or not any(
            schema_branch_matches(value, branch, root_schema, ref_stack, depth + 1) for branch in any_of
        ):
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    one_of = schema.get("oneOf")
    if one_of is not None:
        if not isinstance(one_of, list) or not one_of:
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        if sum(schema_branch_matches(value, branch, root_schema, ref_stack, depth + 1) for branch in one_of) != 1:
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if properties is not None and not isinstance(properties, dict):
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        properties = properties or {}
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        if any(key not in value for key in required):
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        for key, item in value.items():
            if key in properties:
                validate_schema_value(item, properties[key], root_schema, ref_stack, depth + 1)
                continue
            additional = schema.get("additionalProperties", True)
            if additional is False:
                raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
            if isinstance(additional, (dict, bool)):
                validate_schema_value(item, additional, root_schema, ref_stack, depth + 1)
            elif additional is not True:
                raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        for keyword, predicate in (
            ("minProperties", lambda count, limit: count >= limit),
            ("maxProperties", lambda count, limit: count <= limit),
        ):
            if keyword in schema:
                limit = schema[keyword]
                if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or not predicate(len(value), limit):
                    raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")

    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, (dict, bool)):
            for item in value:
                validate_schema_value(item, items, root_schema, ref_stack, depth + 1)
        elif isinstance(items, list):
            for index, item in enumerate(value):
                if index < len(items):
                    validate_schema_value(item, items[index], root_schema, ref_stack, depth + 1)
                else:
                    additional_items = schema.get("additionalItems", True)
                    if additional_items is False:
                        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
                    if isinstance(additional_items, (dict, bool)):
                        validate_schema_value(item, additional_items, root_schema, ref_stack, depth + 1)
        elif items is not None:
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        for keyword, predicate in (
            ("minItems", lambda count, limit: count >= limit),
            ("maxItems", lambda count, limit: count <= limit),
        ):
            if keyword in schema:
                limit = schema[keyword]
                if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or not predicate(len(value), limit):
                    raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        if schema.get("uniqueItems") is True:
            for index, item in enumerate(value):
                if any(json_values_equal(item, previous) for previous in value[:index]):
                    raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")

    if isinstance(value, str):
        for keyword, predicate in (
            ("minLength", lambda count, limit: count >= limit),
            ("maxLength", lambda count, limit: count <= limit),
        ):
            if keyword in schema:
                limit = schema[keyword]
                if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or not predicate(len(value), limit):
                    raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        if "pattern" in schema:
            pattern = schema["pattern"]
            if not isinstance(pattern, str):
                raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
            try:
                matched = re.search(pattern, value) is not None
            except re.error as error:
                raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema") from error
            if not matched:
                raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")

    if is_json_number(value):
        for keyword, predicate in (
            ("minimum", lambda number, limit: number >= limit),
            ("maximum", lambda number, limit: number <= limit),
        ):
            if keyword in schema:
                limit = schema[keyword]
                if not is_json_number(limit) or not predicate(value, limit):
                    raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        for keyword, predicate in (
            ("exclusiveMinimum", lambda number, limit: number > limit),
            ("exclusiveMaximum", lambda number, limit: number < limit),
        ):
            if keyword in schema:
                limit = schema[keyword]
                if isinstance(limit, bool):
                    bound_name = "minimum" if keyword == "exclusiveMinimum" else "maximum"
                    if limit and (bound_name not in schema or not predicate(value, schema[bound_name])):
                        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
                elif not is_json_number(limit) or not predicate(value, limit):
                    raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")

def coerce_schema_value(value, schema, root_schema=None, ref_stack=(), depth=0):
    if depth > SCHEMA_MAX_DEPTH:
        raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
    if root_schema is None:
        root_schema = schema
    if not isinstance(schema, dict):
        return value
    if "$ref" in schema:
        reference = schema["$ref"]
        marker = (reference, id(value))
        if marker in ref_stack:
            raise ToolArgumentValidationError("Tool arguments do not satisfy the advertised schema")
        target = resolve_local_schema_ref(root_schema, reference)
        value = coerce_schema_value(value, target, root_schema, (*ref_stack, marker), depth + 1)
        siblings = {key: item for key, item in schema.items() if key != "$ref"}
        if siblings:
            value = coerce_schema_value(value, siblings, root_schema, ref_stack, depth + 1)
        return value

    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if not isinstance(branches, list) or not branches:
            continue
        candidates = []
        for branch in branches:
            try:
                candidate = coerce_schema_value(value, branch, root_schema, ref_stack, depth + 1)
                validate_schema_value(candidate, branch, root_schema, ref_stack, depth + 1)
            except ToolArgumentValidationError:
                continue
            if not any(json_values_equal(candidate, existing) for existing in candidates):
                candidates.append(candidate)
        if len(candidates) == 1:
            value = candidates[0]

    types = schema_type_names(schema)
    already_matches = types is not None and any(value_matches_schema_type(value, expected) for expected in types)
    string_allowed = types is not None and "string" in types
    exclusive_integer = types is not None and "integer" in types and types.issubset({"integer", "null"})
    number_allowed = types is not None and "number" in types
    boolean_allowed = types is not None and "boolean" in types
    array_allowed = types is not None and "array" in types
    object_allowed = types is not None and "object" in types

    if boolean_allowed and not already_matches and isinstance(value, str):
        if value.strip().lower() == "true":
            value = True
        elif value.strip().lower() == "false":
            value = False
    elif exclusive_integer:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        elif isinstance(value, str) and not string_allowed:
            try:
                numeric = Decimal(value.strip())
                if numeric.is_finite() and numeric == numeric.to_integral_value() and numeric.adjusted() <= 10000:
                    value = int(numeric)
            except (InvalidOperation, ValueError):
                pass
    elif number_allowed and not already_matches and isinstance(value, str) and not string_allowed:
        try:
            numeric = float(value.strip())
            if math.isfinite(numeric):
                value = numeric
        except ValueError:
            pass
    elif (array_allowed or object_allowed) and not already_matches and isinstance(value, str) and not string_allowed:
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = value
        if array_allowed and isinstance(decoded, list):
            value = decoded
        elif object_allowed and isinstance(decoded, dict):
            value = decoded

    if isinstance(value, dict):
        properties = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        additional = schema.get("additionalProperties", True)
        repaired_object = {}
        for key, item in value.items():
            if key in properties:
                repaired_object[key] = coerce_schema_value(
                    item, properties[key], root_schema, ref_stack, depth + 1
                )
            elif additional is False:
                continue
            elif isinstance(additional, dict):
                repaired_object[key] = coerce_schema_value(
                    item, additional, root_schema, ref_stack, depth + 1
                )
            else:
                repaired_object[key] = item
        value = repaired_object
    elif isinstance(value, list):
        item_schema = schema.get("items", {})
        if isinstance(item_schema, dict):
            value = [
                coerce_schema_value(item, item_schema, root_schema, ref_stack, depth + 1)
                for item in value
            ]
        elif isinstance(item_schema, list):
            value = [
                coerce_schema_value(
                    item, item_schema[index], root_schema, ref_stack, depth + 1
                ) if index < len(item_schema) else item
                for index, item in enumerate(value)
            ]
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for branch in all_of:
            value = coerce_schema_value(value, branch, root_schema, ref_stack, depth + 1)
    return value

def repair_function_arguments(function, payload):
    if not isinstance(function, dict):
        raise ToolArgumentValidationError("Tool function is not valid")
    if not isinstance(function.get("arguments"), str):
        raise ToolArgumentValidationError("Tool arguments are not valid JSON")
    original = function["arguments"]
    def reject_non_json_constant(_constant):
        raise ValueError("non-JSON constant")
    try:
        arguments = json.loads(original, parse_constant=reject_non_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise ToolArgumentValidationError("Tool arguments are not valid JSON") from error
    schema = tool_schema(payload, function.get("name"))
    repaired = coerce_schema_value(arguments, schema, schema)
    validate_schema_value(repaired, schema, schema)
    encoded = json.dumps(repaired, separators=(",", ":"))
    original_encoded = json.dumps(arguments, separators=(",", ":"))
    if encoded != original_encoded:
        function["arguments"] = encoded
        return 1
    return 0

class UpstreamResponseValidationError(ValueError):
    """A sanitized upstream response failure that must never reach tool dispatch."""

def pseudo_tool_function(content, payload):
    """Convert an exact Nemotron pseudo-tool envelope into an advertised function call."""
    if not isinstance(content, str):
        return None
    hermes_match = re.fullmatch(
        r"\s*(?:<tool_call>\s*)?<function=([A-Za-z_][A-Za-z0-9_.-]*)>\s*"
        r"((?:<parameter=[A-Za-z_][A-Za-z0-9_.-]*>.*?</parameter>\s*)+)"
        r"</function>\s*</tool_call>\s*",
        content,
        flags=re.DOTALL,
    )
    if hermes_match is not None:
        name = hermes_match.group(1)
        if name not in advertised_tool_names(payload):
            raise UpstreamResponseValidationError("Pseudo-tool was not advertised")
        parameters = {}
        position = 0
        body = hermes_match.group(2)
        pattern = re.compile(
            r"\s*<parameter=([A-Za-z_][A-Za-z0-9_.-]*)>(.*?)</parameter>",
            flags=re.DOTALL,
        )
        for parameter in pattern.finditer(body):
            if parameter.start() != position or parameter.group(1) in parameters:
                raise UpstreamResponseValidationError("Invalid pseudo-tool parameters")
            parameters[parameter.group(1)] = parameter.group(2).strip()
            position = parameter.end()
        if body[position:].strip() or not parameters:
            raise UpstreamResponseValidationError("Invalid pseudo-tool parameters")
        function = {"name": name, "arguments": json.dumps(parameters, separators=(",", ":"))}
        repair_function_arguments(function, payload)
        return function
    if "<function=" in content or "<parameter=" in content or "</tool_call>" in content:
        raise UpstreamResponseValidationError("Invalid pseudo-tool envelope")
    if "<execute>" not in content:
        return None
    match = re.fullmatch(
        r"\s*<execute>\s*(\{.*\})\s*(?:</execute>|execute>)\s*",
        content,
        flags=re.DOTALL,
    )
    if match is None:
        raise UpstreamResponseValidationError("Invalid pseudo-tool envelope")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise UpstreamResponseValidationError("Invalid pseudo-tool JSON") from error
    if not isinstance(value, dict) or set(value) - {"name", "arguments", "parameters"}:
        raise UpstreamResponseValidationError("Invalid pseudo-tool object")
    name = value.get("name")
    arguments = value.get("arguments", value.get("parameters"))
    if not isinstance(name, str) or name not in advertised_tool_names(payload):
        raise UpstreamResponseValidationError("Pseudo-tool was not advertised")
    if not isinstance(arguments, dict):
        raise UpstreamResponseValidationError("Invalid pseudo-tool arguments")
    function = {"name": name, "arguments": json.dumps(arguments, separators=(",", ":"))}
    repair_function_arguments(function, payload)
    return function

def parse_sse_events(response_body):
    if not isinstance(response_body, (bytes, bytearray)):
        raise UpstreamResponseValidationError("Invalid SSE body")
    try:
        text = bytes(response_body).decode("utf-8")
    except UnicodeDecodeError as error:
        raise UpstreamResponseValidationError("Invalid SSE encoding") from error
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise UpstreamResponseValidationError("Invalid SSE framing")
    blocks = []
    current = []
    for line in text.split("\n"):
        if line == "":
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)

    events = []
    terminal_seen = False
    for block in blocks:
        if terminal_seen:
            raise UpstreamResponseValidationError("SSE data followed its terminal event")
        comments = []
        fields = {"data": []}
        for line in block:
            if line.startswith(":"):
                comments.append(line[1:].lstrip(" "))
                continue
            name, separator, raw_value = line.partition(":")
            if not separator:
                raw_value = ""
            if raw_value.startswith(" "):
                raw_value = raw_value[1:]
            if name not in {"data", "event", "id", "retry"}:
                raise UpstreamResponseValidationError("Unsupported SSE field")
            if name == "data":
                fields["data"].append(raw_value)
            elif name in fields:
                raise UpstreamResponseValidationError("Duplicate SSE field")
            else:
                fields[name] = raw_value
        if comments and len(fields) == 1 and not fields["data"]:
            events.append({"kind": "comment", "comments": comments})
            continue
        if comments:
            raise UpstreamResponseValidationError("Mixed SSE comment and data event")
        if not fields["data"]:
            raise UpstreamResponseValidationError("SSE event has no data")
        if "retry" in fields and not fields["retry"].isdigit():
            raise UpstreamResponseValidationError("Invalid SSE retry field")
        data_text = "\n".join(fields["data"]).strip()
        if data_text == "[DONE]":
            if len(fields) != 1:
                raise UpstreamResponseValidationError("Invalid terminal SSE fields")
            terminal_seen = True
            events.append({"kind": "done"})
            continue
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError as error:
            raise UpstreamResponseValidationError("Invalid SSE JSON") from error
        if not isinstance(data, dict):
            raise UpstreamResponseValidationError("Invalid SSE JSON object")
        if fields.get("event", "").casefold() == "error" or "error" in data:
            raise UpstreamResponseValidationError("Upstream SSE error event")
        events.append({
            "kind": "data",
            "data": data,
            "event": fields.get("event"),
            "id": fields.get("id"),
            "retry": fields.get("retry"),
        })
    if not terminal_seen or not events or events[-1]["kind"] != "done":
        raise UpstreamResponseValidationError("SSE terminal event missing")
    return events

def encode_sse_events(events):
    output = []
    for event in events:
        if event["kind"] == "comment":
            output.extend(": " + comment for comment in event["comments"])
        elif event["kind"] == "done":
            output.append("data: [DONE]")
        else:
            for field in ("event", "id", "retry"):
                if event.get(field) is not None:
                    output.append(f"{field}: {event[field]}")
            output.append("data: " + json.dumps(event["data"], separators=(",", ":")))
        output.append("")
    return ("\n".join(output).rstrip("\n") + "\n\n").encode("utf-8")

def repair_sse_response(response_body, payload):
    events = parse_sse_events(response_body)
    repaired = 0
    fragments = {}
    content_fragments = {}
    for event in events:
        if event["kind"] != "data":
            continue
        data = event["data"]
        choices = data.get("choices", [])
        if not isinstance(choices, list):
            raise UpstreamResponseValidationError("Invalid SSE choices")
        for choice_position, choice in enumerate(choices):
            if not isinstance(choice, dict):
                raise UpstreamResponseValidationError("Invalid SSE choice")
            choice_index = choice.get("index", choice_position)
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise UpstreamResponseValidationError("Invalid SSE delta")
            content = delta.get("content")
            if isinstance(content, str):
                aggregate_content = content_fragments.setdefault(
                    choice_index, {"text": "", "deltas": [], "choices": []}
                )
                aggregate_content["text"] += content
                aggregate_content["deltas"].append(delta)
                aggregate_content["choices"].append(choice)
            tool_calls = delta.get("tool_calls", [])
            if not isinstance(tool_calls, list):
                raise UpstreamResponseValidationError("Invalid SSE tool calls")
            for call_position, call in enumerate(tool_calls):
                if not isinstance(call, dict):
                    raise UpstreamResponseValidationError("Invalid SSE tool call")
                call_index = call.get("index", call_position)
                function = call.get("function", {})
                if not isinstance(function, dict):
                    raise UpstreamResponseValidationError("Invalid SSE tool function")
                key = (choice_index, call_index)
                aggregate = fragments.setdefault(key, {"name": "", "arguments": "", "functions": []})
                if isinstance(function.get("name"), str):
                    aggregate["name"] += function["name"]
                if isinstance(function.get("arguments"), str):
                    aggregate["arguments"] += function["arguments"]
                    aggregate["functions"].append(function)
    for aggregate in fragments.values():
        if not aggregate["functions"]:
            continue
        if not aggregate["name"]:
            raise UpstreamResponseValidationError("Invalid SSE tool function name")
        if aggregate["name"] not in advertised_tool_names(payload):
            raise UpstreamResponseValidationError("Upstream tool was not advertised")
        function = {"name": aggregate["name"], "arguments": aggregate["arguments"]}
        changed = repair_function_arguments(function, payload)
        if changed:
            for fragment in aggregate["functions"]:
                fragment["arguments"] = ""
            aggregate["functions"][-1]["arguments"] = function["arguments"]
            repaired += changed
    for choice_index, aggregate in content_fragments.items():
        function = pseudo_tool_function(aggregate["text"], payload)
        if function is None:
            continue
        first_delta = aggregate["deltas"][0]
        for delta in aggregate["deltas"]:
            delta.pop("content", None)
        first_delta["tool_calls"] = [{
            "index": 0,
            "id": f"call_pseudo_{choice_index}",
            "type": "function",
            "function": function,
        }]
        for choice in aggregate["choices"]:
            if choice.get("finish_reason") == "stop":
                choice["finish_reason"] = "tool_calls"
        repaired += 1
    return encode_sse_events(events), repaired

def repair_json_response(response_body, payload):
    try:
        data = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpstreamResponseValidationError("Invalid upstream JSON") from error
    if not isinstance(data, dict) or "error" in data:
        raise UpstreamResponseValidationError("Invalid upstream JSON object")
    repaired = 0
    if "choices" in data:
        if not isinstance(data["choices"], list):
            raise UpstreamResponseValidationError("Invalid upstream choices")
        for choice in data["choices"]:
            if not isinstance(choice, dict):
                raise UpstreamResponseValidationError("Invalid upstream choice")
            message = choice.get("message", {})
            if not isinstance(message, dict):
                raise UpstreamResponseValidationError("Invalid upstream message")
            function = pseudo_tool_function(message.get("content"), payload)
            if function is not None:
                message["content"] = None
                message["tool_calls"] = [{
                    "id": "call_pseudo_0",
                    "type": "function",
                    "function": function,
                }]
                if choice.get("finish_reason") == "stop":
                    choice["finish_reason"] = "tool_calls"
                repaired += 1
            if "tool_calls" in message:
                if not isinstance(message["tool_calls"], list):
                    raise UpstreamResponseValidationError("Invalid upstream tool calls")
                for tc in message["tool_calls"]:
                    if not isinstance(tc, dict):
                        raise UpstreamResponseValidationError("Invalid upstream tool call")
                    func = tc.get("function")
                    if not isinstance(func, dict):
                        raise UpstreamResponseValidationError("Invalid upstream tool function")
                    if not isinstance(func.get("name"), str) or not func["name"]:
                        raise UpstreamResponseValidationError("Invalid upstream tool function name")
                    if func["name"] not in advertised_tool_names(payload):
                        raise UpstreamResponseValidationError("Upstream tool was not advertised")
                    if not isinstance(func.get("arguments"), str):
                        raise UpstreamResponseValidationError("Invalid upstream tool arguments")
                    repaired += repair_function_arguments(func, payload)
    return json.dumps(data, separators=(",", ":")).encode("utf-8"), repaired

def response_has_renderable_output(response_body, content_type):
    """Require assistant text or a tool call before accepting a completion."""
    try:
        if "text/event-stream" in content_type:
            for event in parse_sse_events(response_body):
                if event["kind"] != "data":
                    continue
                choices = event["data"].get("choices", [])
                if not isinstance(choices, list):
                    return False
                for choice in choices:
                    if not isinstance(choice, dict):
                        return False
                    delta = choice.get("delta", {})
                    if not isinstance(delta, dict):
                        return False
                    content = delta.get("content")
                    if isinstance(content, str) and content.strip():
                        return True
                    tool_calls = delta.get("tool_calls")
                    if isinstance(tool_calls, list) and tool_calls:
                        return True
            return False

        data = json.loads(response_body.decode("utf-8"))
        choices = data.get("choices", []) if isinstance(data, dict) else []
        if not isinstance(choices, list):
            return False
        for choice in choices:
            if not isinstance(choice, dict):
                return False
            message = choice.get("message", {})
            if not isinstance(message, dict):
                return False
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return True
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                        return True
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                return True
        return False
    except (UnicodeDecodeError, json.JSONDecodeError, UpstreamResponseValidationError):
        return False

def response_runtime_evidence(response_body, content_type):
    try:
        if "text/event-stream" in content_type:
            values = [event["data"] for event in parse_sse_events(response_body) if event["kind"] == "data"]
        else:
            value = json.loads(response_body.decode("utf-8"))
            values = [value] if isinstance(value, dict) else []
    except (UnicodeDecodeError, json.JSONDecodeError, UpstreamResponseValidationError):
        return {"model": None, "provider": None, "effort": None, "reasoningBudget": None, "reasoningTokens": None, "responseId": None}

    def last_string(key):
        return next((item.get(key) for item in reversed(values) if isinstance(item.get(key), str) and item.get(key)), None)

    usage = next((item.get("usage") for item in reversed(values) if isinstance(item.get("usage"), dict)), {})
    details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    reasoning_config = next((item.get("reasoning") for item in reversed(values) if isinstance(item.get("reasoning"), dict)), {})
    effort = last_string("reasoning_effort")
    if effort is None and isinstance(reasoning_config.get("effort"), str):
        effort = reasoning_config["effort"]
    budget = reasoning_config.get("max_tokens") if isinstance(reasoning_config.get("max_tokens"), int) else None
    try:
        normalized_effort = normalize_reasoning_effort(effort) if effort is not None else None
    except InvalidReasoningEffortError:
        normalized_effort = None
    return {
        "model": last_string("model"),
        "provider": last_string("provider"),
        "effort": normalized_effort,
        "reasoningBudget": budget,
        "reasoningTokens": details.get("reasoning_tokens") if isinstance(details.get("reasoning_tokens"), int) else None,
        "responseId": last_string("id"),
    }


def response_effective_model(response_body, content_type):
    return response_runtime_evidence(response_body, content_type)["model"]

def sse_has_terminal_event(response_body):
    """Return true only when the whole SSE stream is valid and terminal."""
    try:
        parse_sse_events(response_body)
    except UpstreamResponseValidationError:
        return False
    return True

def blocking_wait(operation, on_wait=None, wait_seconds=None, on_disconnect=None, close_late_result=False):
    """Run one blocking operation while its caller remains able to emit SSE comments."""
    finished = threading.Event()
    lock = threading.Lock()
    state = {"value": None, "error": None, "abandoned": False}

    def close_result(value):
        if close_late_result and hasattr(value, "close"):
            try:
                value.close()
            except Exception:
                pass

    def worker():
        value = None
        error = None
        try:
            value = operation()
        except Exception as caught:
            error = caught
        with lock:
            if state["abandoned"]:
                late_value = value
            else:
                state["value"] = value
                state["error"] = error
                late_value = None
        close_result(late_value)
        finished.set()

    thread = threading.Thread(target=worker, name="nemotron-blocking-wait", daemon=True)
    thread.start()
    if on_wait is None:
        finished.wait()
    else:
        while True:
            timeout = wait_seconds() if callable(wait_seconds) else wait_seconds
            try:
                timeout = float(timeout if timeout is not None else SSE_HEARTBEAT_SECONDS)
            except (TypeError, ValueError):
                timeout = SSE_HEARTBEAT_SECONDS
            if finished.wait(max(0.001, timeout)):
                break
            if not on_wait():
                with lock:
                    state["abandoned"] = True
                    late_value = state["value"]
                    state["value"] = None
                if on_disconnect is not None:
                    try:
                        on_disconnect()
                    except Exception:
                        pass
                close_result(late_value)
                return None, BrokenPipeError("downstream client disconnected")
    with lock:
        return state["value"], state["error"]

def read_bounded_response(response, on_wait=None, wait_seconds=None):
    """Read and close one upstream response while keeping downstream SSE alive."""
    def reader():
        try:
            return response.read(MAX_BUFFERED_RESPONSE + 1), None
        except http.client.IncompleteRead as error:
            return bytes(error.partial or b""), error
        except (ConnectionResetError, ConnectionAbortedError, TimeoutError, OSError) as error:
            return b"", error
        finally:
            response.close()

    result, wait_error = blocking_wait(
        reader,
        on_wait=on_wait,
        wait_seconds=wait_seconds,
        on_disconnect=response.close,
    )
    if wait_error is not None:
        return b"", wait_error
    return result

class Handler(BaseHTTPRequestHandler):
    def client_write(self, body):
        try:
            self.wfile.write(body)
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def write_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        delivered = self.client_write(body)
        self.close_connection = True
        return delivered

    def write_json_error(self, status, message, error_type="upstream_error"):
        return self.write_json(status, {"error": {"message": message, "type": error_type}})

    def begin_request_audit(self):
        self._request_audit = {
            "requestId": str(uuid.uuid4()),
            "startedAt": time.monotonic(),
            "status": 500,
            "outcome": "internal_error",
            "delivered": False,
            "model": None,
            "requestedModel": None,
            "effectiveModel": None,
            "requestedEffort": None,
            "effectiveEffort": None,
            "requestedProvider": None,
            "effectiveGateway": None,
            "effectiveProvider": None,
            "reasoningBudget": None,
            "selectionGeneration": None,
            "responseId": None,
            "modelSubstitution": False,
            "failureType": None,
            "toolCount": 0,
            "compactionPhase": "none",
            "repairedToolCalls": 0,
            "payloadRepairs": 0,
            "toolFallbackUsed": False,
            "modelCandidateCount": 0,
            "catalogSource": "none",
            "upstreamProvider": "OpenRouter",
            "upstreamBaseUrl": UPSTREAM,
            "attempts": 0,
            "streamRecoveries": 0,
            "emptyResponseRetries": 0,
        }

    def update_request_audit(self, **values):
        if hasattr(self, "_request_audit"):
            self._request_audit.update(values)

    def finalize_request_audit(self):
        state = getattr(self, "_request_audit", None)
        if not state or state.get("finalized"):
            return
        state["finalized"] = True
        audit(
            requestId=state["requestId"],
            method="POST",
            upstream=urllib.parse.urlsplit(state.get("upstreamBaseUrl", UPSTREAM)).netloc,
            path=urllib.parse.urlsplit(state.get("upstreamBaseUrl", UPSTREAM) + "/chat/completions").path,
            upstreamProvider=state.get("upstreamProvider", "OpenRouter"),
            model=state.get("model"),
            requestedModel=state.get("requestedModel"),
            effectiveModel=state.get("effectiveModel"),
            requestedEffort=state.get("requestedEffort"),
            effectiveEffort=state.get("effectiveEffort"),
            requestedProvider=state.get("requestedProvider"),
            effectiveGateway=state.get("effectiveGateway"),
            effectiveProvider=state.get("effectiveProvider"),
            reasoningBudget=state.get("reasoningBudget"),
            selectionGeneration=state.get("selectionGeneration"),
            responseId=state.get("responseId"),
            modelSubstitution=bool(state.get("modelSubstitution")),
            failureType=state.get("failureType"),
            toolCount=state.get("toolCount", 0),
            compactionPhase=state.get("compactionPhase", "none"),
            repairedToolCalls=state.get("repairedToolCalls", 0),
            payloadRepairs=state.get("payloadRepairs", 0),
            toolFallbackUsed=bool(state.get("toolFallbackUsed")),
            modelCandidateCount=state.get("modelCandidateCount", 0),
            catalogSource=state.get("catalogSource", "none"),
            attempts=state.get("attempts", 0),
            streamRecoveries=state.get("streamRecoveries", 0),
            emptyResponseRetries=state.get("emptyResponseRetries", 0),
            durationMs=round((time.monotonic() - state["startedAt"]) * 1000),
            status=state.get("status", 500),
            outcome=state.get("outcome", "internal_error"),
            delivered=bool(state.get("delivered")),
        )

    def fail_request(self, status, message, error_type="upstream_error"):
        if getattr(self, "_buffered_sse_started", False):
            delivered = self.write_buffered_sse_error(message, error_type)
        else:
            delivered = self.write_json_error(status, message, error_type)
        self.update_request_audit(
            status=status,
            outcome=error_type if delivered else "client_disconnected",
            delivered=bool(delivered),
            failureType=error_type,
        )
        state = getattr(self, "_request_audit", {})
        record_runtime_failure(state.get("requestId"), error_type)
        return delivered

    def start_buffered_sse(self, request_id, metadata):
        self._buffered_sse_started = True
        self._buffered_sse_finished = False
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-OpenRouter-Request-Id", request_id)
        self.send_header("X-OpenRouter-Model", metadata["model"])
        self.send_header("Connection", "close")
        self.end_headers()
        written = self.client_write(b": nemotron-buffering\n\n")
        if not written:
            self.close_connection = True
        return written

    def buffered_sse_heartbeat(self):
        return self.client_write(b": nemotron-buffering\n\n")

    def write_buffered_sse_error(self, message, error_type):
        if getattr(self, "_buffered_sse_finished", False):
            return False
        payload = json.dumps({"error": {"message": message, "type": error_type}}, separators=(",", ":"))
        written = self.client_write(("event: error\ndata: " + payload + "\n\ndata: [DONE]\n\n").encode())
        self._buffered_sse_finished = True
        self.close_connection = True
        return written

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/v1/runtime-selection":
            try:
                length = int(self.headers.get("Content-Length", ""))
                if length < 1 or length > 64 * 1024:
                    raise ValueError("invalid selection size")
                value = json.loads(self.rfile.read(length).decode("utf-8"))
                result = update_runtime_selection(value)
            except ModelUnavailableError as error:
                self.write_json_error(404, str(error), "model_unavailable_error")
                return
            except CatalogUnavailableError as error:
                self.write_json_error(503, str(error), "catalog_unavailable_error")
                return
            except InvalidReasoningEffortError as error:
                self.write_json_error(422, str(error), "unsupported_effort_error")
                return
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                self.write_json_error(400, str(error), "invalid_request_error")
                return
            self.write_json(200, result)
            return
        self.begin_request_audit()
        if path != "/v1/chat/completions":
            self.fail_request(404, "Not found", "not_found")
            self.finalize_request_audit()
            return
        if not REQUEST_SLOTS.acquire(timeout=5.0):
            self.fail_request(503, "The local proxy is at its bounded concurrency limit", "overloaded_error")
            self.finalize_request_audit()
            return
        try:
            try:
                self.handle_chat_completion()
            except Exception as error:
                self.fail_request(
                    500,
                    f"Local proxy request failure: {type(error).__name__}",
                    "internal_error",
                )
        finally:
            REQUEST_SLOTS.release()
            self.finalize_request_audit()

    def handle_chat_completion(self):
        started = time.monotonic()
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.fail_request(400, "Invalid Content-Length", "invalid_request_error")
            return
        if length < 1:
            self.fail_request(400, "A JSON request body is required", "invalid_request_error")
            return
        if length > MAX_REQUEST_BYTES:
            self.fail_request(413, "Request body exceeds the local proxy limit", "invalid_request_error")
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.fail_request(400, "Request body must be valid JSON", "invalid_request_error")
            return
        if not isinstance(payload, dict):
            self.fail_request(400, "Request body must be a JSON object", "invalid_request_error")
            return

        payload, selection_context = runtime_override_for_request(payload)
        requested_model = payload.get("model")
        tool_count = len(payload.get("tools", [])) if isinstance(payload.get("tools"), list) else 0
        image_input = payload_has_image(payload)
        snapshot = None
        try:
            needs_current_catalog = bool(
                tool_count
                or image_input
                or requested_model in LIVE_GATED_MODELS
            )
            if requested_model in LIVE_GATED_MODELS:
                snapshot = current_exact_nemotron_snapshot()
            else:
                snapshot = current_tool_catalog_snapshot() if needs_current_catalog else catalog_snapshot(allow_network=False)
            payload, metadata = normalize_payload(payload, snapshot, locked_selection=selection_context is not None)
            metadata["selectionGeneration"] = selection_context.get("generation") if selection_context else None
            metadata["threadId"] = selection_context.get("threadId") if selection_context else None
            metadata["turnId"] = selection_context.get("turnId") if selection_context else None
        except InvalidReasoningEffortError as error:
            self.fail_request(400, str(error), "invalid_request_error")
            return
        except ModelUnavailableError as error:
            self.update_request_audit(
                requestedModel=requested_model,
                effectiveModel=None,
                toolCount=tool_count,
                imageInput=image_input,
                catalogSource=snapshot["source"] if snapshot else "unavailable",
            )
            self.fail_request(404, str(error), "model_unavailable_error")
            return
        except CatalogUnavailableError:
            self.update_request_audit(
                requestedModel=requested_model,
                toolCount=tool_count,
                imageInput=image_input,
                catalogSource=snapshot["source"] if snapshot else "unavailable",
            )
            self.fail_request(
                503,
                "Current provider catalog is unavailable or cannot verify the requested model capabilities",
                "model_unavailable_error",
            )
            return

        request_id = self._request_audit["requestId"]
        self.update_request_audit(
            model=metadata["model"],
            requestedModel=metadata["requestedModel"],
            effectiveModel=metadata["effectiveModel"],
            requestedEffort=metadata["requestedEffort"],
            effectiveEffort=metadata["effectiveEffort"],
            transportEffort=metadata["transportEffort"],
            toolCount=metadata["toolCount"],
            imageInput=metadata["imageInput"],
            compactionPhase=metadata["compactionPhase"],
            payloadRepairs=metadata["payloadRepairs"],
            toolFallbackUsed=metadata["toolFallbackUsed"],
            modelCandidateCount=len(metadata["modelCandidates"]),
            catalogSource=metadata["catalogSource"],
            reasoningBudget=metadata["reasoningBudget"],
            selectionApplied=metadata["selectionApplied"],
            selectionGeneration=metadata.get("selectionGeneration"),
        )

        stream_requested = payload.get("stream") is True
        response = None
        response_body = None
        attempts = 0
        stream_recoveries = 0
        empty_response_retries = 0
        content_type = "application/octet-stream"
        status = 502
        sse_started = False
        last_sse_write = [time.monotonic()]

        def record_disconnect():
            self.update_request_audit(
                status=499,
                outcome="client_disconnected",
                delivered=False,
                attempts=attempts,
                streamRecoveries=stream_recoveries,
            )
            record_runtime_failure(request_id, "client_disconnected")

        def heartbeat_wait_seconds():
            return max(0.001, SSE_HEARTBEAT_SECONDS - (time.monotonic() - last_sse_write[0]))

        def heartbeat():
            if not self.buffered_sse_heartbeat():
                return False
            last_sse_write[0] = time.monotonic()
            return True

        def retry_pause(seconds):
            deadline = time.monotonic() + max(0.0, seconds)
            while True:
                remaining_pause = deadline - time.monotonic()
                if remaining_pause <= 0:
                    return True
                if not sse_started:
                    time.sleep(remaining_pause)
                    return True
                time.sleep(min(remaining_pause, heartbeat_wait_seconds()))
                if time.monotonic() - last_sse_write[0] >= SSE_HEARTBEAT_SECONDS:
                    if not heartbeat():
                        return False

        if stream_requested:
            sse_started = True
            if not self.start_buffered_sse(request_id, metadata):
                record_disconnect()
                return
            last_sse_write[0] = time.monotonic()

        route = upstream_route(metadata["model"])
        upstream_base_url = route["baseUrl"]
        self.update_request_audit(
            upstreamProvider=route["provider"],
            upstreamBaseUrl=upstream_base_url,
            requestedProvider=route["provider"],
        )
        record_dispatched_runtime_selection(metadata, route, request_id)
        request_deadline_seconds = (
            DOLPHIN_X1_REQUEST_DEADLINE_SECONDS
            if route["provider"] == "paired-pc-llama.cpp"
            else REQUEST_DEADLINE_SECONDS
        )
        if route["provider"] == "OpenRouter":
            if sse_started:
                api_key, key_error = blocking_wait(
                    get_api_key,
                    on_wait=heartbeat,
                    wait_seconds=heartbeat_wait_seconds,
                )
            else:
                try:
                    api_key = get_api_key()
                    key_error = None
                except Exception as error:
                    api_key = None
                    key_error = error
        else:
            api_key = route["apiKey"]
            key_error = None
        if isinstance(key_error, BrokenPipeError):
            record_disconnect()
            return
        if key_error is not None:
            self.fail_request(500, f"OpenRouter credential lookup failed: {type(key_error).__name__}", "authentication_error")
            return
        if route["provider"] == "OpenRouter" and not api_key:
            self.fail_request(401, "OpenRouter API key not configured. Add OPENROUTER_API_KEY to openrouter.env", "authentication_error")
            return
        headers = {
            "Content-Type": "application/json",
            "X-Title": "Nemotron Unrestricted",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        for name in ("Accept", "User-Agent"):
            if self.headers.get(name):
                headers[name] = self.headers[name]

        for attempt in range(MAX_UPSTREAM_ATTEMPTS):
            remaining = request_deadline_seconds - (time.monotonic() - started)
            if remaining <= 0:
                self.fail_request(504, f"{route['provider']} request deadline exceeded", "timeout_error")
                return
            attempts = attempt + 1
            self.update_request_audit(attempts=attempts)
            response_body = None
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            request = urllib.request.Request(f"{upstream_base_url}/chat/completions", data=body, headers=headers, method="POST")

            def open_upstream():
                try:
                    upstream_timeout = 600.0 if route["provider"] == "paired-pc-llama.cpp" else 180.0
                    return urllib.request.urlopen(request, timeout=max(1.0, min(upstream_timeout, remaining)))
                except urllib.error.HTTPError as error:
                    return error

            if sse_started:
                response, open_error = blocking_wait(
                    open_upstream,
                    on_wait=heartbeat,
                    wait_seconds=heartbeat_wait_seconds,
                    close_late_result=True,
                )
            else:
                try:
                    response = open_upstream()
                    open_error = None
                except Exception as error:
                    response = None
                    open_error = error
            if isinstance(open_error, BrokenPipeError):
                record_disconnect()
                return
            if open_error is not None:
                if isinstance(open_error, (urllib.error.URLError, TimeoutError, OSError)) and attempt < MAX_UPSTREAM_ATTEMPTS - 1:
                    if not retry_pause(recovery_delay(attempt)):
                        record_disconnect()
                        return
                    continue
                self.fail_request(502, f"OpenRouter request failed: {type(open_error).__name__}")
                return
            try:
                status = response.getcode()
                content_type = str(response.headers.get("Content-Type", "application/octet-stream"))
                if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
                    raise ValueError("invalid upstream status")
            except Exception as error:
                try:
                    response.close()
                except Exception:
                    pass
                self.fail_request(502, f"OpenRouter response metadata failed: {type(error).__name__}")
                return
            response_body, read_error = read_bounded_response(
                response,
                heartbeat if sse_started else None,
                heartbeat_wait_seconds if sse_started else None,
            )
            if len(response_body) > MAX_BUFFERED_RESPONSE:
                self.fail_request(502, "OpenRouter response exceeds isolated proxy buffer limit")
                return
            if read_error is not None:
                if isinstance(read_error, BrokenPipeError):
                    record_disconnect()
                    return
                if (status < 400 or status in RETRYABLE) and attempt < MAX_UPSTREAM_ATTEMPTS - 1:
                    stream_recoveries += 1
                    self.update_request_audit(streamRecoveries=stream_recoveries)
                    if status in {429, 503} and metadata["modelCandidates"]:
                        next_candidate = metadata["modelCandidates"].index(metadata["model"]) + 1
                        if select_tool_candidate(payload, metadata, next_candidate):
                            metadata["payloadRepairs"] += 1
                            self.update_request_audit(
                                model=metadata["model"],
                                effectiveModel=metadata["effectiveModel"],
                                payloadRepairs=metadata["payloadRepairs"],
                                toolFallbackUsed=metadata["toolFallbackUsed"],
                            )
                    delay = retry_delay(response, attempt) if status in RETRYABLE else recovery_delay(attempt)
                    if not retry_pause(delay):
                        record_disconnect()
                        return
                    continue
                self.fail_request(502, f"OpenRouter response stream interrupted before completion: {type(read_error).__name__}", "stream_incomplete_error")
                return
            if status == 400 and attempt < MAX_UPSTREAM_ATTEMPTS - 1:
                if repair_tool_choice_validation(payload, response_body):
                    metadata["payloadRepairs"] += 1
                    self.update_request_audit(payloadRepairs=metadata["payloadRepairs"])
                    if not retry_pause(0.15):
                        record_disconnect()
                        return
                    continue
            if (
                metadata["modelCandidates"]
                and (
                    model_route_unavailable(status, response_body)
                    or (metadata["imageInput"] and status in {400, 403, 404, 410, 422})
                )
                and attempt < MAX_UPSTREAM_ATTEMPTS - 1
            ):
                next_candidate = metadata["modelCandidates"].index(metadata["model"]) + 1
                if select_tool_candidate(payload, metadata, next_candidate):
                    metadata["payloadRepairs"] += 1
                    self.update_request_audit(
                        model=metadata["model"],
                        effectiveModel=metadata["effectiveModel"],
                        payloadRepairs=metadata["payloadRepairs"],
                        toolFallbackUsed=metadata["toolFallbackUsed"],
                    )
                    if not retry_pause(0.15):
                        record_disconnect()
                        return
                    continue
            if status in RETRYABLE and attempt < MAX_UPSTREAM_ATTEMPTS - 1:
                if status in {429, 503} and metadata["modelCandidates"]:
                    next_candidate = metadata["modelCandidates"].index(metadata["model"]) + 1
                    if select_tool_candidate(payload, metadata, next_candidate):
                        metadata["payloadRepairs"] += 1
                        self.update_request_audit(
                            model=metadata["model"],
                            effectiveModel=metadata["effectiveModel"],
                            payloadRepairs=metadata["payloadRepairs"],
                            toolFallbackUsed=metadata["toolFallbackUsed"],
                        )
                if not retry_pause(retry_delay(response, attempt)):
                    record_disconnect()
                    return
                continue
            if metadata.get("exactRoute") and status in {401, 402, 403}:
                upstream_error = response_error_message(response_body)
                if "key limit exceeded" in upstream_error:
                    reason = "credential_limit_exhausted"
                    message = "The configured OpenRouter credential has no remaining usage limit"
                    error_type = "credential_limit_error"
                elif status == 402 or "credit" in upstream_error:
                    reason = "credential_credit_unavailable"
                    message = "The configured OpenRouter account has no available inference credit"
                    error_type = "credential_credit_error"
                else:
                    reason = "credential_disabled" if status == 403 else "credential_unavailable"
                    message = "The configured OpenRouter credential was rejected"
                    error_type = "authentication_error"
                mark_exact_nemotron_unusable(reason)
                self.fail_request(status, message, error_type)
                return
            if status >= 400:
                self.fail_request(status, f"OpenRouter request failed with status {status}")
                return

            normalized_content_type = content_type.partition(";")[0].strip().casefold()
            if sse_started and normalized_content_type != "text/event-stream":
                self.fail_request(502, "OpenRouter returned a non-SSE response for a streaming request", "invalid_upstream_response")
                return
            if not sse_started and normalized_content_type not in {"application/json", "text/json"}:
                self.fail_request(502, "OpenRouter returned a non-JSON response for a non-streaming request", "invalid_upstream_response")
                return
            if sse_started:
                try:
                    parse_sse_events(response_body)
                except UpstreamResponseValidationError as error:
                    if str(error) == "SSE terminal event missing" and attempt < MAX_UPSTREAM_ATTEMPTS - 1:
                        stream_recoveries += 1
                        self.update_request_audit(streamRecoveries=stream_recoveries)
                        if not retry_pause(recovery_delay(attempt)):
                            record_disconnect()
                            return
                        continue
                    error_type = "stream_incomplete_error" if str(error) == "SSE terminal event missing" else "invalid_upstream_response"
                    self.fail_request(502, str(error), error_type)
                    return
            if not response_has_renderable_output(response_body, content_type):
                empty_response_retries += 1
                self.update_request_audit(emptyResponseRetries=empty_response_retries)
                if attempt < MAX_UPSTREAM_ATTEMPTS - 1:
                    if metadata["modelCandidates"]:
                        try:
                            candidate_index = metadata["modelCandidates"].index(metadata["model"]) + 1
                        except ValueError:
                            candidate_index = 0
                        if select_tool_candidate(payload, metadata, candidate_index):
                            metadata["payloadRepairs"] += 1
                            self.update_request_audit(
                                model=metadata["model"],
                                effectiveModel=metadata["effectiveModel"],
                                payloadRepairs=metadata["payloadRepairs"],
                                toolFallbackUsed=metadata["toolFallbackUsed"],
                            )
                    if not retry_pause(recovery_delay(attempt)):
                        record_disconnect()
                        return
                    continue
                self.fail_request(
                    502,
                    "OpenRouter returned no assistant text or tool call after bounded retries",
                    "empty_response_error",
                )
                return
            break

        repaired = 0
        try:
            if sse_started:
                response_body, repaired = repair_sse_response(response_body, payload)
            else:
                response_body, repaired = repair_json_response(response_body, payload)
        except (ToolArgumentValidationError, UpstreamResponseValidationError) as error:
            self.fail_request(502, f"OpenRouter response validation failed: {type(error).__name__}", "invalid_upstream_response")
            return
        except Exception as error:
            self.fail_request(502, f"OpenRouter response repair failed: {type(error).__name__}", "invalid_upstream_response")
            return

        if sse_started and not response_body.endswith(b"data: [DONE]\n\n"):
            self.fail_request(502, "OpenRouter response repair produced invalid SSE framing", "invalid_upstream_response")
            return

        evidence = response_runtime_evidence(response_body, content_type)
        effective_model = evidence["model"]
        self.update_request_audit(
            effectiveGateway=route["provider"],
            effectiveProvider=evidence.get("provider"),
            effectiveEffort=evidence.get("effort"),
            reasoningBudget=evidence.get("reasoningBudget") or metadata.get("reasoningBudget"),
            responseId=evidence.get("responseId"),
        )
        if metadata.get("exactRoute") and not effective_model:
            self.fail_request(
                502,
                "Provider response omitted model identity for the active exact selection",
                "model_identity_missing_error",
            )
            return
        if metadata.get("exactRoute") and effective_model != metadata["model"]:
            self.update_request_audit(effectiveModel=effective_model, modelSubstitution=True)
            record_confirmed_runtime_selection(metadata, route, request_id, evidence)
            self.fail_request(
                502,
                "Provider returned a different model than the active exact selection",
                "model_substitution_error",
            )
            return
        if (
            metadata.get("exactRoute")
            and metadata["model"] == EXACT_NEMOTRON_MODEL
            and evidence.get("provider") != EXACT_NEMOTRON_UPSTREAM_PROVIDER
        ):
            self.fail_request(
                502,
                "Provider returned an unverified route for the active exact selection",
                "provider_substitution_error",
            )
            return
        metadata["effectiveModel"] = effective_model
        if effective_model != metadata["model"] and effective_model in metadata["modelCandidates"]:
            metadata["toolFallbackUsed"] = True
        self.update_request_audit(
            model=metadata["model"],
            effectiveModel=effective_model,
            repairedToolCalls=repaired,
            payloadRepairs=metadata["payloadRepairs"],
            toolFallbackUsed=metadata["toolFallbackUsed"],
            attempts=attempts,
            streamRecoveries=stream_recoveries,
            emptyResponseRetries=empty_response_retries,
        )
        record_confirmed_runtime_selection(metadata, route, request_id, evidence)

        if not sse_started:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("X-OpenRouter-Request-Id", request_id)
            if effective_model:
                self.send_header("X-OpenRouter-Model", effective_model)
            self.send_header("X-OpenRouter-Tool-Repairs", str(repaired))
            self.send_header("X-OpenRouter-Stream-Recoveries", str(stream_recoveries))
            self.send_header("Connection", "close")
            self.end_headers()
        delivered = self.client_write(response_body)
        if sse_started:
            self._buffered_sse_finished = True
        self.close_connection = True
        self.update_request_audit(
            status=status,
            outcome="success" if delivered else "client_disconnected",
            delivered=bool(delivered),
        )

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/vault-health":
            credential = credential_state(resolve_broker=False)
            local_dolphin = dolphin_x1_health(allow_network=True)
            self.write_json(200, {
                "status": "ok",
                "app": APP_ID,
                "provider": "OpenRouter",
                "model": DEFAULT_MODEL,
                "requestedDolphinModel": REQUESTED_DOLPHIN_MODEL,
                "requestedDolphinAvailable": REQUESTED_DOLPHIN_MODEL in catalog_snapshot(allow_network=False)["models"],
                "availableDolphinModel": AVAILABLE_DOLPHIN_MODEL,
                "exactDolphinModel": DOLPHIN_X1_MODEL,
                "exactDolphinAvailable": local_dolphin["available"],
                "exactDolphinProvider": "paired-pc-llama.cpp" if local_dolphin["available"] else None,
                "exactDolphinHealthError": local_dolphin["error"],
                "modelSubstitution": False,
                "toolModel": DEFAULT_TOOL_MODEL,
                "proxyPort": PORT,
                "port": PORT,
                "guiPort": GUI_PORT,
                "supervisorPort": SUPERVISOR_PORT,
                "providerBaseUrl": PROVIDER_BASE_URL,
                "effectiveBaseUrl": PROVIDER_BASE_URL,
                "sourceHash": SOURCE_SHA256,
                "sourceSha256": SOURCE_SHA256,
                "supervisorSourceHash": SUPERVISOR_SOURCE_SHA256,
                "capabilityContractSha256": MODEL_CAPABILITY_CONTRACT_SHA256,
                "capabilityContractAppliesToEveryModel": True,
                "englishProgressRequired": True,
                "credentialConfigured": credential["configured"],
                "credentialSourceFingerprint": credential["fingerprint"],
                "requestConcurrency": REQUEST_CONCURRENCY,
            })
        elif path in {"/models", "/v1/models"}:
            try:
                snapshot = current_exact_nemotron_snapshot()
            except CatalogUnavailableError:
                snapshot = gate_exact_nemotron_snapshot(
                    catalog_snapshot(allow_network=False),
                    {
                        "usable": False,
                        "providerVerified": False,
                        "supportsMax": False,
                        "reason": "capability_verification_unavailable",
                    },
                )
            self.write_json(200, models_payload(snapshot, allow_local_network=True))
        elif path == "/v1/runtime-selection":
            self.write_json(200, runtime_selection_payload())
        else:
            self.write_json_error(404, "Not found", "not_found")

    def log_message(self, format, *args):
        pass

class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)

if __name__ == "__main__":
    Server(("127.0.0.1", PORT), Handler).serve_forever()
