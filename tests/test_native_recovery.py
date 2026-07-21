import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTIVITY_PATH = (
    ROOT
    / "src"
    / "com"
    / "michaelovsky"
    / "nemotronunrestricted"
    / "isolated"
    / "MainActivity.java"
)
SERVICE_PATH = ACTIVITY_PATH.with_name("NemotronRuntimeService.java")


class NativeRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ACTIVITY_PATH.read_text(encoding="utf-8")
        cls.service_source = SERVICE_PATH.read_text(encoding="utf-8")
        cls.base_activity = cls.source.split("@android.annotation.TargetApi(26)", 1)[0]
        cls.api26_client = cls.source.split("@android.annotation.TargetApi(26)", 1)[1]

    def test_api26_renderer_type_is_not_referenced_by_min_sdk_activity(self):
        self.assertNotIn("import android.webkit.RenderProcessGoneDetail", self.source)
        self.assertNotIn("RenderProcessGoneDetail", self.base_activity)
        self.assertIn("Build.VERSION.SDK_INT >= 26", self.base_activity)
        self.assertIn('Class.forName(', self.base_activity)
        self.assertIn('"com.michaelovsky.nemotronunrestricted.isolated.NemotronApi26WebViewClient"', self.base_activity)
        self.assertNotIn("new NemotronApi26WebViewClient", self.base_activity)
        self.assertIn("extends MainActivity.RuntimeWebViewClient", self.api26_client)
        self.assertIn("onRenderProcessGone", self.api26_client)
        self.assertIn("android.webkit.RenderProcessGoneDetail", self.api26_client)

    def test_common_client_preserves_all_navigation_and_error_callbacks(self):
        self.assertIn("static class RuntimeWebViewClient extends WebViewClient", self.source)
        for callback in (
            "onPageStarted",
            "onPageFinished",
            "doUpdateVisitedHistory",
            "shouldOverrideUrlLoading",
            "onReceivedError",
            "onReceivedHttpError",
        ):
            self.assertIn(callback, self.base_activity)
        self.assertIn("webView.setWebViewClient(createRuntimeWebViewClient())", self.source)

    def test_route_is_committed_on_history_and_every_terminal_lifecycle_edge(self):
        self.assertIn("owner.onRuntimeVisitedHistory(view, url)", self.source)
        self.assertIn(".putString(LAST_ROUTE_KEY, suffix).commit()", self.source)
        for lifecycle in ("protected void onPause()", "protected void onStop()", "protected void onDestroy()"):
            start = self.source.index(lifecycle)
            body = self.source[start:start + 240]
            self.assertIn("rememberCurrentRouteSynchronously();", body)
        renderer = self.source[
            self.source.index("private boolean handleRuntimeRendererGone"):
            self.source.index("protected void onPause()")
        ]
        self.assertIn("rememberCurrentRouteSynchronously();", renderer)

    def test_renderer_recovery_destroys_only_the_owned_webview_and_recreates_activity(self):
        renderer = self.source[
            self.source.index("private boolean handleRuntimeRendererGone"):
            self.source.index("protected void onPause()")
        ]
        self.assertIn("final boolean ownedView = view == webView", renderer)
        self.assertIn("((ViewGroup) parent).removeView(view)", renderer)
        self.assertIn("view.destroy()", renderer)
        self.assertIn("webView = null", renderer)
        self.assertIn("recreate()", renderer)
        self.assertIn("return true", renderer)
        self.assertNotIn("Runtime.getRuntime", renderer)
        self.assertNotIn("Process.killProcess", renderer)
        self.assertNotIn("System.exit", renderer)

    def test_stale_runtime_callbacks_cannot_replace_a_recovery_page(self):
        self.assertIn("expectedRuntimeUrl", self.source)
        self.assertIn("isCurrentRuntimeNavigation", self.source)
        current = self.source[
            self.source.index("private boolean isCurrentRuntimeNavigation"):
            self.source.index("private void markGuiReady")
        ]
        self.assertIn("view != webView", current)
        self.assertIn("generation != runtimeLoadGeneration", current)
        self.assertIn("!guiLoadInProgress", current)
        self.assertIn("!expectedRuntimeUrl.equals(url)", current)
        self.assertIn('expectedRuntimeUrl = "";', self.source)

    def test_stale_webview_navigation_and_errors_are_rejected(self):
        navigation = self.source[
            self.source.index("private boolean onRuntimeNavigation"):
            self.source.index("private boolean isRecoverableMainFrameError")
        ]
        self.assertIn("if (view != webView)", navigation)
        self.assertIn("view == webView", navigation)
        self.assertIn("isTrustedRuntimeUri(request.getUrl())", navigation)
        self.assertIn("onRuntimeReceivedError(view, request, error)", self.source)
        self.assertIn("onRuntimeReceivedHttpError(view, request, response)", self.source)

    def test_recovery_pages_are_null_safe_and_resume_revalidates_dynamic_port(self):
        for method in ("private void showStartingPage", "private void showStartupFailure"):
            body = self.source[self.source.index(method):self.source.index(method) + 220]
            self.assertIn("destroyed || webView == null", body)
        self.assertIn("verifyRuntimeEndpointAfterResume();", self.source)
        probe = self.source[
            self.source.index("private void verifyRuntimeEndpointAfterResume"):
            self.source.index("private String runtimeWebUrl")
        ]
        self.assertIn("final int loadedPort = runtimePort", probe)
        self.assertIn("final boolean ready = discoverRuntimePort()", probe)
        self.assertIn("discoveredPort != loadedPort", probe)
        self.assertIn("loadRuntimeGui();", probe)

    def test_proxy_health_identity_is_strict_but_allows_degraded_auth(self):
        discovery = self.source[
            self.source.index("private boolean discoverRuntimePort"):
            self.source.index("private void startRuntimeWatchdog")
        ]
        for expected in (
            '"/vault-health"',
            '"ok".equals(health.optString("status"))',
            'APP_ID.equals(health.optString("app"))',
            '"OpenRouter".equals(health.optString("provider"))',
            'health.optInt("proxyPort", 0) != proxyPort',
            'health.optString("effectiveBaseUrl")',
            'health.optString("sourceHash")',
            'health.optString("supervisorSourceHash")',
            'health.optString("credentialSourceFingerprint")',
            "credentialConfigured instanceof Boolean",
        ):
            self.assertIn(expected, discovery)
        self.assertNotIn('health.optBoolean("credentialConfigured", false)', discovery)
        self.assertNotIn("DEFAULT_MODEL", self.source)
        self.assertIn("discovered == proxyPort", discovery)
        self.assertIn("discoveredSupervisor == proxyPort", discovery)
        self.assertIn("discoveredSupervisor == discovered", discovery)
        self.assertIn("supervisorIsOurs(discoveredSupervisor, discoveredSupervisorHash)", discovery)
        supervisor = self.source[
            self.source.index("private boolean supervisorIsOurs"):
            self.source.index("private void postSupervisorEvent")
        ]
        self.assertIn('"/health"', supervisor)
        self.assertIn('expectedSourceHash.equals(health.optString("sourceSha256"))', supervisor)

    def test_gui_config_and_free_mode_are_cross_validated(self):
        self.assertIn('"{\\"method\\":\\"config/read\\",\\"params\\":{}}"', self.source)
        self.assertIn('"/codex-api/rpc"', self.source)
        self.assertIn('"custom_endpoint".equals(config.optString("model_provider"))', self.source)
        self.assertIn('providers.optJSONObject("custom_endpoint")', self.source)
        self.assertIn('custom.optString("base_url")', self.source)
        self.assertIn('"/codex-api/custom-proxy/v1"', self.source)
        self.assertIn('"/codex-api/free-mode/status"', self.source)
        self.assertIn('status.optBoolean("enabled", false)', self.source)
        self.assertIn('"custom".equals(status.optString("provider"))', self.source)
        self.assertIn('"chat".equals(status.optString("wireApi"))', self.source)
        self.assertIn('status.optString("customBaseUrl")', self.source)
        config_method = self.source[
            self.source.index("private boolean guiConfigIsOurs"):
            self.source.index("private boolean freeModeIsOurs")
        ]
        self.assertNotIn('config.optString("customBaseUrl")', config_method)
        self.assertIn("MAX_CONFIG_RESPONSE_CHARACTERS = 262144", self.source)
        self.assertIn("readJsonResponse(connection, MAX_CONFIG_RESPONSE_CHARACTERS)", self.source)
        self.assertIn("MAX_CONFIG_RESPONSE_CHARACTERS = 262144", self.service_source)
        self.assertIn("body.length() + line.length() > MAX_CONFIG_RESPONSE_CHARACTERS", self.service_source)

    def test_background_completion_monitor_and_exact_tone_are_native(self):
        self.assertIn('"/events?after="', self.service_source)
        self.assertIn('COMPLETION_SEQUENCE_KEY', self.service_source)
        self.assertIn('scheduleWithFixedDelay', self.service_source)
        self.assertIn('}, 1L, 2L, TimeUnit.SECONDS);', self.service_source)
        self.assertIn('new ToneGenerator(AudioManager.STREAM_NOTIFICATION, 50)', self.service_source)
        self.assertIn('ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 3000', self.service_source)
        self.assertIn('putLong(COMPLETION_SEQUENCE_KEY, newest)', self.service_source)
        self.assertIn('acknowledgeCompletionTone(selected, sequence)', self.service_source)
        self.assertIn('"http://127.0.0.1:" + supervisorPort + "/ack"', self.service_source)
        self.assertIn('contains("isolated Nemotron Autonomy runtime using OpenRouter")', self.service_source)
        self.assertIn('public void missionStarted', self.source)
        self.assertIn('postSupervisorEvent("active", safePayload)', self.source)


if __name__ == "__main__":
    unittest.main()
