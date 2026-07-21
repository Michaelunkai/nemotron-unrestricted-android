package com.michaelovsky.nemotronunrestricted.isolated;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.UUID;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private static final String TERMUX_PACKAGE = "com.termux";
    private static final String TERMUX_SERVICE = "com.termux.app.RunCommandService";
    private static final String TERMUX_PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final String START_SCRIPT =
            "/data/data/com.termux/files/home/nemotron-unrestricted-app/nemotron-unrestricted-start.sh";
    private static final int DEFAULT_GUI_PORT = 5903;
    private static final int MAX_CONFIG_RESPONSE_CHARACTERS = 262144;
    private static final int DEFAULT_PROXY_PORT = 18774;
    private static final int MAX_PROXY_PORT = DEFAULT_PROXY_PORT + 100;
    private static final int DEFAULT_SUPERVISOR_PORT = 18775;
    private static final String APP_ID = "nemotron-unrestricted";
    private static final long MAIN_FRAME_TIMEOUT_MS = 20000L;
    private static final int TERMUX_PERMISSION_REQUEST = 7;
    private static final int FILE_CHOOSER_REQUEST = 8;
    private static final int MEDIA_PERMISSION_REQUEST = 9;
    private static final String WEBVIEW_PREFS = "nemotron-webview";
    private static final String LAST_ROUTE_KEY = "last-route";

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private WebView webView;
    private ValueCallback<Uri[]> fileChooserCallback;
    private PermissionRequest pendingMediaPermission;
    private volatile boolean destroyed;
    private volatile boolean readinessWorkerRunning;
    private volatile boolean resumeRuntimeProbeRunning;
    private volatile int runtimePort = DEFAULT_GUI_PORT;
    private volatile int supervisorPort = DEFAULT_SUPERVISOR_PORT;
    private volatile String supervisorSourceHash = "";
    private boolean guiLoaded;
    private boolean guiLoadInProgress;
    private long runtimeLoadGeneration;
    private String expectedRuntimeUrl = "";
    private volatile String pendingRouteSuffix = "";
    private final String bridgeToken = UUID.randomUUID().toString();

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        runtimePort = NemotronRuntimeService.getRuntimePort(this);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(10, 5, 31));
        webView.setFocusable(true);
        webView.setFocusableInTouchMode(true);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setTextZoom(100);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        if (Build.VERSION.SDK_INT >= 21) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }
        if (Build.VERSION.SDK_INT >= 26) {
            settings.setSafeBrowsingEnabled(true);
        }
        webView.addJavascriptInterface(new NemotronAutonomyBridge(), "NemotronAutonomy");

        webView.setWebViewClient(createRuntimeWebViewClient());
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                if (pendingMediaPermission != null)
                    pendingMediaPermission.deny();
                if (request == null || !isTrustedRuntimeUri(request.getOrigin())) {
                    if (request != null)
                        request.deny();
                    return;
                }
                String[] perms = request.getResources();
                boolean video = false;
                boolean audio = false;
                for (String p : perms) {
                    if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(p))
                        video = true;
                    else if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(p))
                        audio = true;
                    else {
                        request.deny();
                        return;
                    }
                }
                if (!video && !audio) {
                    request.deny();
                    return;
                }
                pendingMediaPermission = request;
                requestMediaPermissions(request, video, audio);
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (!isRuntimeUrl(view == null ? null : view.getUrl())) {
                    callback.onReceiveValue(null);
                    return true;
                }
                if (fileChooserCallback != null)
                    fileChooserCallback.onReceiveValue(null);
                fileChooserCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER_REQUEST);
                    return true;
                } catch (Exception e) {
                    fileChooserCallback = null;
                    return false;
                }
            }
        });
        setContentView(webView);

        showStartingPage(null);
        ensureTermuxPermission();
    }

    private WebViewClient createRuntimeWebViewClient() {
        if (Build.VERSION.SDK_INT >= 26) {
            try {
                Class<?> clientClass = Class.forName(
                        "com.michaelovsky.nemotronunrestricted.isolated.NemotronApi26WebViewClient",
                        true,
                        getClassLoader());
                Object client = clientClass.getDeclaredConstructor(MainActivity.class).newInstance(this);
                if (client instanceof WebViewClient)
                    return (WebViewClient) client;
            } catch (Exception ignored) {
            } catch (LinkageError ignored) {
            }
        }
        return new RuntimeWebViewClient(this);
    }

    private void onRuntimePageStarted(WebView view, String url) {
        if (view == webView && isRuntimeUrl(url) && url.equals(expectedRuntimeUrl))
            guiLoadInProgress = true;
    }

    private void onRuntimePageFinished(final WebView view, final String url) {
        final long generation = runtimeLoadGeneration;
        if (!isCurrentRuntimeNavigation(view, url, generation))
            return;
        rememberRoute(url);
        view.evaluateJavascript(
                "window.__NEMOTRON_BRIDGE_TOKEN__=" + JSONObject.quote(bridgeToken) + ";", null);
        if (Build.VERSION.SDK_INT >= 23) {
            view.postVisualStateCallback(generation, new WebView.VisualStateCallback() {
                @Override
                public void onComplete(long requestId) {
                    markGuiReady(view, url, generation);
                }
            });
        } else {
            markGuiReady(view, url, generation);
        }
    }

    private void onRuntimeVisitedHistory(WebView view, String url) {
        if (view == webView)
            rememberRoute(url);
    }

    private boolean onRuntimeNavigation(WebView view, Uri uri) {
        if (view != webView)
            return true;
        return handleNavigation(uri);
    }

    private boolean isCurrentMainFrameRequest(WebView view, WebResourceRequest request) {
        return view != null && view == webView && request != null && request.isForMainFrame()
                && isTrustedRuntimeUri(request.getUrl());
    }

    private void onRuntimeReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
        if (isCurrentMainFrameRequest(view, request) && isRecoverableMainFrameError(error))
            recoverGui("Connection interrupted");
    }

    private void onRuntimeReceivedHttpError(
            WebView view, WebResourceRequest request, WebResourceResponse response) {
        if (isCurrentMainFrameRequest(view, request) && response != null && response.getStatusCode() >= 500)
            recoverGui("Workspace temporarily unavailable");
    }

    private boolean isRecoverableMainFrameError(WebResourceError error) {
        if (error == null)
            return false;
        int code = error.getErrorCode();
        return code == WebViewClient.ERROR_HOST_LOOKUP || code == WebViewClient.ERROR_CONNECT
                || code == WebViewClient.ERROR_TIMEOUT || code == WebViewClient.ERROR_UNKNOWN;
    }

    private void recoverGui(String reason) {
        if (destroyed || (!guiLoaded && !guiLoadInProgress))
            return;
        rememberCurrentRouteSynchronously();
        if (webView != null)
            webView.stopLoading();
        guiLoaded = false;
        guiLoadInProgress = false;
        runtimeLoadGeneration++;
        expectedRuntimeUrl = "";
        showStartingPage("Recovering: " + reason);
        waitForRuntimeOnce();
    }

    private boolean isCurrentRuntimeNavigation(WebView view, String url, long generation) {
        if (destroyed || view == null || view != webView || generation != runtimeLoadGeneration
                || !guiLoadInProgress || expectedRuntimeUrl.length() == 0 || !expectedRuntimeUrl.equals(url)
                || !isRuntimeUrl(url))
            return false;
        String current = view.getUrl();
        return isRuntimeUrl(current);
    }

    private void markGuiReady(WebView view, String url, long generation) {
        if (!isCurrentRuntimeNavigation(view, url, generation))
            return;
        guiLoadInProgress = false;
        guiLoaded = true;
        view.requestFocus(View.FOCUS_DOWN);
    }

    private void loadRuntimeGui() {
        if (destroyed || webView == null)
            return;
        guiLoaded = false;
        guiLoadInProgress = true;
        final long generation = ++runtimeLoadGeneration;
        expectedRuntimeUrl = runtimeWebUrl() + restoredRouteSuffix();
        webView.loadUrl(expectedRuntimeUrl);
        mainHandler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (!destroyed && generation == runtimeLoadGeneration && guiLoadInProgress && !guiLoaded) {
                    recoverGui("Workspace load timed out");
                }
            }
        }, MAIN_FRAME_TIMEOUT_MS);
    }

    private void showStartingPage(String status) {
        if (destroyed || webView == null)
            return;
        expectedRuntimeUrl = "";
        String safe = status == null ? "Preparing Nemotron 405B · Android · Web · Apps · Files"
                                     : status.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
        String html = "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>html,body{height:100%;margin:0;background:#0a051f;color:#eefcf3;font-family:sans-serif}"
                + ".box{height:100%;display:flex;align-items:center;justify-content:center;text-align:center}.mark{"
                  + "color:#9cff47;font-size:28px;font-weight:700}"
                + ".sub{margin-top:12px;color:#94a3b8;font-size:15px}</style></head><body><div class='box'><div>"
                + "<div class='mark'>NEMOTRON UNRESTRICTED</div><div class='sub'>" + safe + "</div>"
                + "</div></div></body></html>";
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }

    private void waitForRuntimeOnce() {
        if (readinessWorkerRunning)
            return;
        readinessWorkerRunning = true;
        new Thread(new Runnable() {
            @Override
            public void run() {
                boolean ready = false;
                int attempt = 0;
                while (!destroyed) {
                    if (runtimeIsReady()) {
                        ready = true;
                        break;
                    }
                    attempt++;
                    if (attempt % 15 == 0) {
                        final int elapsedSeconds = attempt;
                        mainHandler.post(new Runnable() {
                            @Override public void run() {
                                if (!destroyed && !guiLoaded && !guiLoadInProgress) {
                                    showStartingPage("Repairing isolated runtime · " + elapsedSeconds
                                            + "s · sessions and projects preserved");
                                    startRuntimeWatchdog();
                                }
                            }
                        });
                    }
                    try {
                        Thread.sleep(1000L);
                    } catch (InterruptedException ignored) {
                        break;
                    }
                }
                final boolean finalReady = ready;
                readinessWorkerRunning = false;
                if (destroyed)
                    return;
                mainHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (destroyed || guiLoaded || guiLoadInProgress)
                            return;
                        if (finalReady)
                            loadRuntimeGui();
                    }
                });
            }
        }, "nemotron-codex-readiness").start();
    }

    private boolean runtimeIsReady() {
        try {
            return discoverRuntimePort();
        } catch (Exception ignored) {
            return false;
        }
    }

    private void showStartupFailure() {
        if (destroyed || webView == null)
            return;
        expectedRuntimeUrl = "";
        String html = "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>html,body{height:100%;margin:0;background:#0a051f;color:#eefcf3;font-family:sans-serif}"
                + ".box{height:100%;display:flex;align-items:center;justify-content:center;text-align:center;padding:"
                  + "28px;box-sizing:border-box}"
                + ".title{color:#9cff47;font-size:23px;font-weight:700}.sub{margin-top:12px;color:#94a3b8}"
                + ".retry{margin-top:20px;border:1px solid "
                  + "#9cff47;border-radius:999px;background:#1a2e14;color:#dfffc9;padding:12px "
                  + "20px;font-weight:700}</style></head><body>"
                + "<div class='box'><div><div class='title'>Nemotron workspace did not start</div>"
                + "<div class='sub'>The isolated runtime is repairing itself. Your other Codex apps are "
                  + "unaffected.</div>"
                + "<script>window.__NEMOTRON_BRIDGE_TOKEN__=" + JSONObject.quote(bridgeToken) + ";</script>"
                + ("<button class='retry' "
                   + "onclick='NemotronAutonomy.refreshGui(window.__NEMOTRON_BRIDGE_TOKEN__)'>Retry "
                   + "now</button></div></div>")
                + "</body></html>";
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }

    private void requestMediaPermissions(PermissionRequest request, boolean video, boolean audio) {
        ArrayList<String> permissions = new ArrayList<String>();
        if (video && checkSelfPermission(android.Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(android.Manifest.permission.CAMERA);
        }
        if (audio
                && checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(android.Manifest.permission.RECORD_AUDIO);
        }
        if (permissions.isEmpty()) {
            request.grant(request.getResources());
            pendingMediaPermission = null;
            return;
        }
        requestPermissions(permissions.toArray(new String[permissions.size()]), MEDIA_PERMISSION_REQUEST);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == TERMUX_PERMISSION_REQUEST) {
            if (grantResults.length == 1 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startRuntimeWatchdog();
                waitForRuntimeOnce();
            } else {
                showStartingPage("Termux command permission is required to start the isolated runtime");
            }
        } else if (requestCode == MEDIA_PERMISSION_REQUEST && pendingMediaPermission != null) {
            boolean granted = grantResults.length > 0 && permissions.length == grantResults.length
                    && isTrustedRuntimeUri(pendingMediaPermission.getOrigin());
            for (int r : grantResults) {
                if (r != PackageManager.PERMISSION_GRANTED) {
                    granted = false;
                    break;
                }
            }
            if (granted)
                pendingMediaPermission.grant(pendingMediaPermission.getResources());
            else
                pendingMediaPermission.deny();
            pendingMediaPermission = null;
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (destroyed || webView == null)
            return;
        if (!ensureTermuxPermission())
            return;
        startRuntimeWatchdog();
        String current = webView.getUrl();
        if (!isRuntimeUrl(current)) {
            guiLoaded = false;
            waitForRuntimeOnce();
        } else {
            verifyRuntimeEndpointAfterResume();
        }
    }

    private void verifyRuntimeEndpointAfterResume() {
        if (destroyed || webView == null || resumeRuntimeProbeRunning || !isRuntimeUrl(webView.getUrl()))
            return;
        final int loadedPort = runtimePort;
        resumeRuntimeProbeRunning = true;
        new Thread(new Runnable() {
            @Override
            public void run() {
                final boolean ready = discoverRuntimePort();
                final int discoveredPort = runtimePort;
                mainHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        resumeRuntimeProbeRunning = false;
                        if (destroyed || webView == null || !ready)
                            return;
                        if (discoveredPort != loadedPort || !isRuntimeUrl(webView.getUrl())) {
                            guiLoaded = false;
                            guiLoadInProgress = false;
                            runtimeLoadGeneration++;
                            expectedRuntimeUrl = "";
                            showStartingPage("Restoring the isolated runtime on its verified port");
                            loadRuntimeGui();
                        }
                    }
                });
            }
        }, "nemotron-resume-runtime-probe").start();
    }

    private String runtimeWebUrl() {
        return "http://127.0.0.1:" + runtimePort + "/";
    }

    private String routeSuffix(String url) {
        if (!isRuntimeUrl(url))
            return null;
        Uri uri = Uri.parse(url);
        StringBuilder suffix = new StringBuilder();
        String path = uri.getEncodedPath();
        if (path != null && path.length() > 1)
            suffix.append(path.substring(1));
        String query = uri.getEncodedQuery();
        if (query != null && query.length() > 0)
            suffix.append('?').append(query);
        String fragment = uri.getEncodedFragment();
        if (fragment != null && fragment.length() > 0)
            suffix.append('#').append(fragment);
        return suffix.length() <= 4096 ? suffix.toString() : "";
    }

    private void rememberRoute(String url) {
        String suffix = routeSuffix(url);
        if (suffix == null)
            return;
        pendingRouteSuffix = suffix;
        getSharedPreferences(WEBVIEW_PREFS, MODE_PRIVATE).edit()
                .putString(LAST_ROUTE_KEY, pendingRouteSuffix).apply();
    }

    private void rememberCurrentRouteSynchronously() {
        WebView currentView = webView;
        if (currentView != null) {
            try {
                String suffix = routeSuffix(currentView.getUrl());
                if (suffix != null)
                    pendingRouteSuffix = suffix;
            } catch (RuntimeException ignored) {
            }
        }
        String suffix = pendingRouteSuffix;
        if (suffix == null || suffix.length() > 4096 || suffix.startsWith("//")
                || suffix.contains("\\") || suffix.contains("\n") || suffix.contains("\r"))
            suffix = "";
        getSharedPreferences(WEBVIEW_PREFS, MODE_PRIVATE).edit()
                .putString(LAST_ROUTE_KEY, suffix).commit();
    }

    private String restoredRouteSuffix() {
        String suffix = pendingRouteSuffix;
        if (suffix == null || suffix.length() == 0)
            suffix = getSharedPreferences(WEBVIEW_PREFS, MODE_PRIVATE).getString(LAST_ROUTE_KEY, "");
        if (suffix == null || suffix.length() > 4096 || suffix.startsWith("//")
                || suffix.contains("\\") || suffix.contains("\n") || suffix.contains("\r"))
            return "";
        return suffix;
    }

    private boolean isRuntimeUrl(String url) {
        return url != null && isTrustedRuntimeUri(Uri.parse(url));
    }

    private boolean isTrustedRuntimeUri(Uri uri) {
        return uri != null && "http".equalsIgnoreCase(uri.getScheme()) && "127.0.0.1".equals(uri.getHost())
                && uri.getPort() == runtimePort;
    }

    private boolean handleNavigation(Uri uri) {
        if (isTrustedRuntimeUri(uri))
            return false;
        if (uri == null)
            return true;
        String scheme = uri.getScheme();
        if ("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme)) {
            try {
                Intent external = new Intent(Intent.ACTION_VIEW, uri);
                external.addCategory(Intent.CATEGORY_BROWSABLE);
                startActivity(external);
            } catch (Exception ignored) {
            }
        }
        return true;
    }

    private String sanitizeCompletionPayload(String payload) {
        try {
            JSONObject input = new JSONObject(payload);
            String turnId = input.optString("turnId", "").trim();
            String outcome = input.optString("outcome", "").trim().toLowerCase();
            if (turnId.length() == 0 || turnId.length() > 256
                    || !("completed".equals(outcome) || "failed".equals(outcome) || "stopped".equals(outcome)))
                return null;
            JSONObject safe = new JSONObject();
            safe.put("turnId", turnId);
            safe.put("threadId", boundedText(input.optString("threadId", ""), 256));
            safe.put("outcome", outcome);
            safe.put("durationMs", boundedCount(input.optLong("durationMs", 0L)));
            safe.put("effort", boundedText(input.optString("effort", ""), 32));
            safe.put("actionCount", boundedCount(input.optLong("actionCount", 0L)));
            safe.put("completedActions", boundedCount(input.optLong("completedActions", 0L)));
            safe.put("failureCount", boundedCount(input.optLong("failureCount", 0L)));
            safe.put("plannedSteps", boundedCount(input.optLong("plannedSteps", 0L)));
            return safe.toString();
        } catch (Exception ignored) {
            return null;
        }
    }

    private String sanitizeActivePayload(String payload) {
        try {
            JSONObject input = new JSONObject(payload);
            String turnId = boundedText(input.optString("turnId", ""), 256);
            String threadId = boundedText(input.optString("threadId", ""), 256);
            if (turnId.length() == 0 || threadId.length() == 0)
                return null;
            JSONObject safe = new JSONObject();
            safe.put("turnId", turnId);
            safe.put("threadId", threadId);
            safe.put("effort", boundedText(input.optString("effort", ""), 32));
            safe.put("startedAt", boundedCount(input.optLong("startedAt", 0L)));
            return safe.toString();
        } catch (Exception ignored) {
            return null;
        }
    }

    private String boundedText(String value, int limit) {
        String safe = value == null ? "" : value.trim();
        return safe.length() <= limit ? safe : safe.substring(0, limit);
    }

    private long boundedCount(long value) {
        return Math.max(0L, Math.min(value, 1000000L));
    }

    private boolean supervisorIsOurs(int port, String expectedSourceHash) {
        if (!isSha256(expectedSourceHash))
            return false;
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL("http://127.0.0.1:" + port + "/health").openConnection();
            connection.setConnectTimeout(500);
            connection.setReadTimeout(1000);
            connection.setUseCaches(false);
            if (connection.getResponseCode() != 200)
                return false;
            BufferedReader reader =
                    new BufferedReader(new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && body.length() < 4096) body.append(line);
            reader.close();
            JSONObject health = new JSONObject(body.toString());
            return "ok".equals(health.optString("status")) && APP_ID.equals(health.optString("app"))
                    && health.optInt("port", 0) == port
                    && expectedSourceHash.equals(health.optString("sourceSha256"));
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null)
                connection.disconnect();
        }
    }

    private void postSupervisorEvent(String endpoint, String payload) {
        int selected = supervisorIsOurs(supervisorPort, supervisorSourceHash) ? supervisorPort : 0;
        if (selected == 0 || !("event".equals(endpoint) || "active".equals(endpoint)))
            return;
        HttpURLConnection connection = null;
        try {
            byte[] body = payload.getBytes(StandardCharsets.UTF_8);
            connection = (HttpURLConnection) new URL("http://127.0.0.1:" + selected + "/" + endpoint).openConnection();
            connection.setConnectTimeout(1000);
            connection.setReadTimeout(2000);
            connection.setUseCaches(false);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(body.length);
            OutputStream output = connection.getOutputStream();
            output.write(body);
            output.close();
            if (connection.getResponseCode() == 200)
                supervisorPort = selected;
        } catch (Exception ignored) {
        } finally {
            if (connection != null)
                connection.disconnect();
        }
    }

    private boolean ensureTermuxPermission() {
        if (Build.VERSION.SDK_INT >= 23
                && checkSelfPermission(TERMUX_PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {TERMUX_PERMISSION}, TERMUX_PERMISSION_REQUEST);
            return false;
        }
        return true;
    }

    private JSONObject readJsonResponse(HttpURLConnection connection, int maximumCharacters) throws Exception {
        if (connection.getResponseCode() != 200)
            return null;
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
        StringBuilder body = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            if (body.length() + line.length() > maximumCharacters) {
                reader.close();
                return null;
            }
            body.append(line);
        }
        reader.close();
        return new JSONObject(body.toString());
    }

    private boolean guiConfigIsOurs(int guiPort) {
        HttpURLConnection connection = null;
        try {
            byte[] request = "{\"method\":\"config/read\",\"params\":{}}"
                    .getBytes(StandardCharsets.UTF_8);
            connection = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + guiPort + "/codex-api/rpc").openConnection();
            connection.setConnectTimeout(1000);
            connection.setReadTimeout(2000);
            connection.setUseCaches(false);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(request.length);
            OutputStream output = connection.getOutputStream();
            output.write(request);
            output.close();
            JSONObject payload = readJsonResponse(connection, MAX_CONFIG_RESPONSE_CHARACTERS);
            JSONObject result = payload == null ? null : payload.optJSONObject("result");
            JSONObject config = result == null ? null : result.optJSONObject("config");
            JSONObject providers = config == null ? null : config.optJSONObject("model_providers");
            JSONObject custom = providers == null ? null : providers.optJSONObject("custom_endpoint");
            String expectedBaseUrl = "http://127.0.0.1:" + guiPort + "/codex-api/custom-proxy/v1";
            return config != null && custom != null
                    && "custom_endpoint".equals(config.optString("model_provider"))
                    && expectedBaseUrl.equals(custom.optString("base_url"));
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null)
                connection.disconnect();
        }
    }

    private boolean freeModeIsOurs(int guiPort, int proxyPort) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + guiPort + "/codex-api/free-mode/status").openConnection();
            connection.setConnectTimeout(1000);
            connection.setReadTimeout(2000);
            connection.setUseCaches(false);
            JSONObject status = readJsonResponse(connection, 16384);
            return status != null && status.optBoolean("enabled", false)
                    && "custom".equals(status.optString("provider"))
                    && "chat".equals(status.optString("wireApi"))
                    && ("http://127.0.0.1:" + proxyPort + "/v1")
                            .equals(status.optString("customBaseUrl"));
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null)
                connection.disconnect();
        }
    }

    private boolean guiIdentityIsOurs(int guiPort, int proxyPort) {
        return guiConfigIsOurs(guiPort) && freeModeIsOurs(guiPort, proxyPort);
    }

    private boolean isPort(int port) {
        return port >= 1 && port <= 65535;
    }

    private boolean isSha256(String value) {
        return value != null && value.matches("[0-9a-f]{64}");
    }

    private boolean isCredentialFingerprint(String value) {
        return value != null && value.matches("[0-9a-f]{16,64}");
    }

    private boolean discoverRuntimePort() {
        for (int proxyPort = DEFAULT_PROXY_PORT; proxyPort <= MAX_PROXY_PORT; proxyPort++) {
            HttpURLConnection connection = null;
            try {
                connection =
                        (HttpURLConnection) new URL("http://127.0.0.1:" + proxyPort + "/vault-health").openConnection();
                connection.setConnectTimeout(350);
                connection.setReadTimeout(750);
                connection.setUseCaches(false);
                JSONObject health = readJsonResponse(connection, 16384);
                String expectedBaseUrl = "http://127.0.0.1:" + proxyPort + "/v1";
                Object credentialConfigured = health == null ? null : health.opt("credentialConfigured");
                if (health == null || !"ok".equals(health.optString("status"))
                        || !APP_ID.equals(health.optString("app"))
                        || !"OpenRouter".equals(health.optString("provider"))
                        || health.optInt("proxyPort", 0) != proxyPort
                        || !expectedBaseUrl.equals(health.optString("effectiveBaseUrl"))
                        || !(credentialConfigured instanceof Boolean)
                        || !isSha256(health.optString("sourceHash"))
                        || !isCredentialFingerprint(health.optString("credentialSourceFingerprint")))
                    continue;
                int discovered = health.optInt("guiPort", 0);
                int discoveredSupervisor = health.optInt("supervisorPort", 0);
                String discoveredSupervisorHash = health.optString("supervisorSourceHash");
                if (!isPort(discovered) || !isPort(discoveredSupervisor)
                        || discovered == proxyPort || discoveredSupervisor == proxyPort
                        || discoveredSupervisor == discovered || !isSha256(discoveredSupervisorHash)
                        || !guiIdentityIsOurs(discovered, proxyPort)
                        || !supervisorIsOurs(discoveredSupervisor, discoveredSupervisorHash))
                    continue;
                runtimePort = discovered;
                supervisorPort = discoveredSupervisor;
                supervisorSourceHash = discoveredSupervisorHash;
                NemotronRuntimeService.rememberRuntimeEndpoint(this, discovered, proxyPort, discoveredSupervisor);
                return true;
            } catch (Exception ignored) {
            } finally {
                if (connection != null)
                    connection.disconnect();
            }
        }
        return false;
    }

    private void startRuntimeWatchdog() {
        Intent service = new Intent(this, NemotronRuntimeService.class);
        service.putExtra("reason", "activity-resumed");
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(service);
        } else {
            startService(service);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST && fileChooserCallback != null) {
            Uri[] result =
                    resultCode == RESULT_OK ? WebChromeClient.FileChooserParams.parseResult(resultCode, data) : null;
            fileChooserCallback.onReceiveValue(result);
            fileChooserCallback = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack())
            webView.goBack();
        else
            super.onBackPressed();
    }

    private boolean handleRuntimeRendererGone(final WebView view) {
        if (view == null)
            return true;
        final boolean ownedView = view == webView;
        if (ownedView) {
            rememberCurrentRouteSynchronously();
            guiLoaded = false;
            guiLoadInProgress = false;
            runtimeLoadGeneration++;
            expectedRuntimeUrl = "";
            webView = null;
        }
        try {
            ViewParent parent = view.getParent();
            if (parent instanceof ViewGroup)
                ((ViewGroup) parent).removeView(view);
        } catch (RuntimeException ignored) {
        }
        try {
            view.removeJavascriptInterface("NemotronAutonomy");
            view.setWebChromeClient(null);
            view.setWebViewClient(null);
        } catch (RuntimeException ignored) {
        }
        try {
            view.destroy();
        } catch (RuntimeException ignored) {
        }
        if (ownedView && !destroyed) {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    if (!destroyed && webView == null)
                        recreate();
                }
            });
        }
        return true;
    }

    @Override
    protected void onPause() {
        rememberCurrentRouteSynchronously();
        super.onPause();
    }

    @Override
    protected void onStop() {
        rememberCurrentRouteSynchronously();
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        rememberCurrentRouteSynchronously();
        destroyed = true;
        mainHandler.removeCallbacksAndMessages(null);
        if (fileChooserCallback != null)
            fileChooserCallback.onReceiveValue(null);
        if (pendingMediaPermission != null)
            pendingMediaPermission.deny();
        if (webView != null) {
            webView.stopLoading();
            webView.removeJavascriptInterface("NemotronAutonomy");
            webView.setWebChromeClient(null);
            webView.setWebViewClient(null);
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    static class RuntimeWebViewClient extends WebViewClient {
        private final MainActivity owner;

        RuntimeWebViewClient(MainActivity owner) {
            this.owner = owner;
        }

        protected final boolean rendererGone(WebView view) {
            return owner.handleRuntimeRendererGone(view);
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            owner.onRuntimePageStarted(view, url);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            owner.onRuntimePageFinished(view, url);
        }

        @Override
        public void doUpdateVisitedHistory(WebView view, String url, boolean isReload) {
            owner.onRuntimeVisitedHistory(view, url);
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return request != null && owner.onRuntimeNavigation(view, request.getUrl());
        }

        @SuppressWarnings("deprecation")
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return owner.onRuntimeNavigation(view, Uri.parse(url));
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            owner.onRuntimeReceivedError(view, request, error);
        }

        @Override
        public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
            owner.onRuntimeReceivedHttpError(view, request, response);
        }
    }

    public final class NemotronAutonomyBridge {
        @JavascriptInterface
        public void refreshGui(String token) {
            if (!bridgeToken.equals(token))
                return;
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    if (!destroyed && webView != null) {
                        guiLoaded = false;
                        guiLoadInProgress = false;
                        waitForRuntimeOnce();
                    }
                }
            });
        }

        @JavascriptInterface
        public void missionStarted(String token, String payload) {
            if (!bridgeToken.equals(token) || payload == null || payload.length() > 4096 || webView == null
                    || !isRuntimeUrl(webView.getUrl()))
                return;
            final String safePayload = sanitizeActivePayload(payload);
            if (safePayload == null)
                return;
            new Thread(new Runnable() {
                @Override
                public void run() {
                    postSupervisorEvent("active", safePayload);
                }
            }, "nemotron-active-turn-report").start();
        }

        @JavascriptInterface
        public void missionComplete(String token, String payload) {
            if (!bridgeToken.equals(token) || payload == null || payload.length() > 16384 || webView == null
                    || !isRuntimeUrl(webView.getUrl()))
                return;
            final String safePayload = sanitizeCompletionPayload(payload);
            if (safePayload == null)
                return;
            new Thread(new Runnable() {
                @Override
                public void run() {
                    postSupervisorEvent("event", safePayload);
                }
            }, "nemotron-completion-report").start();
        }
    }
}

@android.annotation.TargetApi(26)
final class NemotronApi26WebViewClient extends MainActivity.RuntimeWebViewClient {
    public NemotronApi26WebViewClient(MainActivity owner) {
        super(owner);
    }

    @Override
    public boolean onRenderProcessGone(WebView view, android.webkit.RenderProcessGoneDetail detail) {
        return rendererGone(view);
    }
}
