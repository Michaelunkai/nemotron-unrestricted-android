import http.client
import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_HOME = pathlib.Path(tempfile.mkdtemp(prefix="nemotron-endpoints-test-"))
os.environ["CODEX_HOME"] = str(TEST_HOME)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROXY = load("nemotron_endpoint_proxy", "nemotron_unrestricted_proxy.py")
SUPERVISOR = load("nemotron_endpoint_supervisor", "nemotron_session_supervisor.py")


class FakeUpstreamResponse:
    def __init__(self, body, content_type="text/event-stream", status=200, read_error=None, read_delay=0.0, headers=None):
        self.body = body
        self.headers = {"Content-Type": content_type}
        self.headers.update(headers or {})
        self.status = status
        self.read_error = read_error
        self.read_delay = read_delay
        self.closed = False

    def getcode(self):
        return self.status

    def read(self, _limit):
        if self.read_delay:
            time.sleep(self.read_delay)
        if self.read_error is not None:
            raise self.read_error
        return self.body

    def close(self):
        self.closed = True


class RuntimeEndpointTests(unittest.TestCase):
    def replace_proxy(self, name, value):
        original = getattr(PROXY, name)
        setattr(PROXY, name, value)
        self.addCleanup(setattr, PROXY, name, original)

    def streaming_payload(self):
        return json.dumps({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "test"}],
            "stream": True,
        })

    def tool_payload(self, stream=False):
        return {
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "test"}],
            "stream": stream,
            "tools": [{
                "type": "function",
                "function": {"name": "test_tool", "parameters": {"type": "object"}},
            }],
        }

    def request_json(self, port, payload, handler_path="/v1/chat/completions"):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request(
            "POST",
            handler_path,
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def local_get_json(self, port, path):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response, payload

    def wait_proxy_catalog_refresh(self, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with PROXY.CATALOG_LOCK:
                if not PROXY.CATALOG_REFRESHING:
                    return
            time.sleep(0.001)
        self.fail("proxy catalog refresh did not finish")

    def install_catalog_and_chat_mock(self, chat_responses, catalog_rows, *, seed_live=False):
        calls = []
        responses = iter(chat_responses)
        original_urlopen = PROXY.urllib.request.urlopen

        def urlopen(request, *_args, **_kwargs):
            if request.full_url == PROXY.PUBLIC_CATALOG_URL:
                calls.append(("catalog", None))
                return FakeUpstreamResponse(
                    json.dumps({"data": catalog_rows}).encode("utf-8"),
                    content_type="application/json",
                )
            body = json.loads(request.data.decode("utf-8"))
            calls.append(("chat", body))
            return next(responses)

        PROXY.urllib.request.urlopen = urlopen
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        seeded_models = {}
        if seed_live:
            for row in catalog_rows:
                entry = PROXY.normalize_catalog_entry(row)
                if entry is not None:
                    seeded_models[entry["id"]] = entry
        with PROXY.CATALOG_LOCK:
            saved_cache = dict(PROXY.CATALOG_CACHE)
            saved_refreshing = PROXY.CATALOG_REFRESHING
            PROXY.CATALOG_CACHE.update({
                "models": seeded_models,
                "loadedAt": time.monotonic() if seeded_models else 0.0,
            })
            PROXY.CATALOG_REFRESHING = False

        def restore_catalog():
            self.wait_proxy_catalog_refresh()
            with PROXY.CATALOG_LOCK:
                PROXY.CATALOG_CACHE.clear()
                PROXY.CATALOG_CACHE.update(saved_cache)
                PROXY.CATALOG_REFRESHING = saved_refreshing

        self.addCleanup(restore_catalog)
        return calls

    def use_audit_path(self):
        path = TEST_HOME / f"audit-{time.monotonic_ns()}.jsonl"
        self.replace_proxy("AUDIT_PATH", path)
        return path

    def read_audit_record(self, path, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                lines = []
            if lines:
                return json.loads(lines[-1])
            time.sleep(0.005)
        self.fail("proxy request audit was not finalized before the bounded deadline")

    def test_launcher_uses_dynamic_identity_without_exporting_credentials_or_following_broker_links(self):
        launcher = (ROOT / "nemotron-unrestricted-start.sh").read_text(encoding="utf-8")
        self.assertNotIn("OPENROUTER_API_KEY=$(", launcher)
        self.assertNotIn("export OPENROUTER_API_KEY", launcher)
        self.assertNotIn('chmod 600 "$ISOLATED_CODEX_ROOT/vault/broker.json"', launcher)
        self.assertIn("ensure_private_credential_file", launcher)
        self.assertIn("os.O_NOFOLLOW", launcher)
        self.assertIn("resolve_dolphin_x1_base_url", launcher)
        self.assertIn('ipaddress.ip_network("100.64.0.0/10")', launcher)
        self.assertIn('DOLPHIN_X1_BASE_URL="$DOLPHIN_X1_BASE_URL"', launcher)
        self.assertNotIn("DOLPHIN_X1_API_KEY", launcher)
        self.assertIn('health.get("proxyPort") == port', launcher)
        self.assertIn('health.get("supervisorPort") == supervisor_port', launcher)
        self.assertIn('health.get("providerBaseUrl") == expected_base_url', launcher)
        self.assertIn('health.get("effectiveBaseUrl") == expected_base_url', launcher)
        self.assertIn('provider_file_is_current "$stored_proxy"', launcher)
        self.assertIn('process_is_owned_session_leader "${process##*/}"', launcher)
        self.assertIn('kill -- "-${process##*/}"', launcher)
        self.assertNotIn('config.get("model") == "nousresearch/hermes-4-405b"', launcher)
        copy_index = launcher.index('if [ ! -f "$ISOLATED_CODEX_ROOT/config.toml" ]')
        provider_index = launcher.index("write_provider_base_url", copy_index)
        preflight_index = launcher.index('"$APP_HOME/isolation-preflight.sh"', provider_index)
        self.assertLess(copy_index, provider_index)
        self.assertLess(provider_index, preflight_index)

    def request_stream(self, port, timeout=2):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=self.streaming_payload(),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def run_server(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_proxy_health_has_strict_identity_without_exposing_a_key(self):
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/vault-health", timeout=2) as response:
            health = json.load(response)
        self.assertEqual(health["app"], "nemotron-unrestricted")
        self.assertEqual(health["provider"], "OpenRouter")
        self.assertEqual(health["proxyPort"], PROXY.PORT)
        self.assertEqual(health["guiPort"], PROXY.GUI_PORT)
        self.assertEqual(health["supervisorPort"], PROXY.SUPERVISOR_PORT)
        self.assertEqual(health["providerBaseUrl"], PROXY.PROVIDER_BASE_URL)
        self.assertEqual(health["effectiveBaseUrl"], PROXY.PROVIDER_BASE_URL)
        self.assertEqual(health["exactDolphinModel"], PROXY.DOLPHIN_X1_MODEL)
        self.assertIs(health["exactDolphinAvailable"], False)
        self.assertEqual(health["sourceHash"], PROXY.SOURCE_SHA256)
        self.assertEqual(health["sourceSha256"], PROXY.SOURCE_SHA256)
        self.assertEqual(health["supervisorSourceHash"], PROXY.SUPERVISOR_SOURCE_SHA256)
        self.assertIs(health["credentialConfigured"], False)
        self.assertRegex(health["credentialSourceFingerprint"], r"^[0-9a-f]{24}$")
        encoded = json.dumps(health)
        self.assertNotIn("OPENROUTER_API_KEY", encoded)
        self.assertNotIn("sk-or-", encoded)

    def test_broker_health_never_connects_and_missing_key_post_returns_precise_401(self):
        with tempfile.TemporaryDirectory(prefix="nemotron-health-credential-") as directory:
            home = pathlib.Path(directory)
            vault = home / "vault"
            vault.mkdir()
            credential = home / "openrouter.env"
            credential.write_text("# broker-backed credential\n", encoding="utf-8")
            credential.chmod(0o600)
            broker = vault / "broker.json"
            broker.write_text(
                json.dumps({"host": "127.0.0.1", "port": 65534, "token": "test-token"}),
                encoding="utf-8",
            )
            broker.chmod(0o600)
            connection_calls = []
            original_create_connection = PROXY.socket.create_connection

            def unavailable_broker(address, *args, **kwargs):
                if address == ("127.0.0.1", 65534):
                    connection_calls.append(time.monotonic())
                    time.sleep(0.2)
                    raise TimeoutError("broker unavailable")
                return original_create_connection(address, *args, **kwargs)

            with mock.patch.object(PROXY, "CODEX_HOME", home), \
                 mock.patch.object(PROXY.socket, "create_connection", side_effect=unavailable_broker):
                port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
                health_started = time.monotonic()
                health_response, health = self.local_get_json(port, "/vault-health")
                health_elapsed = time.monotonic() - health_started
                self.assertEqual(health_response.status, 200)
                self.assertIs(health["credentialConfigured"], True)
                self.assertEqual(connection_calls, [])
                self.assertLess(health_elapsed, 0.15)

                response, body = self.request_json(port, {
                    "model": PROXY.DEFAULT_MODEL,
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": False,
                })
        self.assertEqual(len(connection_calls), 1)
        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(body)["error"]["type"], "authentication_error")

    def test_proxy_rejects_non_object_json_with_json_error(self):
        audit_path = self.use_audit_path()
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("POST", "/v1/chat/completions", body=b"[]", headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        self.assertEqual(response.status, 400)
        self.assertEqual(payload["error"]["type"], "invalid_request_error")
        audit = self.read_audit_record(audit_path)
        self.assertEqual(audit["outcome"], "invalid_request_error")
        self.assertEqual(audit["status"], 400)
        self.assertIs(audit["delivered"], True)

    def test_models_endpoint_refreshes_public_catalog_and_returns_dynamic_models(self):
        rows = [
            {"id": PROXY.DEFAULT_MODEL, "supported_parameters": [], "pricing": {"prompt": "1", "completion": "1"}},
            {"id": "nvidia/nemotron-nano:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "vendor/paid-tool", "supported_parameters": ["tools"], "pricing": {"prompt": "0.1", "completion": "0"}},
        ]
        calls = self.install_catalog_and_chat_mock([], rows)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        first_response, first_payload = self.local_get_json(port, "/v1/models")
        self.assertEqual(first_response.status, 200)
        self.assertEqual(first_payload["catalog_source"], "static")
        self.wait_proxy_catalog_refresh()
        response, payload = self.local_get_json(port, "/v1/models")
        self.assertEqual(calls, [("catalog", None)])
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["catalog_source"], "live")
        self.assertEqual([model["id"] for model in payload["data"]], [
            PROXY.DEFAULT_MODEL,
            "nvidia/nemotron-nano:free",
        ])

    def test_cold_tool_request_fetches_live_catalog_before_routing(self):
        rows = [
            {"id": "nvidia/nemotron-ultra:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
        ]
        calls = self.install_catalog_and_chat_mock([
            FakeUpstreamResponse(b'{"model":"nvidia/nemotron-ultra:free","choices":[{"message":{"role":"assistant","content":"ready"}}]}', content_type="application/json"),
        ], rows, seed_live=False)
        self.replace_proxy("get_api_key", lambda: "test-key")
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_json(port, self.tool_payload())
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body)["model"], "nvidia/nemotron-ultra:free")
        self.assertEqual(calls[0], ("catalog", None))
        chat_bodies = [payload for kind, payload in calls if kind == "chat"]
        self.assertEqual([payload["model"] for payload in chat_bodies], ["nvidia/nemotron-ultra:free"])

    def test_non_stream_malformed_tool_call_shapes_are_sanitized_errors(self):
        self.replace_proxy("get_api_key", lambda: "test-key")
        catalog_rows = [{
            "id": "nvidia/nemotron-ultra:free",
            "supported_parameters": ["tools"],
            "pricing": {"prompt": "0", "completion": "0"},
        }]
        malformed_calls = [
            None,
            {},
            {"function": None},
            {"function": {"name": "schema_tool"}},
            {"function": {"name": "schema_tool", "arguments": None}},
        ]
        for malformed in malformed_calls:
            with self.subTest(malformed=malformed):
                self.replace_proxy("get_api_key", lambda: "test-key")
                upstream = json.dumps({
                    "choices": [{"message": {"tool_calls": [malformed]}}],
                }).encode("utf-8")
                self.install_catalog_and_chat_mock([
                    FakeUpstreamResponse(upstream, content_type="application/json"),
                ], catalog_rows, seed_live=True)
                port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
                response, body = self.request_json(port, self.tool_payload())
                decoded = json.loads(body)
                self.assertEqual(response.status, 502)
                self.assertEqual(decoded["error"]["type"], "invalid_upstream_response")
                self.assertNotIn("schema_tool", decoded["error"]["message"])

    def test_model_retirement_switches_to_next_candidate_without_duplicate_request_models(self):
        rows = [
            {"id": "nvidia/nemotron-ultra:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-super:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-nano:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
        ]
        calls = self.install_catalog_and_chat_mock([
            FakeUpstreamResponse(
                b'{"error":{"message":"model endpoint unavailable"}}',
                content_type="application/json",
                status=404,
            ),
            FakeUpstreamResponse(
                b'{"model":"nvidia/nemotron-super:free","choices":[{"message":{"role":"assistant","content":"ready"}}]}',
                content_type="application/json",
            ),
        ], rows, seed_live=True)
        self.replace_proxy("get_api_key", lambda: "test-key")
        audit_path = self.use_audit_path()
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_json(port, self.tool_payload())
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body)["model"], "nvidia/nemotron-super:free")
        chat_bodies = [body for kind, body in calls if kind == "chat"]
        self.assertEqual([item["model"] for item in chat_bodies], [
            "nvidia/nemotron-ultra:free",
            "nvidia/nemotron-super:free",
        ])
        self.assertEqual(chat_bodies[0]["models"], [
            "nvidia/nemotron-super:free",
            "nvidia/nemotron-nano:free",
        ])
        self.assertEqual(chat_bodies[1]["models"], ["nvidia/nemotron-nano:free"])
        for item in chat_bodies:
            self.assertNotIn(item["model"], item.get("models", []))
        self.assertEqual(response.getheader("X-OpenRouter-Model"), "nvidia/nemotron-super:free")
        audit = self.read_audit_record(audit_path)
        self.assertEqual(audit["outcome"], "success")
        self.assertEqual(audit["effectiveModel"], "nvidia/nemotron-super:free")
        self.assertEqual(audit["attempts"], 2)

    def test_image_route_400_advances_to_next_verified_vision_candidate(self):
        rows = [
            {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "supported_parameters": ["tools"], "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}, "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "google/gemma-4-31b-it:free", "supported_parameters": ["tools"], "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}, "pricing": {"prompt": "0", "completion": "0"}},
        ]
        calls = self.install_catalog_and_chat_mock([
            FakeUpstreamResponse(b'{"error":{"message":"image input unavailable on selected provider"}}', content_type="application/json", status=400),
            FakeUpstreamResponse(b'{"model":"google/gemma-4-31b-it:free","choices":[{"message":{"role":"assistant","content":"red"}}]}', content_type="application/json"),
        ], rows, seed_live=True)
        self.replace_proxy("get_api_key", lambda: "test-key")
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_json(port, {
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "color"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
            ]}],
        })
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body)["model"], "google/gemma-4-31b-it:free")
        chat_bodies = [value for kind, value in calls if kind == "chat"]
        self.assertEqual([value["model"] for value in chat_bodies], [
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "google/gemma-4-31b-it:free",
        ])

    def test_429_and_503_honor_retry_after_while_advancing_candidates(self):
        rows = [
            {"id": "nvidia/nemotron-ultra:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-super:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
        ]
        for retry_status in (429, 503):
            with self.subTest(status=retry_status):
                calls = self.install_catalog_and_chat_mock([
                    FakeUpstreamResponse(
                        b'{"error":{"message":"temporarily unavailable"}}',
                        content_type="application/json",
                        status=retry_status,
                        headers={"Retry-After": "0"},
                    ),
                    FakeUpstreamResponse(
                        b'{"model":"nvidia/nemotron-super:free","choices":[{"message":{"role":"assistant","content":"ready"}}]}',
                        content_type="application/json",
                    ),
                ], rows, seed_live=True)
                self.replace_proxy("get_api_key", lambda: "test-key")
                port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
                response, _body = self.request_json(port, self.tool_payload())
                self.assertEqual(response.status, 200)
                chat_bodies = [body for kind, body in calls if kind == "chat"]
                self.assertEqual([item["model"] for item in chat_bodies], [
                    "nvidia/nemotron-ultra:free",
                    "nvidia/nemotron-super:free",
                ])

    def test_empty_completion_retries_next_tool_model_instead_of_ending_silently(self):
        rows = [
            {"id": "nvidia/nemotron-ultra:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "nvidia/nemotron-super:free", "supported_parameters": ["tools"], "pricing": {"prompt": "0", "completion": "0"}},
        ]
        calls = self.install_catalog_and_chat_mock([
            FakeUpstreamResponse(
                b'{"model":"nvidia/nemotron-ultra:free","choices":[{"message":{"role":"assistant","content":null,"reasoning":"private"},"finish_reason":"stop"}]}',
                content_type="application/json",
            ),
            FakeUpstreamResponse(
                b'{"model":"nvidia/nemotron-super:free","choices":[{"message":{"role":"assistant","content":"visible answer"},"finish_reason":"stop"}]}',
                content_type="application/json",
            ),
        ], rows, seed_live=True)
        self.replace_proxy("get_api_key", lambda: "test-key")
        self.replace_proxy("recovery_delay", lambda _attempt: 0.001)
        audit_path = self.use_audit_path()
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_json(port, self.tool_payload())
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body)["choices"][0]["message"]["content"], "visible answer")
        chat_bodies = [payload for kind, payload in calls if kind == "chat"]
        self.assertEqual([item["model"] for item in chat_bodies], [
            "nvidia/nemotron-ultra:free",
            "nvidia/nemotron-super:free",
        ])
        audit = self.read_audit_record(audit_path)
        self.assertEqual(audit["outcome"], "success")
        self.assertEqual(audit["emptyResponseRetries"], 1)
        self.assertEqual(audit["attempts"], 2)

    def test_slow_sse_sends_immediate_and_three_second_transport_comments(self):
        self.replace_proxy("SSE_HEARTBEAT_SECONDS", 0.02)
        self.replace_proxy("get_api_key", lambda: "test-key")
        response_body = b'data: {"choices":[{"delta":{"content":"ready"}}]}\n\ndata: [DONE]\n\n'
        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = lambda *_args, **_kwargs: FakeUpstreamResponse(
            response_body, read_delay=0.07
        )
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        started = time.monotonic()
        connection.request("POST", "/v1/chat/completions", body=self.streaming_payload(), headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        first_comment = response.readline()
        response.readline()
        self.assertLess(time.monotonic() - started, 0.2)
        second_comment = response.readline()
        response.readline()
        remaining = response.read()
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(first_comment, b": nemotron-buffering\n")
        self.assertEqual(second_comment, b": nemotron-buffering\n")
        self.assertTrue(remaining.endswith(b'data: [DONE]\n\n'))

    def test_stream_headers_and_heartbeats_cover_delayed_credential_lookup(self):
        self.replace_proxy("SSE_HEARTBEAT_SECONDS", 0.02)

        def delayed_key():
            time.sleep(0.07)
            return "test-key"

        self.replace_proxy("get_api_key", delayed_key)
        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = lambda *_args, **_kwargs: FakeUpstreamResponse(
            b'data: {"choices":[{"delta":{"content":"ready"}}]}\n\ndata: [DONE]\n\n'
        )
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        started = time.monotonic()
        connection.request("POST", "/v1/chat/completions", body=self.streaming_payload(), headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        first_comment = response.readline()
        response.readline()
        self.assertLess(time.monotonic() - started, 0.2)
        second_comment = response.readline()
        response.readline()
        remaining = response.read()
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(first_comment, b": nemotron-buffering\n")
        self.assertEqual(second_comment, b": nemotron-buffering\n")
        self.assertTrue(remaining.endswith(b"data: [DONE]\n\n"))

    def test_stream_headers_and_heartbeats_cover_delayed_upstream_connection(self):
        self.replace_proxy("SSE_HEARTBEAT_SECONDS", 0.02)
        self.replace_proxy("get_api_key", lambda: "test-key")

        def delayed_urlopen(*_args, **_kwargs):
            time.sleep(0.07)
            return FakeUpstreamResponse(b"data: [DONE]\n\n")

        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = delayed_urlopen
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        started = time.monotonic()
        connection.request("POST", "/v1/chat/completions", body=self.streaming_payload(), headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        first_comment = response.readline()
        response.readline()
        self.assertLess(time.monotonic() - started, 0.2)
        second_comment = response.readline()
        response.readline()
        remaining = response.read()
        connection.close()
        self.assertEqual(first_comment, b": nemotron-buffering\n")
        self.assertEqual(second_comment, b": nemotron-buffering\n")
        self.assertTrue(remaining.endswith(b"data: [DONE]\n\n"))

    def test_stream_final_connection_failure_is_sse_error_with_done(self):
        self.replace_proxy("get_api_key", lambda: "test-key")
        self.replace_proxy("MAX_UPSTREAM_ATTEMPTS", 1)
        original_urlopen = PROXY.urllib.request.urlopen

        def fail_connection(*_args, **_kwargs):
            raise urllib.error.URLError("offline")

        PROXY.urllib.request.urlopen = fail_connection
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_stream(port)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertIn(b"event: error\n", body)
        self.assertIn(b'"type":"upstream_error"', body)
        self.assertTrue(body.endswith(b"data: [DONE]\n\n"))

    def test_non_stream_final_connection_failure_remains_json(self):
        audit_path = self.use_audit_path()
        self.replace_proxy("get_api_key", lambda: "test-key")
        self.replace_proxy("MAX_UPSTREAM_ATTEMPTS", 1)
        original_urlopen = PROXY.urllib.request.urlopen

        def fail_connection(*_args, **_kwargs):
            raise urllib.error.URLError("offline")

        PROXY.urllib.request.urlopen = fail_connection
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        payload = json.dumps({
            "model": PROXY.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "test"}],
            "stream": False,
        })
        connection.request("POST", "/v1/chat/completions", body=payload, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        self.assertEqual(response.status, 502)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(body["error"]["type"], "upstream_error")
        audit = self.read_audit_record(audit_path)
        self.assertEqual(audit["outcome"], "upstream_error")
        self.assertEqual(audit["status"], 502)
        self.assertIs(audit["delivered"], True)

    def test_final_client_write_failure_is_audited_as_disconnect_not_success(self):
        class DisconnectingHandler(PROXY.Handler):
            def client_write(self, _body):
                return False

        audit_path = self.use_audit_path()
        self.replace_proxy("get_api_key", lambda: "test-key")
        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = lambda *_args, **_kwargs: FakeUpstreamResponse(
            b'{"model":"provider/effective","choices":[{"message":{"role":"assistant","content":"ready"}}]}',
            content_type="application/json",
        )
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), DisconnectingHandler))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=json.dumps({"model": PROXY.DEFAULT_MODEL, "messages": [], "stream": False}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        try:
            response.read()
        except http.client.IncompleteRead:
            pass
        connection.close()
        audit = self.read_audit_record(audit_path)
        self.assertEqual(audit["outcome"], "client_disconnected")
        self.assertIs(audit["delivered"], False)
        self.assertEqual(audit["effectiveModel"], "provider/effective")

    def test_stream_retry_discards_partial_model_bytes(self):
        self.replace_proxy("get_api_key", lambda: "test-key")
        self.replace_proxy("MAX_UPSTREAM_ATTEMPTS", 2)
        self.replace_proxy("recovery_delay", lambda _attempt: 0.001)
        partial = b'data: {"choices":[{"delta":{"content":"LEAKED_ATTEMPT"}}]}\n\n'
        responses = iter([
            FakeUpstreamResponse(b"", read_error=http.client.IncompleteRead(partial, 100)),
            FakeUpstreamResponse(b'data: {"choices":[{"delta":{"content":"FINAL_ATTEMPT"}}]}\n\ndata: [DONE]\n\n'),
        ])
        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = lambda *_args, **_kwargs: next(responses)
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_stream(port)
        self.assertEqual(response.status, 200)
        self.assertNotIn(b"LEAKED_ATTEMPT", body)
        self.assertEqual(body.count(b"FINAL_ATTEMPT"), 1)
        self.assertTrue(body.endswith(b"data: [DONE]\n\n"))

    def test_stream_retry_content_type_mismatch_becomes_sse_error(self):
        self.replace_proxy("get_api_key", lambda: "test-key")
        self.replace_proxy("MAX_UPSTREAM_ATTEMPTS", 2)
        self.replace_proxy("recovery_delay", lambda _attempt: 0.001)
        responses = iter([
            FakeUpstreamResponse(b'data: {"choices":[{"delta":{"content":"FIRST_PARTIAL"}}]}\n\n'),
            FakeUpstreamResponse(b'{"raw":"RAW_JSON_MARKER"}', content_type="application/json"),
        ])
        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = lambda *_args, **_kwargs: next(responses)
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_stream(port)
        self.assertEqual(response.status, 200)
        self.assertIn(b"event: error\n", body)
        self.assertIn(b'"type":"invalid_upstream_response"', body)
        self.assertNotIn(b"FIRST_PARTIAL", body)
        self.assertNotIn(b"RAW_JSON_MARKER", body)
        self.assertTrue(body.endswith(b"data: [DONE]\n\n"))

    def test_stream_repair_exception_becomes_sse_error(self):
        self.replace_proxy("get_api_key", lambda: "test-key")

        def fail_repair(_body, _payload):
            raise RuntimeError("repair failed")

        self.replace_proxy("repair_sse_response", fail_repair)
        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = lambda *_args, **_kwargs: FakeUpstreamResponse(
            b'data: {"choices":[{"delta":{"content":"ready"}}]}\n\ndata: [DONE]\n\n'
        )
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_stream(port)
        self.assertEqual(response.status, 200)
        self.assertIn(b"event: error\n", body)
        self.assertIn(b'"type":"invalid_upstream_response"', body)
        self.assertTrue(body.endswith(b"data: [DONE]\n\n"))

    def test_stream_malformed_tool_arguments_become_sanitized_sse_error(self):
        self.replace_proxy("get_api_key", lambda: "test-key")
        upstream = "\n".join([
            'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"name":"schema_tool","arguments":"{sensitive-marker"}}]}}]}',
            "",
            "data: [DONE]",
            "",
        ]).encode()
        original_urlopen = PROXY.urllib.request.urlopen
        PROXY.urllib.request.urlopen = lambda *_args, **_kwargs: FakeUpstreamResponse(upstream)
        self.addCleanup(setattr, PROXY.urllib.request, "urlopen", original_urlopen)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        response, body = self.request_stream(port)
        self.assertEqual(response.status, 200)
        self.assertIn(b"event: error\n", body)
        self.assertIn(b'"type":"invalid_upstream_response"', body)
        self.assertNotIn(b"sensitive-marker", body)
        self.assertNotIn(b'"arguments":"{}"', body)
        self.assertTrue(body.endswith(b"data: [DONE]\n\n"))

    def test_non_stream_invalid_tool_arguments_become_sanitized_json_error(self):
        self.replace_proxy("get_api_key", lambda: "test-key")
        catalog_rows = [{
            "id": "nvidia/nemotron-ultra:free",
            "supported_parameters": ["tools"],
            "pricing": {"prompt": "0", "completion": "0"},
        }]
        arguments = json.dumps({"count": 1.25})
        upstream = json.dumps({
            "choices": [{
                "message": {
                    "tool_calls": [{"function": {"name": "schema_tool", "arguments": arguments}}],
                },
            }],
        }).encode()
        self.install_catalog_and_chat_mock([
            FakeUpstreamResponse(upstream, content_type="application/json"),
        ], catalog_rows, seed_live=True)
        port = self.run_server(PROXY.Server(("127.0.0.1", 0), PROXY.Handler))
        payload = json.dumps({
            "model": PROXY.DEFAULT_TOOL_MODEL,
            "messages": [{"role": "user", "content": "test"}],
            "stream": False,
            "tools": [{
                "type": "function",
                "function": {
                    "name": "schema_tool",
                    "parameters": {
                        "type": "object",
                        "required": ["count"],
                        "properties": {"count": {"type": "integer"}},
                        "additionalProperties": False,
                    },
                },
            }],
        })
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("POST", "/v1/chat/completions", body=payload, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        decoded = json.loads(body)
        self.assertEqual(response.status, 502)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(decoded["error"]["type"], "invalid_upstream_response")
        self.assertNotIn(b"1.25", body)
        self.assertNotIn(b'"arguments":{}', body)

    def test_supervisor_http_endpoint_persists_once_and_reports_identity(self):
        SUPERVISOR.EVENTS_PATH = TEST_HOME / "http" / "completion-events.jsonl"
        SUPERVISOR.LESSONS_PATH = SUPERVISOR.EVENTS_PATH.with_name("lessons.jsonl")
        SUPERVISOR.SEQUENCE = 0
        SUPERVISOR.SEEN_COMPLETIONS.clear()
        port = self.run_server(SUPERVISOR.Server(("127.0.0.1", 0), SUPERVISOR.Handler))
        event = json.dumps({"turnId": "http-turn", "threadId": "thread", "outcome": "completed", "actionCount": 2})
        results = []
        for _ in range(2):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/event",
                data=event.encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                results.append(json.load(response))
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            health = json.load(response)
        self.assertFalse(results[0]["duplicate"])
        self.assertTrue(results[1]["duplicate"])
        self.assertEqual(health["app"], "nemotron-unrestricted")
        self.assertEqual(health["completionCount"], 1)
        self.assertEqual(len(SUPERVISOR.EVENTS_PATH.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
