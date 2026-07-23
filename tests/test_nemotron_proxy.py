import importlib.util
import copy
import http.client
import os
import pathlib
import tempfile
import threading
import time
import unittest
import json
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_CODEX_HOME = pathlib.Path(tempfile.mkdtemp(prefix="nemotron-proxy-test-"))
_ORIGINAL_CODEX_HOME = os.environ.get("CODEX_HOME")
os.environ["CODEX_HOME"] = str(TEST_CODEX_HOME)
SPEC = importlib.util.spec_from_file_location("nemotron_unrestricted_proxy", PROJECT_ROOT / "nemotron_unrestricted_proxy.py")
PROXY = importlib.util.module_from_spec(SPEC)
try:
    SPEC.loader.exec_module(PROXY)
finally:
    if _ORIGINAL_CODEX_HOME is None:
        os.environ.pop("CODEX_HOME", None)
    else:
        os.environ["CODEX_HOME"] = _ORIGINAL_CODEX_HOME


class FakeCatalogResponse:
    def __init__(self, payload, content_type="application/json"):
        self.payload = json.dumps(payload).encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def getcode(self):
        return 200

    def read(self, _limit):
        return self.payload

    def close(self):
        self.closed = True


def catalog_snapshot(rows, source="live"):
    models = {}
    for row in rows:
        entry = PROXY.normalize_catalog_entry(row)
        if entry is not None:
            models[entry["id"]] = entry
    return {"models": models, "source": source, "ageSeconds": 0.0}


class ProxyNormalizationTests(unittest.TestCase):
    def wait_catalog_refresh(self, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with PROXY.CATALOG_LOCK:
                if not PROXY.CATALOG_REFRESHING:
                    return
            time.sleep(0.001)
        self.fail("catalog refresh did not finish")

    def preserve_catalog_state(self):
        with PROXY.CATALOG_LOCK:
            saved_cache = {
                "models": dict(PROXY.CATALOG_CACHE["models"]),
                "loadedAt": PROXY.CATALOG_CACHE["loadedAt"],
            }
            saved_refreshing = PROXY.CATALOG_REFRESHING

        def restore():
            self.wait_catalog_refresh()
            with PROXY.CATALOG_LOCK:
                PROXY.CATALOG_CACHE.clear()
                PROXY.CATALOG_CACHE.update(saved_cache)
                PROXY.CATALOG_REFRESHING = saved_refreshing

        self.addCleanup(restore)

    def test_health_identity_and_concurrency_are_bounded_in_source(self):
        self.assertEqual(PROXY.APP_ID, "nemotron-unrestricted")
        self.assertEqual(len(PROXY.SOURCE_SHA256), 64)
        self.assertGreaterEqual(PROXY.REQUEST_CONCURRENCY, 1)
        self.assertLessEqual(PROXY.REQUEST_CONCURRENCY, 64)
        source = (PROJECT_ROOT / "nemotron_unrestricted_proxy.py").read_text(encoding="utf-8")
        self.assertIn("REQUEST_SLOTS.acquire", source)
        self.assertIn("REQUEST_SLOTS.release", source)
        self.assertIn("credentialConfigured", source)
        self.assertIn("sourceSha256", source)
        self.assertIn("SUPERVISOR_SOURCE_SHA256", source)
    def test_text_only_hermes_request_stays_on_hermes(self):
        payload, metadata = PROXY.normalize_payload({"model": PROXY.DEFAULT_MODEL, "messages": []})
        self.assertEqual(payload["model"], PROXY.DEFAULT_MODEL)
        self.assertEqual(metadata["model"], PROXY.DEFAULT_MODEL)
        self.assertEqual(metadata["toolCount"], 0)
        self.assertFalse(metadata["imageInput"])

    def test_available_dolphin_selection_is_preserved_without_substitution(self):
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.AVAILABLE_DOLPHIN_MODEL,
            "messages": [],
        })
        self.assertEqual(payload["model"], PROXY.AVAILABLE_DOLPHIN_MODEL)
        self.assertEqual(metadata["requestedModel"], PROXY.AVAILABLE_DOLPHIN_MODEL)
        self.assertEqual(metadata["effectiveModel"], PROXY.AVAILABLE_DOLPHIN_MODEL)
        self.assertEqual(metadata["payloadRepairs"], 0)

    def test_nonexistent_requested_dolphin_is_rejected_not_silently_substituted(self):
        with self.assertRaises(PROXY.ModelUnavailableError):
            PROXY.normalize_payload({
                "model": PROXY.REQUESTED_DOLPHIN_MODEL,
                "messages": [],
            })

    def test_exact_dolphin_successor_is_hidden_until_local_endpoint_is_healthy(self):
        with mock.patch.object(PROXY, "dolphin_x1_health", return_value={
            "available": False, "checkedAt": 0.0, "error": "unreachable", "ageSeconds": 0.0,
        }):
            ids = {entry["id"] for entry in PROXY.models_payload()["data"]}
        self.assertNotIn(PROXY.DOLPHIN_X1_MODEL, ids)

    def test_exact_dolphin_successor_is_selectable_only_after_health_verification(self):
        healthy = {"available": True, "checkedAt": 1.0, "error": None, "ageSeconds": 0.0}
        with mock.patch.object(PROXY, "dolphin_x1_health", return_value=healthy):
            payload, metadata = PROXY.normalize_payload({
                "model": PROXY.DOLPHIN_X1_MODEL,
                "messages": [],
            })
            ids = {entry["id"] for entry in PROXY.models_payload(allow_local_network=True)["data"]}
        self.assertEqual(payload["model"], PROXY.DOLPHIN_X1_MODEL)
        self.assertEqual(metadata["effectiveModel"], PROXY.DOLPHIN_X1_MODEL)
        self.assertIn(PROXY.DOLPHIN_X1_MODEL, ids)

    def test_exact_dolphin_successor_never_silently_falls_back_when_unhealthy(self):
        unavailable = {"available": False, "checkedAt": 1.0, "error": "unreachable", "ageSeconds": 0.0}
        with mock.patch.object(PROXY, "dolphin_x1_health", return_value=unavailable):
            with self.assertRaises(PROXY.ModelUnavailableError):
                PROXY.normalize_payload({"model": PROXY.DOLPHIN_X1_MODEL, "messages": []})

    def test_exact_dolphin_uses_paired_pc_route_while_other_models_use_openrouter(self):
        with mock.patch.object(PROXY, "DOLPHIN_X1_BASE_URL", "http://100.64.0.1:18780/v1"):
            local = PROXY.upstream_route(PROXY.DOLPHIN_X1_MODEL)
        remote = PROXY.upstream_route(PROXY.DEFAULT_MODEL)
        self.assertEqual(local["provider"], "paired-pc-llama.cpp")
        self.assertEqual(local["baseUrl"], "http://100.64.0.1:18780/v1")
        self.assertEqual(remote["provider"], "OpenRouter")
        self.assertEqual(remote["baseUrl"], PROXY.UPSTREAM)

    def test_actionable_download_install_request_requires_a_tool_before_prose(self):
        snapshot = catalog_snapshot([
            {"id": "vendor/free-tool", "supported_parameters": ["tools", "tool_choice"], "pricing": {"prompt": "0", "completion": "0"}},
        ])
        payload, _ = PROXY.normalize_payload({
            "model": PROXY.AVAILABLE_DOLPHIN_MODEL,
            "messages": [{"role": "user", "content": "Find the latest lawful APK online, download it, and install the verified package on my Android device"}],
            "tools": [{"type": "function", "function": {"name": "exec_command", "parameters": {"type": "object"}}}],
        }, snapshot)
        self.assertEqual(payload["tool_choice"], "required")

    def test_actionable_request_returns_to_auto_after_a_tool_result(self):
        snapshot = catalog_snapshot([
            {"id": "vendor/free-tool", "supported_parameters": ["tools", "tool_choice"], "pricing": {"prompt": "0", "completion": "0"}},
        ])
        payload, _ = PROXY.normalize_payload({
            "model": PROXY.AVAILABLE_DOLPHIN_MODEL,
            "messages": [
                {"role": "user", "content": "Search online and download the verified app package"},
                {"role": "tool", "tool_call_id": "fixture", "content": "verified result"},
            ],
            "tools": [{"type": "function", "function": {"name": "exec_command", "parameters": {"type": "object"}}}],
            "tool_choice": "required",
        }, snapshot)
        self.assertEqual(payload["tool_choice"], "auto")

    def test_image_parts_are_detected_in_chat_and_responses_payloads(self):
        self.assertTrue(PROXY.payload_has_image({
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
            ]}],
        }))
        self.assertTrue(PROXY.payload_has_image({
            "input": [{"role": "user", "content": [
                {"type": "input_image", "image_url": "https://example.invalid/image.jpg"},
            ]}],
        }))
        self.assertFalse(PROXY.payload_has_image({
            "messages": [{"role": "user", "content": "the word image_url is only text"}],
        }))

    def test_image_request_routes_to_verified_free_vision_model(self):
        snapshot = catalog_snapshot([
            {"id": "vendor/paid-vision", "supported_parameters": ["tools"], "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}, "pricing": {"prompt": "0.01", "completion": "0"}},
            {"id": "vendor/free-text", "supported_parameters": ["tools"], "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}, "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "google/gemma-4-31b-it:free", "supported_parameters": ["tools"], "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}, "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "supported_parameters": ["tools", "tool_choice"], "architecture": {"input_modalities": ["text", "image", "video"], "output_modalities": ["text"]}, "pricing": {"prompt": "0", "completion": "0"}},
        ])
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "describe this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
            ]}],
        }, snapshot)
        self.assertEqual(payload["model"], "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
        self.assertEqual(payload["models"], ["google/gemma-4-31b-it:free"])
        self.assertTrue(metadata["imageInput"])
        self.assertEqual(metadata["toolCount"], 0)

    def test_image_plus_tools_requires_one_model_supporting_both(self):
        snapshot = catalog_snapshot([
            {"id": "vendor/vision-no-tools:free", "supported_parameters": [], "architecture": {"input_modalities": ["image", "text"], "output_modalities": ["text"]}, "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "google/gemma-4-31b-it:free", "supported_parameters": ["tools"], "architecture": {"input_modalities": ["image", "text"], "output_modalities": ["text"]}, "pricing": {"prompt": "0", "completion": "0"}},
        ])
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": [{"type": "input_image", "image_url": "https://example.invalid/a.png"}]}],
            "tools": [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        }, snapshot)
        self.assertEqual(payload["model"], "google/gemma-4-31b-it:free")
        self.assertEqual(metadata["toolCount"], 1)
        self.assertTrue(metadata["imageInput"])

    def test_reasoning_effort_metadata_is_truthful(self):
        _, default_metadata = PROXY.normalize_payload({"model": PROXY.DEFAULT_MODEL, "messages": []})
        _, explicit_metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [],
            "reasoning": {"effort": "high"},
        })
        self.assertIsNone(default_metadata["requestedEffort"])
        self.assertEqual(default_metadata["transportEffort"], "provider-default")
        self.assertIsNone(default_metadata["effectiveEffort"])
        self.assertEqual(explicit_metadata["requestedEffort"], "high")
        self.assertEqual(explicit_metadata["transportEffort"], "high")
        self.assertIsNone(explicit_metadata["effectiveEffort"])

    def test_max_effort_is_exact_documented_reasoning_budget(self):
        snapshot = catalog_snapshot([{
            "id": PROXY.EXACT_NEMOTRON_MODEL,
            "supported_parameters": ["reasoning", "max_tokens"],
            "reasoning": {"supports_max_tokens": True, "supported_efforts": ["high", "medium"]},
            "pricing": {"prompt": "0.0000006", "completion": "0.0000036"},
        }])
        snapshot["models"][PROXY.EXACT_NEMOTRON_MODEL]["exactProviderVerified"] = True
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.EXACT_NEMOTRON_MODEL,
            "messages": [],
            "reasoning": {"effort": "max"},
        }, snapshot)
        self.assertEqual(payload["reasoning"], {"max_tokens": 128000})
        self.assertNotIn("reasoning_effort", payload)
        self.assertEqual(metadata["requestedEffort"], "max")
        self.assertEqual(metadata["transportEffort"], "max")
        self.assertIsNone(metadata["effectiveEffort"])
        self.assertEqual(metadata["reasoningBudget"], 128000)

    def test_max_effort_fails_closed_without_exact_live_capability(self):
        unsupported = catalog_snapshot([{
            "id": PROXY.DEFAULT_MODEL,
            "supported_parameters": ["reasoning"],
            "reasoning": {"supports_max_tokens": False, "supported_efforts": ["high"]},
            "pricing": {"prompt": "0.1", "completion": "0.2"},
        }])
        with self.assertRaisesRegex(PROXY.InvalidReasoningEffortError, "unsupported"):
            PROXY.normalize_payload({
                "model": PROXY.DEFAULT_MODEL,
                "messages": [],
                "reasoning": {"effort": "max"},
            }, unsupported)
        stale = dict(unsupported)
        stale["source"] = "stale"
        with self.assertRaisesRegex(PROXY.InvalidReasoningEffortError, "unsupported"):
            PROXY.reasoning_budget_for(PROXY.DEFAULT_MODEL, stale)

    def test_locked_exact_nemotron_preserves_model_for_tool_requests(self):
        exact = "nvidia/nemotron-3-ultra-550b-a55b"
        snapshot = catalog_snapshot([{
            "id": exact,
            "supported_parameters": ["tools", "tool_choice", "reasoning", "max_tokens"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {"prompt": "0.0000006", "completion": "0.0000036"},
        }])
        payload, metadata = PROXY.normalize_payload({
            "model": exact,
            "messages": [{"role": "user", "content": "run a tool"}],
            "tools": [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        }, snapshot, locked_selection=True)
        self.assertEqual(payload["model"], exact)
        self.assertNotIn("models", payload)
        self.assertEqual(payload["provider"], {
            "order": [PROXY.EXACT_NEMOTRON_UPSTREAM_PROVIDER],
            "allow_fallbacks": False,
            "require_parameters": True,
        })
        self.assertEqual(metadata["requestedModel"], exact)
        self.assertEqual(metadata["effectiveModel"], exact)
        self.assertTrue(metadata["selectionApplied"])

    def test_live_selection_is_scoped_to_one_matching_active_thread(self):
        exact = "nvidia/nemotron-3-ultra-550b-a55b"
        snapshot = catalog_snapshot([{
            "id": exact,
            "supported_parameters": ["tools", "reasoning", "max_tokens"],
            "reasoning": {"supports_max_tokens": True, "supported_efforts": ["high", "medium"]},
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {"prompt": "0.0000006", "completion": "0.0000036"},
        }])
        snapshot["models"][exact]["exactProviderVerified"] = True
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            active_path = root / "active-turns.json"
            selection_path = root / "runtime-selection.json"
            active_path.write_text(json.dumps({
                "turn-live": {"threadId": "thread-live", "turnId": "turn-live"},
            }), encoding="utf-8")
            try:
                with mock.patch.object(PROXY, "ACTIVE_TURNS_PATH", active_path), \
                     mock.patch.object(PROXY, "RUNTIME_SELECTION_PATH", selection_path), \
                     mock.patch.object(PROXY, "current_exact_nemotron_snapshot", return_value=snapshot):
                    PROXY.RUNTIME_SELECTION.clear()
                    PROXY.RUNTIME_SELECTION.update(saved)
                    PROXY.update_runtime_selection({
                        "threadId": "thread-live",
                        "turnId": "turn-live",
                        "model": exact,
                        "effort": "max",
                    })
                    payload, context = PROXY.runtime_override_for_request({
                        "model": "provider/previous",
                        "messages": [],
                        "reasoning": {"effort": "low"},
                    })
                    self.assertEqual(context["threadId"], "thread-live")
                    self.assertEqual(context["turnId"], "turn-live")
                    self.assertEqual(payload["model"], exact)
                    self.assertEqual(payload["reasoning"]["effort"], "max")
            finally:
                PROXY.RUNTIME_SELECTION.clear()
                PROXY.RUNTIME_SELECTION.update(saved)

    def test_live_selection_uses_unique_matching_thread_amid_other_active_sessions(self):
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            active_path = root / "active-turns.json"
            selection_path = root / "runtime-selection.json"
            active_path.write_text(json.dumps({
                "turn-target": {"threadId": "thread-target", "turnId": "turn-target"},
                "turn-other": {"threadId": "thread-other", "turnId": "turn-other"},
            }), encoding="utf-8")
            try:
                with mock.patch.object(PROXY, "ACTIVE_TURNS_PATH", active_path), \
                     mock.patch.object(PROXY, "RUNTIME_SELECTION_PATH", selection_path):
                    PROXY.RUNTIME_SELECTION.clear()
                    PROXY.RUNTIME_SELECTION.update(saved)
                    PROXY.RUNTIME_SELECTION.update({
                        "generation": 12,
                        "threadId": "thread-target",
                        "turnId": "turn-target",
                        "requestedModel": PROXY.EXACT_NEMOTRON_MODEL,
                        "requestedEffort": "max",
                    })
                    payload, context = PROXY.runtime_override_for_request({
                        "model": "provider/previous",
                        "messages": [{"role": "user", "content": "continue"}],
                    })
                    self.assertEqual(context, {
                        "generation": 12,
                        "threadId": "thread-target",
                        "turnId": "turn-target",
                    })
                    self.assertEqual(payload["model"], PROXY.EXACT_NEMOTRON_MODEL)
                    self.assertEqual(payload["reasoning"]["effort"], "max")
            finally:
                PROXY.RUNTIME_SELECTION.clear()
                PROXY.RUNTIME_SELECTION.update(saved)

    def test_inflight_selection_is_immutable_and_next_request_snapshots_new_generation(self):
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        exact = PROXY.EXACT_NEMOTRON_MODEL
        replacement = "provider/replacement-model"
        snapshot = catalog_snapshot([
            {
                "id": exact,
                "supported_parameters": ["reasoning", "max_tokens", "tools"],
                "reasoning": {"supports_max_tokens": True},
                "pricing": {"prompt": "0.1", "completion": "0.2"},
            },
            {
                "id": replacement,
                "supported_parameters": ["reasoning", "tools"],
                "pricing": {"prompt": "0.1", "completion": "0.2"},
            },
        ])
        active = [{"threadId": "thread-switch", "turnId": "turn-switch"}]
        try:
            with tempfile.TemporaryDirectory() as temporary, \
                 mock.patch.object(PROXY, "RUNTIME_SELECTION_PATH", pathlib.Path(temporary) / "selection.json"), \
                 mock.patch.object(PROXY, "read_active_turns", return_value=active):
                PROXY.RUNTIME_SELECTION.update({
                    "generation": 20,
                    "threadId": "thread-switch",
                    "turnId": "turn-switch",
                    "requestedModel": exact,
                    "requestedEffort": "high",
                    "requestedProvider": "OpenRouter",
                })
                first, first_context = PROXY.runtime_override_for_request({
                    "model": "caller/default", "reasoning": {"effort": "low"},
                    "messages": [{"role": "user", "content": "continue"}],
                })
                first, first_metadata = PROXY.normalize_payload(
                    first, snapshot, locked_selection=True,
                )
                first_metadata.update({
                    "selectionGeneration": first_context["generation"],
                    "threadId": first_context["threadId"],
                    "turnId": first_context["turnId"],
                })
                frozen_first = copy.deepcopy(first)

                PROXY.RUNTIME_SELECTION.update({
                    "generation": 21,
                    "requestedModel": replacement,
                    "requestedEffort": "low",
                    "requestedProvider": "OpenRouter",
                    "verificationStatus": "selected",
                })

                self.assertEqual(first, frozen_first)
                self.assertEqual(first["model"], exact)
                self.assertEqual(first["reasoning"]["effort"], "high")
                self.assertEqual(first_metadata["selectionGeneration"], 20)
                self.assertFalse(PROXY.record_dispatched_runtime_selection(
                    first_metadata, {"provider": "OpenRouter"}, "request-generation-20",
                ))
                self.assertEqual(PROXY.RUNTIME_SELECTION["generation"], 21)
                self.assertEqual(PROXY.RUNTIME_SELECTION["verificationStatus"], "selected")

                second, second_context = PROXY.runtime_override_for_request({
                    "model": "caller/default", "reasoning": {"effort": "medium"},
                    "messages": [{"role": "user", "content": "continue again"}],
                })
                second, second_metadata = PROXY.normalize_payload(
                    second, snapshot, locked_selection=True,
                )
                self.assertEqual(second_context["generation"], 21)
                self.assertEqual(second["model"], replacement)
                self.assertEqual(second["reasoning"]["effort"], "low")
                self.assertEqual(second_metadata["model"], replacement)
        finally:
            PROXY.RUNTIME_SELECTION.clear()
            PROXY.RUNTIME_SELECTION.update(saved)

    def test_locked_selection_preserves_session_transcript_instructions_attachments_and_tool_history(self):
        exact = PROXY.EXACT_NEMOTRON_MODEL
        snapshot = catalog_snapshot([{
            "id": exact,
            "supported_parameters": ["reasoning", "max_tokens", "tools"],
            "reasoning": {"supports_max_tokens": True},
            "pricing": {"prompt": "0.1", "completion": "0.2"},
        }])
        transcript = [
            {"role": "system", "content": "preserve the original instructions"},
            {"role": "user", "content": [{"type": "text", "text": "continue the same task"}]},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-stable",
                    "type": "function",
                    "function": {"name": "read_state", "arguments": "{\"scope\":\"all\"}"},
                }],
            },
            {"role": "tool", "tool_call_id": "call-stable", "content": "state retained"},
        ]
        attachments = [{"label": "requirements.md", "path": "/workspace/requirements.md"}]
        tools = [{
            "type": "function",
            "function": {"name": "read_state", "parameters": {"type": "object"}},
        }]
        original = {
            "model": exact,
            "reasoning": {"effort": "high"},
            "messages": transcript,
            "instructions": "retain every instruction and approval state",
            "attachments": attachments,
            "tools": tools,
            "tool_choice": "required",
            "metadata": {"session": "session-stable", "turn": "turn-stable"},
            "stream": True,
        }
        expected = copy.deepcopy(original)
        normalized, metadata = PROXY.normalize_payload(
            original, snapshot, locked_selection=True,
        )
        self.assertEqual(normalized["messages"], expected["messages"])
        self.assertEqual(normalized["instructions"], expected["instructions"])
        self.assertEqual(normalized["attachments"], expected["attachments"])
        self.assertEqual(normalized["tools"], expected["tools"])
        self.assertEqual(normalized["metadata"], expected["metadata"])
        self.assertEqual(normalized["stream"], expected["stream"])
        self.assertEqual(normalized["tool_choice"], "auto")
        self.assertTrue(metadata["selectionApplied"])
        self.assertEqual(metadata["model"], exact)

    def test_locked_replay_strips_previous_route_pin_fallbacks_and_max_budget(self):
        replacement = "provider/replacement-model"
        snapshot = catalog_snapshot([{
            "id": replacement,
            "supported_parameters": ["reasoning", "tools"],
            "pricing": {"prompt": "0.1", "completion": "0.2"},
        }])
        history = [
            {"role": "assistant", "tool_calls": [{
                "id": "call-replay",
                "type": "function",
                "function": {"name": "read_state", "arguments": "{}"},
            }]},
            {"role": "tool", "tool_call_id": "call-replay", "content": "retained"},
        ]
        normalized, metadata = PROXY.normalize_payload({
            "model": replacement,
            "models": [PROXY.EXACT_NEMOTRON_MODEL],
            "provider": {
                "order": [PROXY.EXACT_NEMOTRON_UPSTREAM_PROVIDER],
                "allow_fallbacks": False,
                "require_parameters": True,
            },
            "reasoning": {"effort": "low", "max_tokens": 128000},
            "messages": history,
            "tools": [{
                "type": "function",
                "function": {"name": "read_state", "parameters": {"type": "object"}},
            }],
        }, snapshot, locked_selection=True)
        self.assertNotIn("provider", normalized)
        self.assertNotIn("models", normalized)
        self.assertEqual(normalized["reasoning"], {"effort": "low"})
        self.assertEqual(normalized["messages"], history)
        self.assertEqual(metadata["model"], replacement)

    def test_locked_exact_selection_has_no_retry_model_or_provider_fallback(self):
        exact = PROXY.EXACT_NEMOTRON_MODEL
        snapshot = catalog_snapshot([{
            "id": exact,
            "supported_parameters": ["reasoning", "max_tokens", "tools"],
            "reasoning": {"supports_max_tokens": True},
            "pricing": {"prompt": "0.1", "completion": "0.2"},
        }])
        snapshot["models"][exact]["exactProviderVerified"] = True
        normalized, metadata = PROXY.normalize_payload({
            "model": exact,
            "reasoning": {"effort": "max"},
            "messages": [{"role": "user", "content": "retain exact routing"}],
            "tools": [{
                "type": "function",
                "function": {"name": "read_state", "parameters": {"type": "object"}},
            }],
        }, snapshot, locked_selection=True)
        immutable = copy.deepcopy(normalized)
        self.assertEqual(metadata["modelCandidates"], [])
        for retry_index in range(PROXY.MAX_UPSTREAM_ATTEMPTS):
            self.assertFalse(PROXY.select_tool_candidate(normalized, metadata, retry_index))
            self.assertEqual(normalized, immutable)
        self.assertEqual(normalized["model"], exact)
        self.assertNotIn("models", normalized)
        self.assertEqual(normalized["reasoning"], {"max_tokens": 128000})
        self.assertEqual(normalized["provider"], {
            "order": [PROXY.EXACT_NEMOTRON_UPSTREAM_PROVIDER],
            "allow_fallbacks": False,
            "require_parameters": True,
        })

    def test_request_audit_keeps_identity_evidence_and_drops_content_headers_and_keys(self):
        handler = object.__new__(PROXY.Handler)
        handler.begin_request_audit()
        handler.update_request_audit(
            requestedProvider="OpenRouter",
            requestedModel=PROXY.EXACT_NEMOTRON_MODEL,
            requestedEffort="max",
            reasoningBudget=128000,
            selectionGeneration=31,
            effectiveGateway="OpenRouter",
            effectiveProvider=PROXY.EXACT_NEMOTRON_UPSTREAM_PROVIDER,
            effectiveModel=PROXY.EXACT_NEMOTRON_MODEL,
            effectiveEffort=None,
            responseId="response-redacted-test",
            messages=[{"role": "user", "content": "SENSITIVE-CONTENT-SENTINEL"}],
            Authorization="Bearer FAKE-AUTHORIZATION-SENTINEL",
            apiKey="FAKE-AUTHORIZATION-SENTINEL",
        )
        with mock.patch.object(PROXY, "audit") as audit_sink:
            handler.finalize_request_audit()
        record = audit_sink.call_args.kwargs
        self.assertEqual(record["requestedProvider"], "OpenRouter")
        self.assertEqual(record["requestedModel"], PROXY.EXACT_NEMOTRON_MODEL)
        self.assertEqual(record["requestedEffort"], "max")
        self.assertEqual(record["reasoningBudget"], 128000)
        self.assertEqual(record["selectionGeneration"], 31)
        self.assertEqual(record["effectiveGateway"], "OpenRouter")
        self.assertEqual(record["effectiveProvider"], PROXY.EXACT_NEMOTRON_UPSTREAM_PROVIDER)
        self.assertEqual(record["effectiveModel"], PROXY.EXACT_NEMOTRON_MODEL)
        self.assertEqual(record["responseId"], "response-redacted-test")
        encoded = json.dumps(record)
        self.assertNotIn("SENSITIVE-CONTENT-SENTINEL", encoded)
        self.assertNotIn("FAKE-AUTHORIZATION-SENTINEL", encoded)
        self.assertNotIn("Authorization", encoded)
        self.assertNotIn("apiKey", encoded)

    def test_all_composer_efforts_are_preserved_exactly(self):
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh"):
            with self.subTest(effort=effort):
                payload, metadata = PROXY.normalize_payload({
                    "model": PROXY.DEFAULT_MODEL,
                    "messages": [],
                    "reasoning": {"effort": effort},
                })
                self.assertEqual(payload["reasoning"]["effort"], effort)
                self.assertEqual(metadata["requestedEffort"], effort)
                self.assertEqual(metadata["transportEffort"], effort)
                self.assertIsNone(metadata["effectiveEffort"])

    def test_effort_alias_is_canonical_and_conflicts_fail_closed(self):
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [],
            "reasoning_effort": "Extra high",
        })
        self.assertEqual(payload["reasoning_effort"], "xhigh")
        self.assertEqual(metadata["requestedEffort"], "Extra high")
        self.assertEqual(metadata["transportEffort"], "xhigh")
        self.assertIsNone(metadata["effectiveEffort"])
        with self.assertRaises(PROXY.InvalidReasoningEffortError):
            PROXY.normalize_payload({
                "model": PROXY.DEFAULT_MODEL,
                "messages": [],
                "reasoning_effort": "low",
                "reasoning": {"effort": "high"},
            })

    def test_hermes_tool_request_routes_to_tool_model(self):
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [],
            "tools": [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        })
        self.assertEqual(payload["model"], PROXY.DEFAULT_TOOL_MODEL)
        self.assertEqual(metadata["requestedModel"], PROXY.DEFAULT_MODEL)
        self.assertEqual(metadata["toolCount"], 1)
        self.assertEqual(metadata["payloadRepairs"], 1)

    def test_capability_verification_requires_a_real_tool_call(self):
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "Give me a verified capability inventory"}],
            "tools": [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        })
        self.assertEqual(payload["tool_choice"], "required")
        self.assertGreaterEqual(metadata["payloadRepairs"], 2)

    def test_capability_verification_allows_final_answer_after_tool_result(self):
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [
                {"role": "user", "content": "Give me a verified capability inventory"},
                {"role": "assistant", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "exec_command", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call-1", "content": "python: /data/data/com.termux/files/usr/bin/python"},
            ],
            "tools": [{"type": "function", "function": {"name": "exec_command", "parameters": {"type": "object"}}}],
            "tool_choice": "required",
        })
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertGreaterEqual(metadata["payloadRepairs"], 2)

    def test_responses_function_output_allows_final_answer(self):
        self.assertTrue(PROXY.payload_has_tool_results({
            "input": [{"type": "function_call_output", "call_id": "call-1", "output": "ok"}],
        }))

    def test_ordinary_tool_request_does_not_force_tool_choice(self):
        payload, _ = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "Explain this code and act only if needed"}],
            "tools": [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        })
        self.assertNotIn("tool_choice", payload)

    def test_explicit_tool_capable_model_is_preserved(self):
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.TOOL_FALLBACK_MODEL,
            "messages": [],
            "tools": [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        })
        self.assertEqual(payload["model"], PROXY.TOOL_FALLBACK_MODEL)
        self.assertEqual(metadata["payloadRepairs"], 0)

    def test_models_payload_is_openai_compatible(self):
        payload = PROXY.models_payload()
        self.assertEqual(payload["object"], "list")
        self.assertTrue(payload["capability_contract"]["applies_to_every_model"])
        self.assertTrue(payload["capability_contract"]["tool_route_preserves_instructions"])
        self.assertTrue(payload["capability_contract"]["english_progress_required"])
        self.assertTrue(payload["capability_contract"]["ordered_progress_required"])
        self.assertTrue(payload["capability_contract"]["progress_metadata_only"])
        self.assertTrue(payload["capability_contract"]["external_content_is_untrusted_data"])
        self.assertTrue(payload["capability_contract"]["authority_bound_to_active_request_and_turn"])
        self.assertEqual(
            payload["capability_contract"]["sha256"],
            PROXY.MODEL_CAPABILITY_CONTRACT_SHA256,
        )
        self.assertTrue(all(
            model["capability_contract_sha256"] == PROXY.MODEL_CAPABILITY_CONTRACT_SHA256
            for model in payload["data"]
        ))
        ids = {model["id"] for model in payload["data"]}
        self.assertIn(PROXY.DEFAULT_MODEL, ids)
        self.assertIn(PROXY.DEFAULT_TOOL_MODEL, ids)
        self.assertIn(PROXY.TOOL_FALLBACK_MODEL, ids)
        self.assertIn(PROXY.AVAILABLE_DOLPHIN_MODEL, ids)
        self.assertFalse(payload["requested_model_status"]["available"])
        self.assertFalse(payload["requested_model_status"]["substituted"])

    def test_exact_nemotron_is_hidden_without_fresh_live_catalog_evidence(self):
        for source in ("static", "stale"):
            snapshot = catalog_snapshot([
                {
                    "id": PROXY.EXACT_NEMOTRON_MODEL,
                    "supported_parameters": ["tools", "reasoning", "max_tokens"],
                    "pricing": {"prompt": "0.1", "completion": "0.2"},
                },
                {
                    "id": PROXY.EXACT_NEMOTRON_FREE_MODEL,
                    "supported_parameters": ["tools", "reasoning", "max_tokens"],
                    "pricing": {"prompt": "0", "completion": "0"},
                },
            ], source=source)
            ids = {entry["id"] for entry in PROXY.models_payload(snapshot)["data"]}
            self.assertNotIn(PROXY.EXACT_NEMOTRON_MODEL, ids)
            self.assertNotIn(PROXY.EXACT_NEMOTRON_FREE_MODEL, ids)

    def test_exact_nemotron_is_exposed_only_from_fresh_live_catalog_evidence(self):
        snapshot = catalog_snapshot([{
            "id": PROXY.EXACT_NEMOTRON_MODEL,
            "supported_parameters": ["tools", "reasoning", "max_tokens"],
            "pricing": {"prompt": "0.0000006", "completion": "0.0000036"},
        }])
        payload = PROXY.models_payload(snapshot)
        ids = {entry["id"] for entry in payload["data"]}
        self.assertIn(PROXY.EXACT_NEMOTRON_MODEL, ids)
        self.assertNotIn(PROXY.EXACT_NEMOTRON_FREE_MODEL, ids)
        self.assertEqual(payload["catalog_source"], "live")

    def test_exact_nemotron_selection_requires_a_fresh_catalog(self):
        live = catalog_snapshot([{
            "id": PROXY.EXACT_NEMOTRON_MODEL,
            "supported_parameters": ["tools", "reasoning", "max_tokens"],
            "pricing": {"prompt": "0.0000006", "completion": "0.0000036"},
        }])
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        with tempfile.TemporaryDirectory() as temporary:
            try:
                with mock.patch.object(PROXY, "RUNTIME_SELECTION_PATH", pathlib.Path(temporary) / "selection.json"), \
                     mock.patch.object(PROXY, "current_exact_nemotron_snapshot", return_value=live) as current:
                    result = PROXY.update_runtime_selection({"model": PROXY.EXACT_NEMOTRON_MODEL})
                self.assertEqual(result["requestedModel"], PROXY.EXACT_NEMOTRON_MODEL)
                current.assert_called_once_with()
                with mock.patch.object(PROXY, "current_exact_nemotron_snapshot", side_effect=PROXY.CatalogUnavailableError("offline")):
                    with self.assertRaises(PROXY.CatalogUnavailableError):
                        PROXY.update_runtime_selection({"model": PROXY.EXACT_NEMOTRON_MODEL})
            finally:
                PROXY.RUNTIME_SELECTION.clear()
                PROXY.RUNTIME_SELECTION.update(saved)

    def test_live_catalog_filters_paid_and_non_tool_models_and_prefers_nemotron_tiers(self):
        snapshot = catalog_snapshot([
            {"id": "vendor/paid-ultra", "supported_parameters": ["tools"], "pricing": {"prompt": "0.1", "completion": "0"}},
            {"id": "vendor/free-text", "supported_parameters": [], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "vendor/free-tool", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-nano:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-super:free", "supported_parameters": ["tools", "tool_choice"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-ultra:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0.0", "completion": "0.000"}},
        ])
        self.assertEqual(PROXY.tool_model_candidates(snapshot), [
            "nvidia/nemotron-ultra:free",
            "nvidia/nemotron-super:free",
            "nvidia/nemotron-nano:free",
            "vendor/free-tool",
        ])

    def test_tool_request_sends_primary_once_and_only_remaining_ordered_fallbacks(self):
        snapshot = catalog_snapshot([
            {"id": "nvidia/nemotron-ultra:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-super:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-nano:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
        ])
        payload, metadata = PROXY.normalize_payload({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [],
            "tools": [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        }, snapshot)
        self.assertEqual(payload["model"], "nvidia/nemotron-ultra:free")
        self.assertEqual(payload["models"], [
            "nvidia/nemotron-super:free",
            "nvidia/nemotron-nano:free",
        ])
        self.assertNotIn(payload["model"], payload["models"])
        self.assertTrue(PROXY.select_tool_candidate(payload, metadata, 1))
        self.assertEqual(payload["model"], "nvidia/nemotron-super:free")
        self.assertEqual(payload["models"], ["nvidia/nemotron-nano:free"])
        self.assertNotIn(payload["model"], payload["models"])

    def test_public_catalog_fetch_is_bounded_and_never_sends_authorization(self):
        captured = []

        def urlopen(request, timeout):
            captured.append((request, timeout))
            return FakeCatalogResponse({"data": [{
                "id": "nvidia/nemotron-ultra:free",
                "supported_parameters": ["tools"],
                "pricing": {"prompt": "0", "completion": "0"},
            }]})

        with mock.patch.object(PROXY.urllib.request, "urlopen", side_effect=urlopen):
            models = PROXY.fetch_public_catalog()
        request, timeout = captured[0]
        self.assertEqual(request.full_url, PROXY.PUBLIC_CATALOG_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(timeout, PROXY.CATALOG_FETCH_TIMEOUT_SECONDS)
        self.assertIn("nvidia/nemotron-ultra:free", models)

    def test_openrouter_key_capability_rejects_zero_remaining_without_exposing_key(self):
        captured = []

        def urlopen(request, timeout):
            captured.append((request, timeout))
            return FakeCatalogResponse({"data": {
                "limit": 0,
                "limit_remaining": 0,
                "usage": 0,
                "is_free_tier": False,
            }})

        with mock.patch.object(PROXY.urllib.request, "urlopen", side_effect=urlopen):
            capability = PROXY.fetch_openrouter_key_capability("private-test-credential")
        request, timeout = captured[0]
        self.assertEqual(request.full_url, PROXY.OPENROUTER_USAGE_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer private-test-credential")
        self.assertEqual(timeout, PROXY.CAPABILITY_FETCH_TIMEOUT_SECONDS)
        self.assertIs(capability["usable"], False)
        self.assertEqual(capability["reason"], "credential_limit_exhausted")
        self.assertNotIn("private-test-credential", repr(capability))

    def test_exact_provider_capability_requires_together_and_required_parameters(self):
        healthy = {"data": {
            "id": PROXY.EXACT_NEMOTRON_MODEL,
            "endpoints": [{
                "model_id": PROXY.EXACT_NEMOTRON_MODEL,
                "provider_name": PROXY.EXACT_NEMOTRON_UPSTREAM_PROVIDER,
                "status": 0,
                "supported_parameters": [
                    "reasoning", "max_tokens", "tools", "tool_choice", "reasoning_effort",
                ],
            }],
        }}
        missing_tools = copy.deepcopy(healthy)
        missing_tools["data"]["endpoints"][0]["supported_parameters"].remove("tools")
        responses = [FakeCatalogResponse(healthy), FakeCatalogResponse(missing_tools)]
        captured = []

        def urlopen(request, timeout):
            captured.append((request, timeout))
            return responses.pop(0)

        with mock.patch.object(PROXY.urllib.request, "urlopen", side_effect=urlopen):
            verified = PROXY.fetch_exact_nemotron_provider_capability()
            rejected = PROXY.fetch_exact_nemotron_provider_capability()
        request, timeout = captured[0]
        self.assertEqual(request.full_url, PROXY.EXACT_NEMOTRON_ENDPOINTS_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(timeout, PROXY.CAPABILITY_FETCH_TIMEOUT_SECONDS)
        self.assertIs(verified["verified"], True)
        self.assertIs(verified["supportsMax"], True)
        self.assertEqual(verified["provider"], "Together")
        self.assertIs(rejected["verified"], False)
        self.assertEqual(rejected["reason"], "provider_capabilities_missing")

    def test_exact_snapshot_is_fail_closed_for_key_and_provider_capability(self):
        snapshot = catalog_snapshot([{
            "id": PROXY.EXACT_NEMOTRON_MODEL,
            "supported_parameters": ["tools", "reasoning", "max_tokens"],
            "reasoning": {"supports_max_tokens": True},
            "pricing": {"prompt": "0.0000006", "completion": "0.0000036"},
        }])
        exhausted = PROXY.gate_exact_nemotron_snapshot(snapshot, {
            "usable": False,
            "providerVerified": True,
            "supportsMax": True,
            "reason": "credential_limit_exhausted",
        })
        self.assertNotIn(PROXY.EXACT_NEMOTRON_MODEL, exhausted["models"])
        self.assertEqual(exhausted["exactNemotronCapability"]["reason"], "credential_limit_exhausted")
        provider_missing = PROXY.gate_exact_nemotron_snapshot(snapshot, {
            "usable": True,
            "providerVerified": False,
            "supportsMax": False,
            "reason": "provider_unavailable",
        })
        self.assertNotIn(PROXY.EXACT_NEMOTRON_MODEL, provider_missing["models"])
        verified = PROXY.gate_exact_nemotron_snapshot(snapshot, {
            "usable": True,
            "providerVerified": True,
            "supportsMax": True,
            "reason": None,
        })
        self.assertIn(PROXY.EXACT_NEMOTRON_MODEL, verified["models"])
        self.assertIs(
            verified["models"][PROXY.EXACT_NEMOTRON_MODEL]["exactProviderVerified"],
            True,
        )

    def test_exact_capability_cache_is_reverified_when_credential_source_changes(self):
        with PROXY.EXACT_CAPABILITY_CONDITION:
            saved_cache = dict(PROXY.EXACT_CAPABILITY_CACHE)
            saved_refreshing = PROXY.EXACT_CAPABILITY_REFRESHING
            PROXY.EXACT_CAPABILITY_CACHE.update({
                "fingerprint": None,
                "checkedAt": 0.0,
                "result": None,
            })
            PROXY.EXACT_CAPABILITY_REFRESHING = False

        def restore():
            with PROXY.EXACT_CAPABILITY_CONDITION:
                PROXY.EXACT_CAPABILITY_CACHE.clear()
                PROXY.EXACT_CAPABILITY_CACHE.update(saved_cache)
                PROXY.EXACT_CAPABILITY_REFRESHING = saved_refreshing
                PROXY.EXACT_CAPABILITY_CONDITION.notify_all()

        self.addCleanup(restore)
        credentials = [
            {"configured": True, "key": "first-private-key", "fingerprint": "source-a"},
            {"configured": True, "key": "first-private-key", "fingerprint": "source-a"},
            {"configured": True, "key": "second-private-key", "fingerprint": "source-b"},
        ]
        with (
            mock.patch.object(PROXY, "credential_state", side_effect=credentials),
            mock.patch.object(PROXY, "fetch_openrouter_key_capability", return_value={
                "usable": True,
                "reason": None,
            }) as key_check,
            mock.patch.object(PROXY, "fetch_exact_nemotron_provider_capability", return_value={
                "verified": True,
                "supportsMax": True,
                "provider": PROXY.EXACT_NEMOTRON_UPSTREAM_PROVIDER,
                "reason": None,
            }) as provider_check,
        ):
            first = PROXY.exact_nemotron_capability()
            cached = PROXY.exact_nemotron_capability()
            changed = PROXY.exact_nemotron_capability()
        self.assertEqual(first, cached)
        self.assertEqual(changed, first)
        self.assertEqual(key_check.call_count, 2)
        self.assertEqual(provider_check.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in key_check.call_args_list],
            ["first-private-key", "second-private-key"],
        )

    def test_catalog_ttl_refreshes_then_uses_stale_and_static_fallbacks(self):
        self.preserve_catalog_state()
        live_models = catalog_snapshot([{
            "id": "nvidia/nemotron-ultra:free",
            "supported_parameters": ["tools"],
            "pricing": {"prompt": "0", "completion": "0"},
        }])["models"]
        calls = []

        def fetch():
            calls.append(time.monotonic())
            if len(calls) == 1:
                return live_models
            raise OSError("offline")

        with PROXY.CATALOG_LOCK:
            PROXY.CATALOG_CACHE.update({"models": {}, "loadedAt": 0.0})
            PROXY.CATALOG_REFRESHING = False
        with mock.patch.object(PROXY, "fetch_public_catalog", side_effect=fetch):
            first_continuity = PROXY.catalog_snapshot(allow_network=True)
            self.wait_catalog_refresh()
            fresh = PROXY.catalog_snapshot(allow_network=True)
            with PROXY.CATALOG_LOCK:
                PROXY.CATALOG_CACHE["loadedAt"] = time.monotonic() - PROXY.CATALOG_TTL_SECONDS - 1
            stale = PROXY.catalog_snapshot(allow_network=True)
            self.wait_catalog_refresh()
            with PROXY.CATALOG_LOCK:
                PROXY.CATALOG_CACHE["loadedAt"] = time.monotonic() - PROXY.CATALOG_MAX_STALE_SECONDS - 1
            static = PROXY.catalog_snapshot(allow_network=True)
            self.wait_catalog_refresh()
        self.assertEqual(first_continuity["source"], "static")
        self.assertEqual(fresh["source"], "live")
        self.assertEqual(stale["source"], "stale")
        self.assertEqual(static["source"], "static")
        self.assertEqual(len(calls), 3)

    def test_tool_requests_require_a_fresh_catalog_instead_of_static_candidates(self):
        self.preserve_catalog_state()
        with PROXY.CATALOG_LOCK:
            PROXY.CATALOG_CACHE.update({"models": {}, "loadedAt": 0.0})
            PROXY.CATALOG_REFRESHING = False
        with mock.patch.object(PROXY, "fetch_public_catalog", side_effect=OSError("offline")):
            with self.assertRaises(PROXY.CatalogUnavailableError):
                PROXY.current_tool_catalog_snapshot()

        rows = {
            "nvidia/nemotron-ultra:free": PROXY.normalize_catalog_entry({
                "id": "nvidia/nemotron-ultra:free",
                "supported_parameters": ["tools"],
                "pricing": {"prompt": "0", "completion": "0"},
            }),
        }
        with PROXY.CATALOG_LOCK:
            PROXY.CATALOG_CACHE.update({"models": {}, "loadedAt": 0.0})
            PROXY.CATALOG_REFRESHING = False
        with mock.patch.object(PROXY, "fetch_public_catalog", return_value=rows):
            snapshot = PROXY.current_tool_catalog_snapshot()
        self.assertEqual(snapshot["source"], "live")
        self.assertEqual(PROXY.tool_model_candidates(snapshot), ["nvidia/nemotron-ultra:free"])

    def test_slow_catalog_refresh_is_immediate_and_single_flight_for_concurrent_callers(self):
        self.preserve_catalog_state()
        stale_models = catalog_snapshot([{
            "id": "nvidia/nemotron-super:free",
            "supported_parameters": ["tools"],
            "pricing": {"prompt": "0", "completion": "0"},
        }])["models"]
        started = threading.Event()
        release = threading.Event()
        fetch_calls = []

        def slow_fetch():
            fetch_calls.append(time.monotonic())
            started.set()
            release.wait(1)
            return stale_models

        with PROXY.CATALOG_LOCK:
            PROXY.CATALOG_CACHE.update({
                "models": stale_models,
                "loadedAt": time.monotonic() - PROXY.CATALOG_TTL_SECONDS - 1,
            })
            PROXY.CATALOG_REFRESHING = False
        with mock.patch.object(PROXY, "fetch_public_catalog", side_effect=slow_fetch):
            initiating_started = time.monotonic()
            initiating_snapshot = PROXY.catalog_snapshot(allow_network=True)
            initiating_elapsed = time.monotonic() - initiating_started
            self.assertTrue(started.wait(1))
            snapshots = []
            durations = []

            def read_snapshot():
                reader_started = time.monotonic()
                snapshots.append(PROXY.catalog_snapshot(allow_network=True))
                durations.append(time.monotonic() - reader_started)

            readers = [threading.Thread(target=read_snapshot) for _ in range(16)]
            for reader in readers:
                reader.start()
            for reader in readers:
                reader.join(0.5)
            release.set()
            self.wait_catalog_refresh()
        self.assertTrue(all(not reader.is_alive() for reader in readers))
        self.assertEqual(len(fetch_calls), 1)
        self.assertEqual(initiating_snapshot["source"], "stale")
        self.assertTrue(all(snapshot["source"] == "stale" for snapshot in snapshots))
        self.assertLess(initiating_elapsed, 0.2)
        self.assertTrue(all(duration < 0.2 for duration in durations))

    def test_live_models_payload_is_authoritative_and_dynamic(self):
        snapshot = catalog_snapshot([
            {"id": PROXY.DEFAULT_MODEL, "supported_parameters": [], "pricing": {"prompt": "1", "completion": "1"}},
            {"id": "nvidia/nemotron-nano:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
        ])
        payload = PROXY.models_payload(snapshot)
        ids = [model["id"] for model in payload["data"]]
        self.assertEqual(ids, [PROXY.DEFAULT_MODEL, "nvidia/nemotron-nano:free"])
        self.assertEqual(payload["catalog_source"], "live")

    def exec_payload(self):
        return {
            "tools": [{
                "type": "function",
                "function": {
                    "name": "exec_command",
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "cmd": {"type": "string"},
                            "login": {"type": "boolean"},
                            "max_output_tokens": {"type": "integer"},
                            "prefix_rule": {"type": "array", "items": {"type": "string"}},
                            "tty": {"type": "boolean"},
                            "yield_time_ms": {"type": "integer"},
                        },
                    },
                },
            }],
        }

    def payload_for_schema(self, schema, name="schema_tool"):
        return {
            "tools": [{
                "type": "function",
                "function": {"name": name, "parameters": schema},
            }],
        }

    def repair_value(self, value, value_schema, name="schema_tool"):
        schema = {
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": value_schema},
        }
        function = {"name": name, "arguments": json.dumps({"value": value})}
        repaired = PROXY.repair_function_arguments(function, self.payload_for_schema(schema, name))
        return repaired, json.loads(function["arguments"])["value"]

    def test_tool_arguments_are_coerced_to_advertised_schema(self):
        function = {
            "name": "exec_command",
            "arguments": json.dumps({
                "cmd": "codex-wifi-scan --refresh",
                "login": "true",
                "max_output_tokens": "10000",
                "prefix_rule": "[]",
                "tty": "false",
                "yield_time_ms": "3000",
                "unexpected": "drop me",
            }),
        }
        repaired = PROXY.repair_function_arguments(function, self.exec_payload())
        arguments = json.loads(function["arguments"])
        self.assertEqual(repaired, 1)
        self.assertIs(arguments["login"], True)
        self.assertIs(arguments["tty"], False)
        self.assertEqual(arguments["max_output_tokens"], 10000)
        self.assertEqual(arguments["yield_time_ms"], 3000)
        self.assertEqual(arguments["prefix_rule"], [])
        self.assertNotIn("unexpected", arguments)

    def test_split_sse_tool_arguments_are_reassembled_then_coerced(self):
        response = "\n\n".join([
            'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"name":"exec_command","arguments":"{\\\"cmd\\\":\\\"iwlist wlan0 scan\\\",\\\"login\\\":\\\"tr"}}]}}]}',
            'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"ue\\\",\\\"max_output_tokens\\\":\\\"10000\\\",\\\"prefix_rule\\\":\\\"[]\\\"}"}}]}}]}',
            "data: [DONE]",
            "",
        ]).encode()
        repaired_body, repaired = PROXY.repair_sse_response(response, self.exec_payload())
        combined = ""
        for line in repaired_body.decode().splitlines():
            if not line.startswith("data: {"):
                continue
            data = json.loads(line[6:])
            for choice in data.get("choices", []):
                for call in choice.get("delta", {}).get("tool_calls", []):
                    combined += call.get("function", {}).get("arguments", "")
        arguments = json.loads(combined)
        self.assertEqual(repaired, 1)
        self.assertIs(arguments["login"], True)
        self.assertEqual(arguments["max_output_tokens"], 10000)
        self.assertEqual(arguments["prefix_rule"], [])
        self.assertTrue(repaired_body.endswith(b"data: [DONE]\n\n"))

    def test_exec_command_integral_floats_are_repaired_for_codex(self):
        function = {
            "name": "exec_command",
            "arguments": json.dumps({
                "cmd": "powershell -Command Get-PSDrive",
                "max_output_tokens": 10000.0,
                "yield_time_ms": 10000.0,
            }),
        }
        repaired = PROXY.repair_function_arguments(function, self.exec_payload())
        arguments = json.loads(function["arguments"])
        self.assertEqual(repaired, 1)
        self.assertEqual(arguments["max_output_tokens"], 10000)
        self.assertEqual(arguments["yield_time_ms"], 10000)
        self.assertIsInstance(arguments["max_output_tokens"], int)
        self.assertIsInstance(arguments["yield_time_ms"], int)

    def test_integral_float_coercion_only_when_schema_exclusively_requires_integer(self):
        repaired, integer_value = self.repair_value(10000.0, {"type": "integer"})
        self.assertEqual(repaired, 1)
        self.assertEqual(integer_value, 10000)
        self.assertIsInstance(integer_value, int)

        repaired, nullable_integer = self.repair_value(10000.0, {"type": ["integer", "null"]})
        self.assertEqual(repaired, 1)
        self.assertIsInstance(nullable_integer, int)

        repaired, exact_string_integer = self.repair_value("9007199254740993.0", {"type": "integer"})
        self.assertEqual(repaired, 1)
        self.assertEqual(exact_string_integer, 9007199254740993)
        self.assertIsInstance(exact_string_integer, int)

        repaired, union_value = self.repair_value(10000.0, {"type": ["integer", "number"]})
        self.assertEqual(repaired, 0)
        self.assertEqual(union_value, 10000.0)
        self.assertIsInstance(union_value, float)

    def test_number_schema_preserves_integral_and_fractional_floats(self):
        for value in (10000.0, 1.25):
            with self.subTest(value=value):
                repaired, result = self.repair_value(value, {"type": "number"})
                self.assertEqual(repaired, 0)
                self.assertEqual(result, value)
                self.assertIsInstance(result, float)

    def test_absent_schema_and_unknown_property_never_trigger_name_based_coercion(self):
        original = json.dumps({"yield_time_ms": 10000.0})
        function = {"name": "exec_command", "arguments": original}
        self.assertEqual(PROXY.repair_function_arguments(function, {}), 0)
        self.assertEqual(function["arguments"], original)
        self.assertIsInstance(json.loads(function["arguments"])["yield_time_ms"], float)

        schema = {"type": "object", "properties": {}, "additionalProperties": True}
        function = {"name": "exec_command", "arguments": original}
        self.assertEqual(PROXY.repair_function_arguments(function, self.payload_for_schema(schema, "exec_command")), 0)
        self.assertIsInstance(json.loads(function["arguments"])["yield_time_ms"], float)

    def test_nested_integer_values_are_repaired_and_additional_property_schema_is_honored(self):
        schema = {
            "type": "object",
            "required": ["nested", "values"],
            "properties": {
                "nested": {
                    "type": "object",
                    "required": ["count"],
                    "properties": {"count": {"type": "integer"}},
                    "additionalProperties": {"type": "integer"},
                },
                "values": {"type": "array", "items": {"type": "integer"}},
            },
            "additionalProperties": False,
        }
        function = {
            "name": "schema_tool",
            "arguments": json.dumps({
                "nested": {"count": 3.0, "extra": "4.0"},
                "values": [1.0, "2"],
            }),
        }
        self.assertEqual(PROXY.repair_function_arguments(function, self.payload_for_schema(schema)), 1)
        arguments = json.loads(function["arguments"])
        self.assertEqual(arguments, {"nested": {"count": 3, "extra": 4}, "values": [1, 2]})
        self.assertIsInstance(arguments["nested"]["count"], int)

    def test_malformed_arguments_raise_sanitized_error_without_mutation(self):
        original = '{"sensitive-marker":'
        function = {"name": "schema_tool", "arguments": original}
        with self.assertRaises(PROXY.ToolArgumentValidationError) as raised:
            PROXY.repair_function_arguments(function, self.payload_for_schema({"type": "object"}))
        self.assertEqual(function["arguments"], original)
        self.assertNotIn("sensitive-marker", str(raised.exception))
        self.assertNotEqual(function["arguments"], "{}")

    def test_malformed_fragmented_sse_arguments_raise_without_empty_object_substitution(self):
        response = "\n\n".join([
            'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"name":"schema_tool","arguments":"{\\\"count\\\":"}}]}}]}',
            "data: [DONE]",
            "",
        ]).encode()
        with self.assertRaises(PROXY.ToolArgumentValidationError):
            PROXY.repair_sse_response(response, self.payload_for_schema({"type": "object"}))
        self.assertNotIn(b'"arguments":"{}"', response)

    def test_post_repair_validation_rejects_invalid_arguments_without_mutation(self):
        cases = [
            ({"type": "integer"}, 1.25),
            ({"type": "integer"}, True),
            ({"type": "object"}, []),
            ({"type": "object", "required": ["required_value"]}, {}),
            ({"type": "string", "enum": ["allowed"]}, "denied"),
            ({"type": "number", "minimum": 2, "exclusiveMaximum": 5}, 1.5),
            ({"type": "number", "minimum": 2, "exclusiveMaximum": 5}, 5),
        ]
        for value_schema, value in cases:
            with self.subTest(schema=value_schema, value_type=type(value).__name__):
                schema = {
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": value_schema},
                    "additionalProperties": False,
                }
                original = json.dumps({"value": value})
                function = {"name": "schema_tool", "arguments": original}
                with self.assertRaises(PROXY.ToolArgumentValidationError):
                    PROXY.repair_function_arguments(function, self.payload_for_schema(schema))
                self.assertEqual(function["arguments"], original)

        root_original = json.dumps(["not", "an", "object"])
        root_function = {"name": "schema_tool", "arguments": root_original}
        with self.assertRaises(PROXY.ToolArgumentValidationError):
            PROXY.repair_function_arguments(root_function, self.payload_for_schema({"type": "object"}))
        self.assertEqual(root_function["arguments"], root_original)

    def test_schema_combinators_sizes_patterns_const_and_array_limits(self):
        schema = {
            "type": "object",
            "required": ["tag", "mode", "values", "constant"],
            "properties": {
                "tag": {"type": "string", "minLength": 3, "maxLength": 8, "pattern": "^[a-z]+$"},
                "mode": {"anyOf": [{"const": "safe"}, {"const": "guarded"}]},
                "values": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "number"}},
                "constant": {"allOf": [{"type": "integer"}, {"minimum": 1, "maximum": 3}]},
                "choice": {"oneOf": [{"type": "string"}, {"type": "null"}]},
            },
            "additionalProperties": False,
        }
        function = {
            "name": "schema_tool",
            "arguments": json.dumps({"tag": "valid", "mode": "safe", "values": [1.25], "constant": 2, "choice": None}),
        }
        self.assertEqual(PROXY.repair_function_arguments(function, self.payload_for_schema(schema)), 0)

        invalid = {"name": "schema_tool", "arguments": json.dumps({
            "tag": "NO", "mode": "unsafe", "values": [], "constant": 4, "choice": None,
        })}
        with self.assertRaises(PROXY.ToolArgumentValidationError):
            PROXY.repair_function_arguments(invalid, self.payload_for_schema(schema))

    def test_nullable_anyof_repairs_integral_tool_arguments(self):
        repaired, value = self.repair_value("10000.0", {
            "anyOf": [{"type": "integer"}, {"type": "null"}],
        })
        self.assertEqual(repaired, 1)
        self.assertEqual(value, 10000)
        self.assertIsInstance(value, int)

    def test_nested_local_refs_repair_and_validate_recursively(self):
        schema = {
            "$defs": {
                "count": {"type": "integer"},
                "node": {
                    "type": "object",
                    "required": ["count", "next"],
                    "additionalProperties": False,
                    "properties": {
                        "count": {"$ref": "#/$defs/count"},
                        "next": {"anyOf": [{"$ref": "#/$defs/node"}, {"type": "null"}]},
                    },
                },
            },
            "$ref": "#/$defs/node",
        }
        function = {
            "name": "schema_tool",
            "arguments": json.dumps({"count": "1", "next": {"count": 2.0, "next": None}}),
        }
        self.assertEqual(PROXY.repair_function_arguments(function, self.payload_for_schema(schema)), 1)
        self.assertEqual(json.loads(function["arguments"]), {
            "count": 1,
            "next": {"count": 2, "next": None},
        })

    def test_schema_ref_cycles_and_excessive_depth_fail_closed(self):
        cyclic = {"$ref": "#"}
        function = {"name": "schema_tool", "arguments": "{}"}
        with self.assertRaises(PROXY.ToolArgumentValidationError):
            PROXY.repair_function_arguments(function, self.payload_for_schema(cyclic))

        deep = {"$defs": {}, "$ref": "#/$defs/n0"}
        for index in range(PROXY.SCHEMA_MAX_DEPTH + 2):
            deep["$defs"][f"n{index}"] = (
                {"type": "integer"}
                if index == PROXY.SCHEMA_MAX_DEPTH + 1
                else {"$ref": f"#/$defs/n{index + 1}"}
            )
        function = {"name": "schema_tool", "arguments": '"1"'}
        with self.assertRaises(PROXY.ToolArgumentValidationError):
            PROXY.repair_function_arguments(function, self.payload_for_schema(deep))

    def test_private_credential_rotates_without_restart_and_fingerprint_never_hashes_key(self):
        with tempfile.TemporaryDirectory(prefix="nemotron-credential-") as directory:
            home = pathlib.Path(directory)
            credential = home / "openrouter.env"
            credential.write_text("OPENROUTER_API_KEY=test-rotation-alpha\n", encoding="utf-8")
            credential.chmod(0o600)
            with mock.patch.object(PROXY, "CODEX_HOME", home):
                first = PROXY.credential_state()
                credential.write_text("OPENROUTER_API_KEY=test-rotation-beta-longer\n", encoding="utf-8")
                credential.chmod(0o600)
                second = PROXY.credential_state()
        self.assertEqual(first["key"], "test-rotation-alpha")
        self.assertEqual(second["key"], "test-rotation-beta-longer")
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotIn(first["key"], first["fingerprint"])
        self.assertNotIn(second["key"], second["fingerprint"])

    def test_invalid_private_credential_fails_closed_without_env_or_broker_fallback(self):
        with tempfile.TemporaryDirectory(prefix="nemotron-credential-") as directory:
            home = pathlib.Path(directory)
            (home / "vault").mkdir()
            credential = home / "openrouter.env"
            credential.write_text("OPENROUTER_API_KEY=test-private-key\n", encoding="utf-8")
            credential.chmod(0o644)
            broker = home / "vault" / "broker.json"
            broker.write_text(json.dumps({"host": "127.0.0.1", "port": 12345, "token": "test-token"}), encoding="utf-8")
            broker.chmod(0o600)
            with mock.patch.object(PROXY, "CODEX_HOME", home), \
                 mock.patch.dict(PROXY.os.environ, {"OPENROUTER_API_KEY": "test-env-key"}), \
                 mock.patch.object(PROXY.socket, "create_connection", side_effect=AssertionError("broker must not be called")):
                state = PROXY.credential_state()
        self.assertIsNone(state["key"])
        self.assertIs(state["configured"], False)

    def test_private_credential_symlink_is_rejected_without_reading_target(self):
        with tempfile.TemporaryDirectory(prefix="nemotron-credential-") as directory:
            home = pathlib.Path(directory)
            target = home / "not-the-credential-source"
            target.write_text("OPENROUTER_API_KEY=test-symlink-target\n", encoding="utf-8")
            target.chmod(0o600)
            (home / "openrouter.env").symlink_to(target)
            with mock.patch.object(PROXY, "CODEX_HOME", home), \
                 mock.patch.object(PROXY.os, "read", side_effect=AssertionError("symlink target must not be read")):
                state = PROXY.credential_state()
        self.assertIsNone(state["key"])
        self.assertIs(state["configured"], False)

    def test_private_credential_path_swap_uses_the_already_open_descriptor(self):
        with tempfile.TemporaryDirectory(prefix="nemotron-credential-") as directory:
            home = pathlib.Path(directory)
            credential = home / "openrouter.env"
            retained = home / "retained-open-file"
            replacement = home / "replacement"
            credential.write_text("OPENROUTER_API_KEY=test-open-descriptor\n", encoding="utf-8")
            credential.chmod(0o600)
            descriptor = os.open(credential, os.O_RDONLY)
            credential.rename(retained)
            replacement.write_text("OPENROUTER_API_KEY=test-replacement\n", encoding="utf-8")
            replacement.chmod(0o600)
            credential.symlink_to(replacement)
            try:
                with mock.patch.object(PROXY, "CODEX_HOME", home), \
                     mock.patch.object(PROXY.os, "open", return_value=os.dup(descriptor)):
                    source = PROXY.private_env_credential()
            finally:
                os.close(descriptor)
        self.assertEqual(source["key"], "test-open-descriptor")
        self.assertNotEqual(source["key"], "test-replacement")

    def test_secure_empty_private_file_intentionally_uses_valid_loopback_broker(self):
        class Reader:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def readline(self, _limit):
                return b'{"ok":true,"value":"test-broker-key"}\n'

        class Client:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def sendall(self, value):
                self.sent = value

            def makefile(self, _mode):
                return Reader()

        with tempfile.TemporaryDirectory(prefix="nemotron-credential-") as directory:
            home = pathlib.Path(directory)
            (home / "vault").mkdir()
            credential = home / "openrouter.env"
            credential.write_text("# configured through the private loopback broker\n", encoding="utf-8")
            credential.chmod(0o600)
            broker = home / "vault" / "broker.json"
            broker.write_text(json.dumps({"host": "127.0.0.1", "port": 12345, "token": "test-token"}), encoding="utf-8")
            broker.chmod(0o600)
            client = Client()
            with mock.patch.object(PROXY, "CODEX_HOME", home), \
                 mock.patch.object(PROXY.socket, "create_connection", return_value=client) as connection:
                state = PROXY.credential_state()
        connection.assert_called_once_with(("127.0.0.1", 12345), timeout=4)
        self.assertEqual(state["key"], "test-broker-key")
        self.assertIs(state["configured"], True)

    def test_broker_rejects_non_loopback_host_before_connecting(self):
        with tempfile.TemporaryDirectory(prefix="nemotron-credential-") as directory:
            home = pathlib.Path(directory)
            (home / "vault").mkdir()
            broker = home / "vault" / "broker.json"
            broker.write_text(json.dumps({"host": "example.com", "port": 443, "token": "test-token"}), encoding="utf-8")
            broker.chmod(0o600)
            with mock.patch.object(PROXY, "CODEX_HOME", home), \
                 mock.patch.dict(PROXY.os.environ, {"OPENROUTER_API_KEY": ""}), \
                 mock.patch.object(PROXY.socket, "create_connection", side_effect=AssertionError("non-loopback broker")):
                state = PROXY.credential_state()
        self.assertIsNone(state["key"])
        self.assertIs(state["configured"], False)

    def test_broker_symlink_is_rejected_without_reading_or_connecting(self):
        with tempfile.TemporaryDirectory(prefix="nemotron-credential-") as directory:
            home = pathlib.Path(directory)
            vault = home / "vault"
            vault.mkdir()
            target = home / "not-the-broker-source"
            target.write_text(json.dumps({"host": "127.0.0.1", "port": 12345, "token": "test-token"}), encoding="utf-8")
            target.chmod(0o600)
            (vault / "broker.json").symlink_to(target)
            with mock.patch.object(PROXY, "CODEX_HOME", home), \
                 mock.patch.object(PROXY.os, "read", side_effect=AssertionError("broker symlink must not be read")), \
                 mock.patch.object(PROXY.socket, "create_connection", side_effect=AssertionError("broker must not connect")):
                broker = PROXY.private_broker_config()
        self.assertIs(broker["exists"], True)
        self.assertIs(broker["valid"], False)

    def test_sse_requires_an_explicit_terminal_event(self):
        complete = b'data: {"choices":[]}\r\n\r\ndata: [DONE]\r\n\r\n'
        truncated = b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        self.assertTrue(PROXY.sse_has_terminal_event(complete))
        self.assertFalse(PROXY.sse_has_terminal_event(truncated))
        self.assertFalse(PROXY.sse_has_terminal_event(b""))
        self.assertFalse(PROXY.sse_has_terminal_event(b"data: [DONE]\n\ndata: {\"late\":true}\n\n"))
        self.assertFalse(PROXY.sse_has_terminal_event(b"data: [DONE]\n\n: late-comment\n\n"))

    def test_strict_sse_rejects_malformed_json_error_events_and_data_after_done(self):
        malformed = b"data: {not-json}\n\ndata: [DONE]\n\n"
        error_event = b'event: error\ndata: {"message":"provider failure"}\n\ndata: [DONE]\n\n'
        after_done = b'data: [DONE]\n\ndata: {"choices":[]}\n\n'
        for body in (malformed, error_event, after_done):
            with self.subTest(body=body[:20]):
                with self.assertRaises(PROXY.UpstreamResponseValidationError):
                    PROXY.parse_sse_events(body)

    def test_effective_model_is_extracted_from_json_and_last_sse_event(self):
        json_body = b'{"id":"response-json","model":"provider/json-model","provider":"Together","choices":[],"usage":{"completion_tokens_details":{"reasoning_tokens":16}}}'
        sse_body = (
            b'data: {"model":"provider/first","choices":[]}\n\n'
            b'data: {"model":"provider/final","choices":[]}\n\n'
            b'data: [DONE]\n\n'
        )
        self.assertEqual(PROXY.response_effective_model(json_body, "application/json"), "provider/json-model")
        self.assertEqual(PROXY.response_effective_model(sse_body, "text/event-stream"), "provider/final")
        evidence = PROXY.response_runtime_evidence(json_body, "application/json")
        self.assertEqual(evidence["provider"], "Together")
        self.assertEqual(evidence["responseId"], "response-json")
        self.assertEqual(evidence["reasoningTokens"], 16)
        self.assertIsNone(evidence["effort"])

    def test_runtime_identity_is_dispatched_then_provider_confirmed_without_inferred_effort(self):
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        with tempfile.TemporaryDirectory() as temporary:
            try:
                with mock.patch.object(PROXY, "RUNTIME_SELECTION_PATH", pathlib.Path(temporary) / "selection.json"), \
                     mock.patch.object(PROXY, "read_active_turns", return_value=[]):
                    PROXY.RUNTIME_SELECTION.clear()
                    PROXY.RUNTIME_SELECTION.update(saved)
                    PROXY.RUNTIME_SELECTION.update({
                        "generation": 7,
                        "turns": {},
                        "requestedProvider": "OpenRouter",
                        "requestedModel": PROXY.EXACT_NEMOTRON_MODEL,
                        "requestedEffort": "max",
                        "threadId": "thread-7",
                        "turnId": "turn-7",
                        "effectiveProvider": "EarlierProvider",
                        "effectiveModel": "provider/earlier",
                        "effectiveEffort": "low",
                        "confirmedGeneration": 6,
                    })
                    metadata = {
                        "selectionApplied": True,
                        "selectionGeneration": 7,
                        "requestedModel": PROXY.EXACT_NEMOTRON_MODEL,
                        "transportEffort": "max",
                        "reasoningBudget": 128000,
                        "model": PROXY.EXACT_NEMOTRON_MODEL,
                        "threadId": "thread-7",
                        "turnId": "turn-7",
                    }
                    self.assertTrue(PROXY.record_dispatched_runtime_selection(
                        metadata, {"provider": "OpenRouter"}, "request-7"
                    ))
                    dispatched = PROXY.runtime_selection_payload()
                    self.assertEqual(dispatched["verificationStatus"], "dispatched")
                    self.assertEqual(dispatched["effectiveProvider"], "EarlierProvider")
                    self.assertFalse(dispatched["identityVerified"])
                    evidence = {
                        "model": PROXY.EXACT_NEMOTRON_MODEL,
                        "provider": "Together",
                        "effort": None,
                        "reasoningBudget": None,
                        "reasoningTokens": 16,
                        "responseId": "response-7",
                    }
                    self.assertTrue(PROXY.record_confirmed_runtime_selection(
                        metadata, {"provider": "OpenRouter"}, "request-7", evidence
                    ))
                    confirmed = PROXY.runtime_selection_payload()
                    self.assertEqual(confirmed["verificationStatus"], "confirmed")
                    self.assertEqual(confirmed["effectiveGateway"], "OpenRouter")
                    self.assertEqual(confirmed["effectiveProvider"], "Together")
                    self.assertEqual(confirmed["effectiveModel"], PROXY.EXACT_NEMOTRON_MODEL)
                    self.assertIsNone(confirmed["effectiveEffort"])
                    self.assertEqual(confirmed["effectiveReasoningTokens"], 16)
                    self.assertEqual(confirmed["requestedReasoningBudget"], 128000)
                    self.assertTrue(confirmed["identityVerified"])
                    self.assertFalse(confirmed["effortVerified"])
                    self.assertFalse(confirmed["verified"])
                    self.assertEqual(confirmed["trackedTurnCount"], 1)
                    self.assertEqual(confirmed["currentTurn"]["verificationStatus"], "confirmed")
                    self.assertEqual(confirmed["currentTurn"]["requestedEffort"], "max")
                    self.assertEqual(confirmed["currentTurn"]["effectiveProvider"], "Together")
                    self.assertIsNone(confirmed["currentTurn"]["effectiveEffort"])
                    persisted = json.loads(PROXY.RUNTIME_SELECTION_PATH.read_text(encoding="utf-8"))
                    turn_key = PROXY.runtime_turn_key("thread-7", "turn-7")
                    self.assertEqual(persisted["turns"][turn_key]["responseId"], "response-7")
            finally:
                PROXY.RUNTIME_SELECTION.clear()
                PROXY.RUNTIME_SELECTION.update(saved)

    def test_runtime_turn_ledger_is_bounded_and_deterministically_keyed(self):
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        try:
            PROXY.RUNTIME_SELECTION["turns"] = {}
            for index in range(PROXY.MAX_RUNTIME_TURNS + 6):
                PROXY.update_runtime_turn(
                    f"thread-{index}", f"turn-{index}", generation=index,
                    verificationStatus="confirmed", effectiveModel=f"model/{index}",
                )
            turns = PROXY.RUNTIME_SELECTION["turns"]
            self.assertEqual(len(turns), PROXY.MAX_RUNTIME_TURNS)
            self.assertNotIn(PROXY.runtime_turn_key("thread-0", "turn-0"), turns)
            newest = turns[PROXY.runtime_turn_key("thread-69", "turn-69")]
            self.assertEqual(newest["effectiveModel"], "model/69")
        finally:
            PROXY.RUNTIME_SELECTION.clear()
            PROXY.RUNTIME_SELECTION.update(saved)

    def test_runtime_status_before_first_request_restore_and_new_switch(self):
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        with tempfile.TemporaryDirectory() as temporary:
            selection_path = pathlib.Path(temporary) / "selection.json"
            try:
                with mock.patch.object(PROXY, "RUNTIME_SELECTION_PATH", selection_path), \
                     mock.patch.object(PROXY, "read_active_turns", return_value=[]):
                    blank = {
                        key: (0 if key == "generation" else False if key == "modelSubstitution" else {} if key == "turns" else None)
                        for key in PROXY.RUNTIME_SELECTION
                    }
                    blank["verificationStatus"] = "unverified"
                    PROXY.RUNTIME_SELECTION.clear()
                    PROXY.RUNTIME_SELECTION.update(blank)
                    initial = PROXY.runtime_selection_payload()
                    self.assertEqual(initial["verificationStatus"], "unverified")
                    self.assertFalse(initial["identityVerified"])
                    self.assertFalse(initial["effortVerified"])
                    self.assertIsNone(initial["currentTurn"])

                    PROXY.RUNTIME_SELECTION.update({
                        "generation": 4,
                        "verificationStatus": "confirmed",
                        "requestedProvider": "OpenRouter",
                        "requestedModel": PROXY.EXACT_NEMOTRON_MODEL,
                        "requestedEffort": "high",
                        "effectiveGateway": "OpenRouter",
                        "effectiveProvider": "Together",
                        "effectiveModel": PROXY.EXACT_NEMOTRON_MODEL,
                        "effectiveEffort": None,
                        "threadId": "thread-restore",
                        "turnId": "turn-restore",
                        "confirmedGeneration": 4,
                    })
                    PROXY.update_runtime_turn(
                        "thread-restore", "turn-restore", generation=4,
                        verificationStatus="confirmed", requestedProvider="OpenRouter",
                        requestedModel=PROXY.EXACT_NEMOTRON_MODEL, requestedEffort="high",
                        effectiveProvider="Together", effectiveModel=PROXY.EXACT_NEMOTRON_MODEL,
                        effectiveEffort=None,
                    )
                    PROXY.persist_runtime_selection()
                    PROXY.RUNTIME_SELECTION.clear()
                    PROXY.RUNTIME_SELECTION.update(blank)
                    PROXY.load_runtime_selection()
                    restored = PROXY.runtime_selection_payload()
                    self.assertEqual(restored["verificationStatus"], "confirmed")
                    self.assertTrue(restored["identityVerified"])
                    self.assertFalse(restored["effortVerified"])
                    self.assertEqual(restored["currentTurn"]["effectiveProvider"], "Together")

                    live = catalog_snapshot([{
                        "id": PROXY.EXACT_NEMOTRON_MODEL,
                        "supported_parameters": ["reasoning", "max_tokens", "tools"],
                        "reasoning": {"supports_max_tokens": True},
                        "pricing": {"prompt": "0.0000006", "completion": "0.0000036"},
                    }])
                    live["models"][PROXY.EXACT_NEMOTRON_MODEL]["exactProviderVerified"] = True
                    with mock.patch.object(PROXY, "current_exact_nemotron_snapshot", return_value=live):
                        switched = PROXY.update_runtime_selection({
                            "threadId": "thread-restore", "turnId": "turn-restore",
                            "model": PROXY.EXACT_NEMOTRON_MODEL, "effort": "max",
                        })
                    self.assertEqual(switched["verificationStatus"], "selected")
                    self.assertEqual(switched["requestedEffort"], "max")
                    self.assertEqual(switched["requestedReasoningBudget"], 128000)
                    self.assertFalse(switched["identityVerified"])
                    self.assertFalse(switched["effortVerified"])
                    self.assertEqual(switched["currentTurn"]["verificationStatus"], "selected")
            finally:
                PROXY.RUNTIME_SELECTION.clear()
                PROXY.RUNTIME_SELECTION.update(saved)

    def test_failed_or_stale_request_never_overwrites_last_confirmed_identity(self):
        saved = copy.deepcopy(PROXY.RUNTIME_SELECTION)
        with tempfile.TemporaryDirectory() as temporary:
            try:
                with mock.patch.object(PROXY, "RUNTIME_SELECTION_PATH", pathlib.Path(temporary) / "selection.json"):
                    PROXY.RUNTIME_SELECTION.clear()
                    PROXY.RUNTIME_SELECTION.update(saved)
                    PROXY.RUNTIME_SELECTION.update({
                        "generation": 9,
                        "effectiveProvider": "Together",
                        "effectiveModel": PROXY.EXACT_NEMOTRON_MODEL,
                        "effectiveEffort": None,
                        "confirmedGeneration": 8,
                    })
                    current = {
                        "selectionApplied": True,
                        "selectionGeneration": 9,
                        "requestedModel": PROXY.EXACT_NEMOTRON_MODEL,
                        "transportEffort": "max",
                        "reasoningBudget": 128000,
                        "model": PROXY.EXACT_NEMOTRON_MODEL,
                    }
                    PROXY.record_dispatched_runtime_selection(current, {"provider": "OpenRouter"}, "request-9")
                    self.assertTrue(PROXY.record_runtime_failure("request-9", "timeout_error"))
                    self.assertEqual(PROXY.RUNTIME_SELECTION["verificationStatus"], "failed")
                    self.assertEqual(PROXY.RUNTIME_SELECTION["effectiveProvider"], "Together")
                    self.assertEqual(PROXY.RUNTIME_SELECTION["effectiveModel"], PROXY.EXACT_NEMOTRON_MODEL)
                    stale = dict(current, selectionGeneration=8)
                    self.assertFalse(PROXY.record_confirmed_runtime_selection(
                        stale, {"provider": "OpenRouter"}, "request-8",
                        {"model": "provider/stale", "provider": "Stale", "effort": "low", "reasoningBudget": None, "reasoningTokens": 1, "responseId": "stale"},
                    ))
                    self.assertEqual(PROXY.RUNTIME_SELECTION["effectiveProvider"], "Together")
            finally:
                PROXY.RUNTIME_SELECTION.clear()
                PROXY.RUNTIME_SELECTION.update(saved)

    def test_response_requires_renderable_text_or_tool_call(self):
        empty_json = b'{"choices":[{"message":{"role":"assistant","content":null,"reasoning":"private"},"finish_reason":"stop"}],"usage":{"completion_tokens":17}}'
        text_json = b'{"choices":[{"message":{"role":"assistant","content":"ready"}}]}'
        tool_json = b'{"choices":[{"message":{"role":"assistant","content":null,"tool_calls":[{"id":"call-1","type":"function","function":{"name":"exec_command","arguments":"{}"}}]}}]}'
        empty_sse = (
            b'data: {"choices":[{"index":0,"delta":{"reasoning":"private"}}]}\n\n'
            b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
            b'data: [DONE]\n\n'
        )
        text_sse = (
            b'data: {"choices":[{"index":0,"delta":{"content":"ready"}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        tool_sse = (
            b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"name":"exec_command","arguments":"{}"}}]}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        self.assertFalse(PROXY.response_has_renderable_output(empty_json, "application/json"))
        self.assertTrue(PROXY.response_has_renderable_output(text_json, "application/json"))
        self.assertTrue(PROXY.response_has_renderable_output(tool_json, "application/json"))
        self.assertFalse(PROXY.response_has_renderable_output(empty_sse, "text/event-stream"))
        self.assertTrue(PROXY.response_has_renderable_output(text_sse, "text/event-stream"))
        self.assertTrue(PROXY.response_has_renderable_output(tool_sse, "text/event-stream"))

    def test_exact_pseudo_tool_envelope_becomes_advertised_tool_call(self):
        payload = self.exec_payload()
        body = json.dumps({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": '<execute>\n{"name":"exec_command","arguments":{"cmd":"command -v python","yield_time_ms":1000.0}}\nexecute>',
                },
                "finish_reason": "stop",
            }]
        }).encode()
        repaired_body, repaired = PROXY.repair_json_response(body, payload)
        choice = json.loads(repaired_body)["choices"][0]
        function = choice["message"]["tool_calls"][0]["function"]
        self.assertGreaterEqual(repaired, 1)
        self.assertIsNone(choice["message"]["content"])
        self.assertEqual(choice["finish_reason"], "tool_calls")
        self.assertEqual(function["name"], "exec_command")
        self.assertEqual(json.loads(function["arguments"])["yield_time_ms"], 1000)

    def test_split_sse_pseudo_tool_envelope_becomes_tool_delta(self):
        body = (
            b'data: {"choices":[{"index":0,"delta":{"content":"<execute>\\n{\\\"name\\\":\\\"exec_command\\\",\\\"arguments\\\":{"}}]}'
            b'\n\ndata: {"choices":[{"index":0,"delta":{"content":"\\\"cmd\\\":\\\"command -v python\\\"}}\\nexecute>"},"finish_reason":"stop"}]}'
            b'\n\ndata: [DONE]\n\n'
        )
        repaired_body, repaired = PROXY.repair_sse_response(body, self.exec_payload())
        events = PROXY.parse_sse_events(repaired_body)
        deltas = [choice["delta"] for event in events if event["kind"] == "data" for choice in event["data"]["choices"]]
        calls = [call for delta in deltas for call in delta.get("tool_calls", [])]
        self.assertGreaterEqual(repaired, 1)
        self.assertEqual(calls[0]["function"]["name"], "exec_command")
        self.assertNotIn("<execute>", repaired_body.decode())

    def test_hermes_function_markup_becomes_advertised_tool_call(self):
        markup = """<function=exec_command>
<parameter=cmd>
codex-gallery semantic --query woman --limit 1
</parameter>
</function>
</tool_call>"""
        body = json.dumps({
            "choices": [{
                "message": {"role": "assistant", "content": markup},
                "finish_reason": "stop",
            }]
        }).encode()
        repaired_body, repaired = PROXY.repair_json_response(body, self.exec_payload())
        choice = json.loads(repaired_body)["choices"][0]
        function = choice["message"]["tool_calls"][0]["function"]
        self.assertGreaterEqual(repaired, 1)
        self.assertIsNone(choice["message"]["content"])
        self.assertEqual(choice["finish_reason"], "tool_calls")
        self.assertEqual(function["name"], "exec_command")
        self.assertEqual(
            json.loads(function["arguments"])["cmd"],
            "codex-gallery semantic --query woman --limit 1",
        )

    def test_split_sse_hermes_function_markup_becomes_tool_delta(self):
        body = (
            b'data: {"choices":[{"index":0,"delta":{"content":"<function=exec_command>\\n<parameter=cmd>\\n"}}]}\n\n'
            b'data: {"choices":[{"index":0,"delta":{"content":"codex-gallery semantic --query woman --limit 1\\n</parameter>\\n</function>\\n</tool_call>"},"finish_reason":"stop"}]}\n\n'
            b'data: [DONE]\n\n'
        )
        repaired_body, repaired = PROXY.repair_sse_response(body, self.exec_payload())
        events = PROXY.parse_sse_events(repaired_body)
        deltas = [choice["delta"] for event in events if event["kind"] == "data" for choice in event["data"]["choices"]]
        calls = [call for delta in deltas for call in delta.get("tool_calls", [])]
        self.assertGreaterEqual(repaired, 1)
        self.assertEqual(calls[0]["function"]["name"], "exec_command")
        self.assertNotIn("<function=", repaired_body.decode())

    def test_malformed_or_unadvertised_hermes_function_markup_is_rejected(self):
        with self.assertRaisesRegex(PROXY.UpstreamResponseValidationError, "Invalid pseudo-tool envelope"):
            PROXY.pseudo_tool_function(
                "<function=exec_command><parameter=cmd>echo ok</function></tool_call>",
                self.exec_payload(),
            )
        with self.assertRaisesRegex(PROXY.UpstreamResponseValidationError, "not advertised"):
            PROXY.pseudo_tool_function(
                "<function=unknown><parameter=cmd>echo ok</parameter></function></tool_call>",
                self.exec_payload(),
            )

    def test_unknown_pseudo_tool_is_rejected_instead_of_rendered(self):
        body = json.dumps({
            "choices": [{"message": {
                "role": "assistant",
                "content": '<execute>{"name":"command_not_supported","arguments":{}}</execute>',
            }}]
        }).encode()
        with self.assertRaisesRegex(PROXY.UpstreamResponseValidationError, "not advertised"):
            PROXY.repair_json_response(body, self.exec_payload())

    def test_unknown_structured_tool_is_rejected_for_json_and_sse(self):
        json_body = b'{"choices":[{"message":{"tool_calls":[{"function":{"name":"unknown_tool","arguments":"{}"}}]}}]}'
        sse_body = (
            b'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"name":"unknown_tool","arguments":"{}"}}]}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        with self.assertRaisesRegex(PROXY.UpstreamResponseValidationError, "not advertised"):
            PROXY.repair_json_response(json_body, self.exec_payload())
        with self.assertRaisesRegex(PROXY.UpstreamResponseValidationError, "not advertised"):
            PROXY.repair_sse_response(sse_body, self.exec_payload())

    def test_repaired_sse_has_exact_done_framing(self):
        source = b'data: {"choices":[]}\r\n\r\ndata: [DONE]   \r\n\r\n'
        repaired, count = PROXY.repair_sse_response(source, {})
        self.assertEqual(count, 0)
        self.assertTrue(repaired.endswith(b"data: [DONE]\n\n"))
        self.assertFalse(repaired.endswith(b"data: [DONE]\n\n\n"))

    def test_successful_sse_buffers_model_bytes_while_comments_keep_transport_alive(self):
        source = (PROJECT_ROOT / "nemotron_unrestricted_proxy.py").read_text(encoding="utf-8")
        self.assertIn("read_bounded_response(", source)
        self.assertIn("blocking_wait(", source)
        self.assertIn(": nemotron-buffering", source)
        self.assertIn("heartbeat if sse_started else None", source)
        self.assertIn("stream_incomplete_error", source)
        self.assertIn("X-OpenRouter-Stream-Recoveries", source)
        self.assertNotIn("while chunk := response.read", source)

    def test_incomplete_upstream_read_is_detected_before_client_commit(self):
        class IncompleteResponse:
            closed = False

            def read(self, _limit):
                raise http.client.IncompleteRead(b"data: partial\n", 100)

            def close(self):
                self.closed = True

        response = IncompleteResponse()
        body, error = PROXY.read_bounded_response(response)
        self.assertEqual(body, b"data: partial\n")
        self.assertIsInstance(error, http.client.IncompleteRead)
        self.assertTrue(response.closed)

    def test_slow_buffered_read_emits_safe_heartbeat_callbacks(self):
        class SlowResponse:
            closed = False

            def read(self, _limit):
                time.sleep(0.05)
                return b"data: [DONE]\n\n"

            def close(self):
                self.closed = True

        response = SlowResponse()
        heartbeats = []
        body, error = PROXY.read_bounded_response(
            response, lambda: heartbeats.append(time.monotonic()) or True, wait_seconds=0.01
        )
        self.assertIsNone(error)
        self.assertEqual(body, b"data: [DONE]\n\n")
        self.assertGreaterEqual(len(heartbeats), 2)
        self.assertTrue(response.closed)

    def test_disconnected_blocking_wait_does_not_duplicate_and_closes_late_response(self):
        release = threading.Event()
        closed = threading.Event()
        calls = []

        class LateResponse:
            def close(self):
                closed.set()

        def operation():
            calls.append("called")
            release.wait(1)
            return LateResponse()

        value, error = PROXY.blocking_wait(
            operation,
            on_wait=lambda: False,
            wait_seconds=0.001,
            close_late_result=True,
        )
        self.assertIsNone(value)
        self.assertIsInstance(error, BrokenPipeError)
        release.set()
        self.assertTrue(closed.wait(1))
        self.assertEqual(calls, ["called"])


if __name__ == "__main__":
    unittest.main()
