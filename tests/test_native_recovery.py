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

    def test_signed_packaged_overlay_is_intercepted_loaded_and_probed_by_the_real_webview(self):
        self.assertIn('NATIVE_OVERLAY_PATH = "/nemotron-autonomy-progress.js"', self.source)
        self.assertIn("private WebResourceResponse interceptRuntimeResource", self.source)
        self.assertIn('getAssets().open("runtime-contract/nemotron-autonomy-progress.js")', self.source)
        self.assertIn('new WebResourceResponse("application/javascript", "UTF-8", overlay)', self.source)
        self.assertIn('headers.put("Cache-Control", "no-store, no-cache, must-revalidate")', self.source)
        self.assertIn("owner.interceptRuntimeResource(view, request.getUrl())", self.source)
        self.assertIn("owner.interceptRuntimeResource(view, Uri.parse(url))", self.source)
        self.assertIn("injectPackagedAutonomyOverlay(view, url);", self.source)
        self.assertIn("nemotron-native-overlay-loader", self.source)
        self.assertIn("script.onload=function()", self.source)
        self.assertIn("script.onerror=function()", self.source)
        self.assertIn("native-loader-loaded", self.source)
        self.assertIn("native-loader-error", self.source)
        self.assertNotIn("view.evaluateJavascript(source", self.source)
        self.assertIn("private void probeCleanupUi", self.source)
        self.assertIn("NemotronUiProof", self.source)
        page_finished = self.source[
            self.source.index("private void onRuntimePageFinished"):
            self.source.index("private void onRuntimeVisitedHistory")
        ]
        self.assertIn("schedulePackagedAutonomyOverlay(view, url, generation);", page_finished)

    def test_packaged_overlay_waits_for_committed_vue_frame_and_settling_delay(self):
        page_finished = self.source[
            self.source.index("private void onRuntimePageFinished"):
            self.source.index("private void onRuntimeVisitedHistory")
        ]
        self.assertGreater(
            page_finished.index("schedulePackagedAutonomyOverlay(view, url, generation);"),
            page_finished.index("view.postVisualStateCallback"),
        )
        self.assertIn("OVERLAY_BOOT_DELAY_MS", self.source)
        scheduler = self.source[
            self.source.index("private void schedulePackagedAutonomyOverlay"):
            self.source.index("private void onRuntimeVisitedHistory")
        ]
        self.assertIn("mainHandler.postDelayed", scheduler)
        self.assertIn("generation != runtimeLoadGeneration", scheduler)
        self.assertIn("injectPackagedAutonomyOverlay(view, url);", scheduler)

    def test_webview_console_errors_are_logged_for_real_app_diagnostics(self):
        self.assertIn("import android.webkit.ConsoleMessage;", self.source)
        self.assertIn("public boolean onConsoleMessage(ConsoleMessage message)", self.source)
        self.assertIn('Log.e(UI_PROOF_TAG, "console "', self.source)

    def test_package_replacement_runs_one_offscreen_real_webview_mount_proof(self):
        receiver = ACTIVITY_PATH.with_name("BootReceiver.java").read_text(encoding="utf-8")
        self.assertIn("ACTION_VERIFY_HEADLESS_UI", self.service_source)
        self.assertIn("verifyHeadlessUiAsync", self.service_source)
        self.assertIn("new WebView(headlessPresentation.getContext())", self.service_source)
        self.assertIn("headless-ui-proof", self.service_source)
        self.assertIn("bundleExecutions", self.service_source)
        self.assertIn("bundleExecutions===1", self.service_source)
        self.assertIn("__NEMOTRON_LAZY_ROUTE_EXERCISED__", self.service_source)
        self.assertIn("stage:'lazy-route-loading'", self.service_source)
        self.assertIn("skillsButton.click()", self.service_source)
        self.assertIn("scriptSources", self.service_source)
        self.assertIn("sidebar-settings-button", self.service_source)
        self.assertIn("Expand sidebar", self.service_source)
        self.assertIn("codex-web-local.sidebar-collapsed.v1", self.service_source)
        self.assertIn("__NEMOTRON_PROOF_STORAGE_GUARD__", self.service_source)
        self.assertIn("nemotron-session-cleanup-card", self.service_source)
        self.assertIn("Delete all sessions and threads now", self.service_source)
        self.assertIn("floatingControls===0", self.service_source)
        self.assertIn("document.getElementById('app')", self.service_source)
        self.assertIn("childElementCount", self.service_source)
        self.assertIn("EXPECTED_UI_BUNDLE_PATH", self.service_source)
        self.assertIn("settings.setOffscreenPreRaster(true)", self.service_source)
        self.assertIn("headlessWebView.setVisibility(View.VISIBLE)", self.service_source)
        self.assertIn("headlessWebView.setLayoutParams(new FrameLayout.LayoutParams(", self.service_source)
        self.assertNotIn("headlessWebView.setLayoutParams(new ViewGroup.LayoutParams(", self.service_source)
        self.assertIn("headlessWebView.measure(", self.service_source)
        self.assertIn("headlessWebView.layout(0, 0, HEADLESS_UI_WIDTH, HEADLESS_UI_HEIGHT)", self.service_source)
        self.assertIn("headlessWebView.onResume()", self.service_source)
        self.assertIn("WebView.setWebContentsDebuggingEnabled(true)", self.service_source)
        self.assertIn("WebView.setWebContentsDebuggingEnabled(false)", self.service_source)
        self.assertIn('Log.e(HEADLESS_UI_TAG, "console source="', self.service_source)
        self.assertIn('message.message().startsWith("nemotron-startup-state ")', self.service_source)
        self.assertIn("DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY", self.service_source)
        self.assertIn("DisplayManager.VIRTUAL_DISPLAY_FLAG_PRESENTATION", self.service_source)
        self.assertIn("new Presentation(this, headlessVirtualDisplay.getDisplay())", self.service_source)
        self.assertIn("privateVirtualDisplay", self.service_source)
        self.assertIn('proof.put("physicalDisplay", displayId == Display.DEFAULT_DISPLAY)', self.service_source)
        self.assertIn("headlessPresentation.dismiss()", self.service_source)
        self.assertIn("headlessVirtualDisplay.release()", self.service_source)
        self.assertIn("headlessImageReader.close()", self.service_source)
        self.assertIn("onPageStarted(WebView view, String url, Bitmap favicon)", self.service_source)
        self.assertIn("onReceivedError(WebView view, WebResourceRequest request", self.service_source)
        self.assertIn("isExpectedHeadlessUrl(view.getUrl(), expectedUrl)", self.service_source)
        self.assertIn("verificationView.destroy()", self.service_source)
        self.assertNotIn("setContentView(headlessWebView)", self.service_source)
        self.assertNotIn("clearCache(", self.service_source)
        self.assertIn("Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)", receiver)
        self.assertIn("setAction(NemotronRuntimeService.ACTION_VERIFY_HEADLESS_UI)", receiver)

    def test_page_finished_is_single_flight_per_navigation_generation(self):
        self.assertIn("pageFinishHandledGeneration", self.source)
        page_finished = self.source[
            self.source.index("private void onRuntimePageFinished"):
            self.source.index("private void schedulePackagedAutonomyOverlay")
        ]
        self.assertIn("pageFinishHandledGeneration == generation", page_finished)
        self.assertIn("pageFinishHandledGeneration = generation", page_finished)
        load = self.source[
            self.source.index("private void loadRuntimeGui"):
            self.source.index("private void showStartingPage")
        ]
        self.assertIn("pageFinishHandledGeneration = -1L", load)

    def test_javascript_bridge_never_reads_webview_from_java_bridge_thread(self):
        bridge = self.source[
            self.source.index("public final class NemotronAutonomyBridge"):
            self.source.index("@android.annotation.TargetApi(26)")
        ]
        report = bridge[
            bridge.index("public void reportUiState"):
            bridge.index("public void refreshGui")
        ]
        self.assertIn("mainHandler.post(new Runnable()", report)
        pre_post = report[:report.index("mainHandler.post(new Runnable()")]
        self.assertNotIn("webView.getUrl()", pre_post)

    def test_overlay_url_is_real_static_javascript_even_under_service_worker_control(self):
        self.assertIn('NATIVE_OVERLAY_PATH = "/nemotron-autonomy-progress.js"', self.source)
        self.assertNotIn('NATIVE_OVERLAY_PATH = "/__nemotron-native-overlay.js"', self.source)

    def test_blank_root_probe_has_one_bounded_recovery_and_dark_fallback(self):
        self.assertIn("blankRootRecoveryAttempted", self.source)
        self.assertIn("probeStartupRoot", self.source)
        self.assertIn("native-startup-probe", self.source)
        self.assertIn("native-blank-root-recovery", self.source)
        page_finished = self.source[
            self.source.index("private void onRuntimePageFinished"):
            self.source.index("private void scheduleStartupRootProbe")
        ]
        self.assertNotIn("markGuiReady(view, url, generation);", page_finished)
        self.assertNotIn("schedulePackagedAutonomyOverlay(view, url, generation);", page_finished)
        probe = self.source[
            self.source.index("private void probeStartupRoot"):
            self.source.index("private void recoverBlankRoot")
        ]
        self.assertIn('if ("true".equals(value))', probe)
        self.assertIn("markGuiReady(view, url, generation);", probe)
        self.assertIn("schedulePackagedAutonomyOverlay(view, url, generation);", probe)
        self.assertIn("STARTUP_RECOVERY_TIMEOUT_MS", self.source)
        self.assertIn("scheduleStartupRecoveryTimeout", self.source)
        self.assertIn("showStartupFailure();", self.source)
        self.assertNotIn("clearCache(", self.source)
        self.assertNotIn("clearHistory(", self.source)

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

    def test_startup_copy_is_model_truthful_bounded_and_recovery_preserving(self):
        self.assertIn("Preparing verified model runtime", self.source)
        self.assertNotIn("Preparing Nemotron 405B", self.source)
        self.assertIn("background recovery continues", self.source)
        self.assertIn("sessions and projects preserved", self.source)
        self.assertIn("if (rawStatus.length() > 220)", self.source)
        self.assertIn("rawStatus.substring(0, 219)", self.source)

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
            self.source.index("private long postSupervisorEvent")
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
        self.assertIn('}, 250L, 250L, TimeUnit.MILLISECONDS);', self.service_source)
        self.assertIn('RINGTONE_SAMPLE_RATE = 48000', self.service_source)
        self.assertIn('RINGTONE_DURATION_MS = 3000', self.service_source)
        self.assertIn('RINGTONE_VOLUME = 0.5f', self.service_source)
        self.assertIn(
            'RINGTONE_NOTES = {880.0, 659.25, 987.77, 783.99, 1174.66, 880.0}',
            self.service_source,
        )
        self.assertIn(
            'int sampleCount = RINGTONE_SAMPLE_RATE * RINGTONE_DURATION_MS / 1000',
            self.service_source,
        )
        self.assertEqual(48000 * 3000 // 1000, 144000)
        self.assertIn('AudioAttributes.USAGE_NOTIFICATION', self.service_source)
        self.assertIn('AudioTrack.MODE_STREAM', self.service_source)
        self.assertIn('AudioTrack.getMinBufferSize(', self.service_source)
        self.assertIn('track.getPlaybackHeadPosition() < samples.length', self.service_source)
        self.assertIn('track.setVolume(RINGTONE_VOLUME)', self.service_source)
        self.assertIn('"completed".equals(outcome) || "failed".equals(outcome) || "stopped".equals(outcome)', self.service_source)
        self.assertNotIn('ToneGenerator', self.service_source)
        self.assertIn('synchronized (completionToneGuard)', self.service_source)
        self.assertIn('.putLong(COMPLETION_SEQUENCE_KEY, sequence).commit()', self.service_source)
        self.assertIn('ACTION_TERMINAL_COMPLETION.equals(intent.getAction())', self.service_source)
        self.assertIn('watchdog.execute(new Runnable()', self.service_source)
        self.assertIn('pollCompletionEvents();', self.service_source)
        self.assertIn('acknowledgeCompletionTone(supervisorPort, sequence)', self.service_source)
        self.assertIn('"http://127.0.0.1:" + supervisorPort + "/ack"', self.service_source)
        self.assertIn('contains("isolated Nemotron Autonomy runtime using OpenRouter")', self.service_source)
        self.assertIn('public void missionStarted', self.source)
        self.assertIn('postSupervisorEvent("active", safePayload)', self.source)
        self.assertIn('long sequence = postSupervisorEvent("event", safePayload)', self.source)
        self.assertIn('NemotronRuntimeService.playCompletionNow(', self.source)

    def test_screen_off_cpu_lock_is_scoped_to_authoritative_active_turns(self):
        manifest = (ROOT / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("android.permission.WAKE_LOCK", manifest)
        self.assertIn('android:permission="android.permission.DUMP"', manifest)
        self.assertIn("PowerManager.PARTIAL_WAKE_LOCK", self.service_source)
        self.assertIn('getPackageName() + ":active-turn"', self.service_source)
        self.assertIn("payload.has(\"activeTurnCount\")", self.service_source)
        self.assertIn("setActiveTurnWakeLock(reportedActiveTurns > 0)", self.service_source)
        self.assertIn("setActiveTurnWakeLock(false)", self.service_source)
        self.assertIn("activeTurnWakeLock.release()", self.service_source)
        self.assertIn("public void onTaskRemoved", self.service_source)
        supervisor = (ROOT / "nemotron_session_supervisor.py").read_text(encoding="utf-8")
        self.assertIn('"activeTurnCount": active_turn_count', supervisor)


if __name__ == "__main__":
    unittest.main()
