package com.michaelovsky.nemotronunrestricted.isolated;

import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Presentation;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.media.Image;
import android.media.ImageReader;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;
import android.view.View;
import android.view.Display;
import android.widget.FrameLayout;
import android.webkit.ConsoleMessage;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;
import org.json.JSONArray;
import org.json.JSONTokener;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class NemotronRuntimeService extends Service {
    private static final String TAG = "NemotronRuntimeService";
    private static final String HEADLESS_UI_TAG = "NemotronHeadlessProof";
    private static final String CHANNEL_ID = "nemotron-unrestricted-runtime";
    private static final int NOTIFICATION_ID = 5903;
    private static final String TERMUX_PACKAGE = "com.termux";
    private static final String TERMUX_SERVICE = "com.termux.app.RunCommandService";
    private static final String TERMUX_PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final String START_SCRIPT = "/data/data/com.termux/files/home/nemotron-unrestricted-app/nemotron-unrestricted-start.sh";
    private static final String PROJECT_ROOT = "/data/data/com.termux/files/home/nemotron-unrestricted-app";
    private static final String PREFS = "nemotron-runtime";
    private static final String GUI_PORT_KEY = "gui-port";
    private static final String PROXY_PORT_KEY = "proxy-port";
    private static final String SUPERVISOR_PORT_KEY = "supervisor-port";
    private static final String COMPLETION_SEQUENCE_KEY = "completion-sequence";
    private static final int DEFAULT_GUI_PORT = 5903;
    private static final int DEFAULT_PROXY_PORT = 18774;
    private static final int MAX_PROXY_PORT = DEFAULT_PROXY_PORT + 100;
    private static final int MAX_CONFIG_RESPONSE_CHARACTERS = 262144;
    private static final String APP_ID = "nemotron-unrestricted";
    static final String ACTION_VERIFY_HEADLESS_UI =
            "com.michaelovsky.nemotronunrestricted.isolated.VERIFY_HEADLESS_UI";
    private static final String EXPECTED_UI_BUNDLE_PATH = "/assets/index-BjdL8GKN.js";
    private static final long HEADLESS_UI_TIMEOUT_MS = 30000L;
    private static final int HEADLESS_UI_MAX_PROBES = 30;
    private static final int HEADLESS_UI_WIDTH = 1080;
    private static final int HEADLESS_UI_HEIGHT = 1920;
    private static final int RINGTONE_SAMPLE_RATE = 48000;
    private static final int RINGTONE_DURATION_MS = 3000;
    private static final float RINGTONE_VOLUME = 0.5f;
    private static final double[] RINGTONE_NOTES = {880.0, 659.25, 987.77, 783.99, 1174.66, 880.0};
    private static final String ACTION_TERMINAL_COMPLETION =
            "com.michaelovsky.nemotronunrestricted.isolated.TERMINAL_COMPLETION";
    private static final String EXTRA_TERMINAL_SEQUENCE = "terminal-sequence";
    private static final String EXTRA_SUPERVISOR_PORT = "supervisor-port";

    private ScheduledExecutorService watchdog;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean runtimeStartQueued = new AtomicBoolean(false);
    private long lastRuntimeDispatchAt;
    private String lastNotificationText = "";
    private volatile boolean lastCredentialConfigured;
    private final Object wakeLockGuard = new Object();
    private final Object completionToneGuard = new Object();
    private PowerManager.WakeLock activeTurnWakeLock;
    private volatile int activeTurnCount;
    private WebView headlessWebView;
    private ImageReader headlessImageReader;
    private VirtualDisplay headlessVirtualDisplay;
    private Presentation headlessPresentation;
    private FrameLayout headlessPresentationRoot;
    private boolean headlessUiVerificationRunning;
    private boolean headlessPageFinished;
    private int headlessConsoleErrorCount;
    private String headlessLastConsoleError = "";
    private String headlessExpectedUrl = "";

    @Override public void onCreate() {
        super.onCreate();
        createChannel();
        startForeground(NOTIFICATION_ID, buildNotification("Protecting isolated runtime"));
        PowerManager powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (powerManager != null) {
            activeTurnWakeLock = powerManager.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    getPackageName() + ":active-turn");
            activeTurnWakeLock.setReferenceCounted(false);
        }
        watchdog = Executors.newScheduledThreadPool(2);
        watchdog.scheduleWithFixedDelay(new Runnable() {
            @Override public void run() { ensureRuntime(); }
        }, 0L, 15L, TimeUnit.SECONDS);
        watchdog.scheduleWithFixedDelay(new Runnable() {
            @Override public void run() { pollCompletionEvents(); }
        }, 250L, 250L, TimeUnit.MILLISECONDS);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        Log.i(TAG, "Starting Nemotron Unrestricted runtime");
        dispatchTermuxRuntime();
        if (intent != null && ACTION_VERIFY_HEADLESS_UI.equals(intent.getAction())) {
            verifyHeadlessUiAsync();
        }
        if (intent != null && ACTION_TERMINAL_COMPLETION.equals(intent.getAction())) {
            final long sequence = intent.getLongExtra(EXTRA_TERMINAL_SEQUENCE, 0L);
            final int selectedSupervisorPort = intent.getIntExtra(EXTRA_SUPERVISOR_PORT, 0);
            if (sequence > 0L && isPort(selectedSupervisorPort) && watchdog != null) {
                watchdog.execute(new Runnable() {
                    @Override public void run() {
                        rememberRuntimeEndpoint(
                                NemotronRuntimeService.this,
                                getRuntimePort(NemotronRuntimeService.this),
                                getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                                        .getInt(PROXY_PORT_KEY, DEFAULT_PROXY_PORT),
                                selectedSupervisorPort);
                        pollCompletionEvents();
                    }
                });
            }
        }
        return START_STICKY;
    }

    @Override public void onDestroy() {
        if (watchdog != null) watchdog.shutdownNow();
        mainHandler.removeCallbacksAndMessages(null);
        destroyHeadlessUiVerification();
        setActiveTurnWakeLock(false);
        super.onDestroy();
    }

    @Override public void onTaskRemoved(Intent rootIntent) {
        dispatchTermuxRuntime();
        super.onTaskRemoved(rootIntent);
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    public static int getRuntimePort(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getInt(GUI_PORT_KEY, DEFAULT_GUI_PORT);
    }

    public static void rememberRuntimePort(Context context, int port) {
        if (port >= 1 && port <= 65535) {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putInt(GUI_PORT_KEY, port).apply();
        }
    }

    public static void rememberRuntimeEndpoint(Context context, int guiPort, int proxyPort, int supervisorPort) {
        if (!isPort(guiPort) || !isPort(proxyPort) || !isPort(supervisorPort)) return;
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putInt(GUI_PORT_KEY, guiPort)
                .putInt(PROXY_PORT_KEY, proxyPort)
                .putInt(SUPERVISOR_PORT_KEY, supervisorPort)
                .apply();
    }

    public static void playCompletionNow(Context context, int supervisorPort, long sequence) {
        if (context == null || !isPort(supervisorPort) || sequence < 1L) return;
        Intent intent = new Intent(context, NemotronRuntimeService.class)
                .setAction(ACTION_TERMINAL_COMPLETION)
                .putExtra(EXTRA_TERMINAL_SEQUENCE, sequence)
                .putExtra(EXTRA_SUPERVISOR_PORT, supervisorPort);
        context.startService(intent);
    }

    private void verifyHeadlessUiAsync() {
        if (headlessUiVerificationRunning || watchdog == null || watchdog.isShutdown()) return;
        headlessUiVerificationRunning = true;
        watchdog.execute(new Runnable() {
            @Override public void run() {
                int selectedPort = 0;
                for (int attempt = 0; attempt < 12 && selectedPort == 0; attempt++) {
                    selectedPort = discoverGuiPort();
                    if (selectedPort == 0) SystemClock.sleep(500L);
                }
                final int verifiedPort = selectedPort;
                mainHandler.post(new Runnable() {
                    @Override public void run() {
                        if (verifiedPort == 0) {
                            logHeadlessUiFailure("runtime-unavailable");
                            headlessUiVerificationRunning = false;
                            return;
                        }
                        startHeadlessUiVerification(verifiedPort);
                    }
                });
            }
        });
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void startHeadlessUiVerification(int guiPort) {
        if (!headlessUiVerificationRunning || headlessWebView != null || !isPort(guiPort)) return;
        try {
            WebView.setWebContentsDebuggingEnabled(true);
            DisplayManager displayManager = (DisplayManager) getSystemService(Context.DISPLAY_SERVICE);
            if (displayManager == null) throw new IllegalStateException("display-manager-unavailable");
            headlessImageReader = ImageReader.newInstance(
                    HEADLESS_UI_WIDTH, HEADLESS_UI_HEIGHT, PixelFormat.RGBA_8888, 2);
            headlessImageReader.setOnImageAvailableListener(new ImageReader.OnImageAvailableListener() {
                @Override public void onImageAvailable(ImageReader reader) {
                    Image image = null;
                    try {
                        image = reader.acquireLatestImage();
                    } catch (RuntimeException ignored) {
                    } finally {
                        if (image != null) image.close();
                    }
                }
            }, mainHandler);
            headlessVirtualDisplay = displayManager.createVirtualDisplay(
                    "NemotronHeadlessProof",
                    HEADLESS_UI_WIDTH,
                    HEADLESS_UI_HEIGHT,
                    getResources().getDisplayMetrics().densityDpi,
                    headlessImageReader.getSurface(),
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY
                            | DisplayManager.VIRTUAL_DISPLAY_FLAG_PRESENTATION);
            if (headlessVirtualDisplay == null || headlessVirtualDisplay.getDisplay() == null) {
                throw new IllegalStateException("virtual-display-unavailable");
            }
            headlessPresentation = new Presentation(this, headlessVirtualDisplay.getDisplay());
            headlessPresentationRoot = new FrameLayout(headlessPresentation.getContext());
            headlessWebView = new WebView(headlessPresentation.getContext());
            headlessPresentationRoot.addView(headlessWebView, new FrameLayout.LayoutParams(
                    HEADLESS_UI_WIDTH, HEADLESS_UI_HEIGHT));
            headlessPresentation.setContentView(headlessPresentationRoot);
            headlessPresentation.show();
            WebSettings settings = headlessWebView.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setDatabaseEnabled(true);
            settings.setAllowFileAccess(false);
            settings.setAllowContentAccess(true);
            settings.setAllowFileAccessFromFileURLs(false);
            settings.setAllowUniversalAccessFromFileURLs(false);
            settings.setCacheMode(WebSettings.LOAD_DEFAULT);
            if (Build.VERSION.SDK_INT >= 21) {
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
            }
            if (Build.VERSION.SDK_INT >= 23) {
                settings.setOffscreenPreRaster(true);
            }
            if (Build.VERSION.SDK_INT >= 26) {
                settings.setSafeBrowsingEnabled(true);
            }
            headlessWebView.setVisibility(View.VISIBLE);
            headlessWebView.setLayoutParams(new FrameLayout.LayoutParams(
                    HEADLESS_UI_WIDTH, HEADLESS_UI_HEIGHT));
            headlessWebView.measure(
                    View.MeasureSpec.makeMeasureSpec(HEADLESS_UI_WIDTH, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(HEADLESS_UI_HEIGHT, View.MeasureSpec.EXACTLY));
            headlessWebView.layout(0, 0, HEADLESS_UI_WIDTH, HEADLESS_UI_HEIGHT);
            headlessWebView.onResume();
            headlessConsoleErrorCount = 0;
            headlessLastConsoleError = "";
            headlessPageFinished = false;
            headlessExpectedUrl = "http://127.0.0.1:" + guiPort
                    + "/?nemotron-headless-self-test=4.9.2";
            headlessWebView.setWebChromeClient(new WebChromeClient() {
                @Override public boolean onConsoleMessage(ConsoleMessage message) {
                    if (message != null && message.message() != null
                            && message.message().startsWith("nemotron-startup-state ")) {
                        Log.i(HEADLESS_UI_TAG, message.message());
                    }
                    if (message != null && message.messageLevel() == ConsoleMessage.MessageLevel.ERROR) {
                        String text = message.message() == null ? "" : message.message();
                        if (text.contains("TypeError") || text.contains("ReferenceError")
                                || text.contains("Uncaught") || text.contains("SyntaxError")) {
                            headlessConsoleErrorCount++;
                            headlessLastConsoleError = text.length() > 240
                                    ? text.substring(0, 240) : text;
                            Log.e(HEADLESS_UI_TAG, "console source=" + message.sourceId()
                                    + " line=" + message.lineNumber() + " message=" + text);
                        }
                    }
                    return false;
                }
            });
            headlessWebView.setWebViewClient(new WebViewClient() {
                @Override public void onPageStarted(WebView view, String url, Bitmap favicon) {
                    if (view == headlessWebView) {
                        Log.i(HEADLESS_UI_TAG, "page-started url=" + String.valueOf(url));
                    }
                }

                @Override public void onPageFinished(WebView view, String url) {
                    if (view != headlessWebView || headlessPageFinished
                            || !isExpectedHeadlessUrl(url, headlessExpectedUrl)) return;
                    headlessPageFinished = true;
                    Log.i(HEADLESS_UI_TAG, "page-finished url=" + String.valueOf(url));
                }

                @Override public void onReceivedError(WebView view, WebResourceRequest request,
                        WebResourceError error) {
                    if (view == headlessWebView && request != null && request.isForMainFrame()) {
                        Log.e(HEADLESS_UI_TAG, "main-frame-error code="
                                + (error == null ? "unknown" : error.getErrorCode())
                                + " description=" + (error == null ? "unknown"
                                : String.valueOf(error.getDescription())));
                    }
                }
            });
            final WebView verificationView = headlessWebView;
            mainHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    if (verificationView == headlessWebView && headlessUiVerificationRunning) {
                        logHeadlessUiFailure("timeout");
                        destroyHeadlessUiVerification();
                    }
                }
            }, HEADLESS_UI_TIMEOUT_MS);
            headlessWebView.loadUrl(headlessExpectedUrl);
            final WebView probeView = headlessWebView;
            final String probeUrl = headlessExpectedUrl;
            mainHandler.postDelayed(new Runnable() {
                @Override public void run() {
                    probeHeadlessUi(probeView, probeUrl, 1);
                }
            }, 1200L);
        } catch (RuntimeException error) {
            logHeadlessUiFailure("webview-create-failed:" + error.getClass().getSimpleName());
            destroyHeadlessUiVerification();
        }
    }

    private void probeHeadlessUi(final WebView view, final String expectedUrl, final int attempt) {
        if (!headlessUiVerificationRunning || view == null || view != headlessWebView
                || !expectedUrl.equals(headlessExpectedUrl)) return;
        if (!isExpectedHeadlessUrl(view.getUrl(), expectedUrl)) {
            if (attempt < HEADLESS_UI_MAX_PROBES) {
                mainHandler.postDelayed(new Runnable() {
                    @Override public void run() {
                        probeHeadlessUi(view, expectedUrl, attempt + 1);
                    }
                }, 750L);
            } else {
                logHeadlessUiFailure("navigation-not-committed");
                destroyHeadlessUiVerification();
            }
            return;
        }
        String script = "(function(){try{var app=document.getElementById('app');"
                + "var scripts=Array.prototype.slice.call(document.scripts||[]);"
                + "var scriptSources=scripts.map(function(s){return s.src||'[inline]';});"
                + "var bundle=scripts.some(function(s){return (s.src||'').indexOf("
                + JSONObject.quote(EXPECTED_UI_BUNDLE_PATH) + ")>=0;});"
                + "var bundleExecutions=Number(window.__NEMOTRON_BUNDLE_EXECUTIONS__||0);"
                + "if(!window.__NEMOTRON_PROOF_STORAGE_GUARD__&&window.Storage){"
                + "var originalSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){"
                + "if(k==='codex-web-local.sidebar-collapsed.v1')return;return originalSetItem.call(this,k,v);};"
                + "window.__NEMOTRON_PROOF_STORAGE_GUARD__=true;}"
                + "var panel=document.querySelector('.sidebar-settings-panel');"
                + "var settingsButton=document.querySelector('.sidebar-settings-button');"
                + "var expandButton=Array.prototype.find.call(document.querySelectorAll('.sidebar-thread-controls-button'),"
                + "function(b){return /Expand sidebar/i.test((b.getAttribute('aria-label')||'')+' '+(b.title||''));});"
                + "if(!settingsButton&&expandButton){expandButton.click();settingsButton=document.querySelector('.sidebar-settings-button');}"
                + "var lazyRouteExercised=window.__NEMOTRON_LAZY_ROUTE_EXERCISED__===true;"
                + "var skillsButton=document.querySelector('.sidebar-skills-link');"
                + "if(!lazyRouteExercised&&skillsButton){window.__NEMOTRON_LAZY_ROUTE_EXERCISED__=true;"
                + "skillsButton.click();return JSON.stringify({event:'headless-ui-proof',ready:false,"
                + "stage:'lazy-route-loading',bundleExecutions:bundleExecutions,attempt:" + attempt + "});}"
                + "lazyRouteExercised=window.__NEMOTRON_LAZY_ROUTE_EXERCISED__===true;"
                + "if(!panel&&settingsButton){settingsButton.click();panel=document.querySelector('.sidebar-settings-panel');}"
                + "var cleanupApi=window.NemotronAutonomyProgress;"
                + "if(panel&&(!cleanupApi||typeof cleanupApi.ensureSessionCleanupCard!=='function')"
                + "&&!document.getElementById('nemotron-headless-cleanup-loader')){"
                + "var loader=document.createElement('script');loader.id='nemotron-headless-cleanup-loader';"
                + "loader.src='/nemotron-autonomy-progress.js?nemotron-private-proof=4.9.2';"
                + "(document.head||document.documentElement).appendChild(loader);}"
                + "cleanupApi=window.NemotronAutonomyProgress;"
                + "if(cleanupApi&&typeof cleanupApi.ensureSessionCleanupCard==='function')cleanupApi.ensureSessionCleanupCard();"
                + "panel=document.querySelector('.sidebar-settings-panel');"
                + "var cards=document.querySelectorAll('#nemotron-session-cleanup-card');"
                + "var buttons=document.querySelectorAll('#nemotron-session-cleanup-open');"
                + "var cleanupButton=buttons.length===1?buttons[0]:null;"
                + "var cleanupCard=cards.length===1?cards[0]:null;"
                + "var cleanupRect=cleanupCard?cleanupCard.getBoundingClientRect():null;"
                + "var cleanupStyle=cleanupCard?window.getComputedStyle(cleanupCard):null;"
                + "var cleanupButtonText=cleanupButton?(cleanupButton.textContent||'').trim():'';"
                + "var floatingControls=document.querySelectorAll("
                + "'#nemotron-autonomy-progress,#nemotron-autonomy-tools,.na-floating').length;"
                + "var cleanupReady=!!(panel&&cleanupCard&&cleanupButton"
                + "&&cleanupButtonText==='Delete all sessions and threads now'"
                + "&&cleanupRect&&cleanupRect.width>0&&cleanupRect.height>0"
                + "&&cleanupStyle&&cleanupStyle.display!=='none'&&cleanupStyle.visibility!=='hidden'"
                + "&&floatingControls===0);"
                + "var errors=Array.isArray(window.__NEMOTRON_STARTUP_ERRORS__)"
                + "?window.__NEMOTRON_STARTUP_ERRORS__.slice(-3):[];"
                + "var children=app?app.childElementCount:0;var html=app?app.innerHTML.length:0;"
                + "var text=app?(app.textContent||'').trim().length:0;"
                + "return JSON.stringify({event:'headless-ui-proof',ready:!!(app&&children>0&&html>32"
                + "&&text>0&&bundle&&bundleExecutions===1&&lazyRouteExercised&&cleanupReady&&errors.length===0),app:!!app,"
                + "children:children,html:html,text:text,bundle:bundle,"
                + "bundleExecutions:bundleExecutions,lazyRouteExercised:lazyRouteExercised,scriptSources:scriptSources,"
                + "settingsButton:!!settingsButton,expandButton:!!expandButton,settingsPanel:!!panel,"
                + "cleanupCardCount:cards.length,cleanupButtonCount:buttons.length,"
                + "cleanupButtonText:cleanupButtonText,cleanupWidth:cleanupRect?Math.round(cleanupRect.width):0,"
                + "cleanupHeight:cleanupRect?Math.round(cleanupRect.height):0,floatingControls:floatingControls,"
                + "errors:errors,attempt:" + attempt + "});"
                + "}catch(e){return JSON.stringify({event:'headless-ui-proof',ready:false,"
                + "error:String(e&&e.message||e),attempt:" + attempt + "});}})();";
        view.evaluateJavascript(script, new ValueCallback<String>() {
            @Override public void onReceiveValue(String value) {
                if (view != headlessWebView || !headlessUiVerificationRunning) return;
                JSONObject proof = decodeHeadlessUiProof(value);
                boolean attached = view.isAttachedToWindow();
                int displayId = view.getDisplay() == null ? -1 : view.getDisplay().getDisplayId();
                boolean privateVirtualDisplay = attached && displayId != Display.DEFAULT_DISPLAY;
                boolean ready = proof.optBoolean("ready", false) && headlessConsoleErrorCount == 0
                        && privateVirtualDisplay;
                try {
                    proof.put("event", "headless-ui-proof");
                    proof.put("ready", ready);
                    proof.put("consoleErrorCount", headlessConsoleErrorCount);
                    proof.put("lastConsoleError", headlessLastConsoleError);
                    proof.put("windowAttached", attached);
                    proof.put("displayId", displayId);
                    proof.put("privateVirtualDisplay", privateVirtualDisplay);
                    proof.put("physicalDisplay", displayId == Display.DEFAULT_DISPLAY);
                    proof.put("expectedBundle", EXPECTED_UI_BUNDLE_PATH);
                } catch (Exception ignored) { }
                if (ready) {
                    Log.i(HEADLESS_UI_TAG, proof.toString());
                    destroyHeadlessUiVerification();
                } else if (attempt < HEADLESS_UI_MAX_PROBES) {
                    mainHandler.postDelayed(new Runnable() {
                        @Override public void run() {
                            probeHeadlessUi(view, expectedUrl, attempt + 1);
                        }
                    }, 750L);
                } else {
                    Log.e(HEADLESS_UI_TAG, proof.toString());
                    destroyHeadlessUiVerification();
                }
            }
        });
    }

    private boolean isExpectedHeadlessUrl(String actualUrl, String expectedUrl) {
        if (actualUrl == null || expectedUrl == null) return false;
        int queryIndex = expectedUrl.indexOf('?');
        String expectedBase = queryIndex >= 0 ? expectedUrl.substring(0, queryIndex) : expectedUrl;
        return actualUrl.startsWith(expectedBase);
    }

    private JSONObject decodeHeadlessUiProof(String value) {
        try {
            Object outer = new JSONTokener(value == null ? "null" : value).nextValue();
            if (outer instanceof String) return new JSONObject((String) outer);
            if (outer instanceof JSONObject) return (JSONObject) outer;
        } catch (Exception ignored) { }
        JSONObject proof = new JSONObject();
        try {
            proof.put("event", "headless-ui-proof");
            proof.put("ready", false);
            proof.put("error", "invalid-evaluation-result");
        } catch (Exception ignored) { }
        return proof;
    }

    private void logHeadlessUiFailure(String reason) {
        JSONObject proof = new JSONObject();
        try {
            WebView verificationView = headlessWebView;
            boolean attached = verificationView != null && verificationView.isAttachedToWindow();
            int displayId = verificationView == null || verificationView.getDisplay() == null
                    ? -1 : verificationView.getDisplay().getDisplayId();
            proof.put("event", "headless-ui-proof");
            proof.put("ready", false);
            proof.put("reason", reason);
            proof.put("windowAttached", attached);
            proof.put("displayId", displayId);
            proof.put("privateVirtualDisplay", attached && displayId != Display.DEFAULT_DISPLAY);
            proof.put("physicalDisplay", displayId == Display.DEFAULT_DISPLAY);
            proof.put("expectedBundle", EXPECTED_UI_BUNDLE_PATH);
        } catch (Exception ignored) { }
        Log.e(HEADLESS_UI_TAG, proof.toString());
    }

    private void destroyHeadlessUiVerification() {
        WebView verificationView = headlessWebView;
        headlessWebView = null;
        headlessExpectedUrl = "";
        headlessPageFinished = false;
        headlessUiVerificationRunning = false;
        if (headlessPresentationRoot != null && verificationView != null) {
            try {
                headlessPresentationRoot.removeView(verificationView);
            } catch (RuntimeException ignored) { }
        }
        if (verificationView != null) {
            try {
                verificationView.stopLoading();
                verificationView.loadUrl("about:blank");
                verificationView.removeAllViews();
                verificationView.destroy();
            } catch (RuntimeException error) {
                Log.w(HEADLESS_UI_TAG, "headless-webview-destroy-failed", error);
            }
        }
        headlessPresentationRoot = null;
        if (headlessPresentation != null) {
            try {
                headlessPresentation.dismiss();
            } catch (RuntimeException ignored) { }
            headlessPresentation = null;
        }
        if (headlessVirtualDisplay != null) {
            headlessVirtualDisplay.release();
            headlessVirtualDisplay = null;
        }
        if (headlessImageReader != null) {
            headlessImageReader.close();
            headlessImageReader = null;
        }
        WebView.setWebContentsDebuggingEnabled(false);
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Nemotron Unrestricted runtime",
                NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Keeps the isolated Nemotron workspace available");
        channel.setShowBadge(false);
        channel.setSound(null, null);
        channel.enableVibration(false);
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager != null) manager.createNotificationChannel(channel);
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent pending = PendingIntent.getActivity(this, 0, open, flags);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentTitle("Nemotron Unrestricted")
                .setContentText(text)
                .setContentIntent(pending)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(Notification.CATEGORY_SERVICE)
                .setPriority(Notification.PRIORITY_LOW)
                .build();
    }

    private void ensureRuntime() {
        int guiPort = discoverGuiPort();
        if (guiPort > 0 && isOurGui(guiPort)) {
            rememberRuntimePort(this, guiPort);
            updateNotification(activeTurnCount > 0
                    ? activeTurnCount + " active session(s) protected with screen off"
                    : (lastCredentialConfigured
                        ? "Provider and workspace ready"
                        : "Workspace ready · provider credential required"));
            return;
        }
        updateNotification("Repairing isolated runtime");
        dispatchTermuxRuntime();
    }

    private void pollCompletionEvents() {
        int selected = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getInt(SUPERVISOR_PORT_KEY, 0);
        if (!isPort(selected)) return;
        long after = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(COMPLETION_SEQUENCE_KEY, 0L);
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + selected + "/events?after=" + after).openConnection();
            connection.setConnectTimeout(500);
            connection.setReadTimeout(1000);
            connection.setUseCaches(false);
            if (connection.getResponseCode() != 200) return;
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && body.length() < 262144) body.append(line);
            reader.close();
            JSONObject payload = new JSONObject(body.toString());
            if (payload.has("activeTurnCount")) {
                int reportedActiveTurns = Math.max(0, payload.optInt("activeTurnCount", 0));
                activeTurnCount = reportedActiveTurns;
                setActiveTurnWakeLock(reportedActiveTurns > 0);
                if (reportedActiveTurns > 0) {
                    updateNotification(reportedActiveTurns + " active session(s) protected with screen off");
                } else {
                    updateNotification(lastCredentialConfigured
                            ? "Provider and workspace ready"
                            : "Workspace ready · provider credential required");
                }
            }
            JSONArray events = payload.optJSONArray("events");
            if (events != null) {
                for (int index = 0; index < events.length(); index++) {
                    JSONObject event = events.optJSONObject(index);
                    if (event == null) continue;
                    long sequence = event.optLong("sequence", 0L);
                    if (sequence <= after) continue;
                    String outcome = event.optString("outcome");
                    if (!isTerminalOutcome(outcome)) continue;
                    if (!playCompletionSequence(selected, sequence)) break;
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private void setActiveTurnWakeLock(boolean active) {
        synchronized (wakeLockGuard) {
            if (activeTurnWakeLock == null) return;
            try {
                if (active && !activeTurnWakeLock.isHeld()) {
                    activeTurnWakeLock.acquire();
                } else if (!active && activeTurnWakeLock.isHeld()) {
                    activeTurnWakeLock.release();
                }
            } catch (RuntimeException error) {
                Log.w(TAG, "Could not update active-turn wake lock", error);
            }
        }
    }

    private static boolean isTerminalOutcome(String outcome) {
        return "completed".equals(outcome) || "failed".equals(outcome) || "stopped".equals(outcome);
    }

    private boolean playCompletionSequence(int supervisorPort, long sequence) {
        synchronized (completionToneGuard) {
            long completed = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .getLong(COMPLETION_SEQUENCE_KEY, 0L);
            if (sequence <= completed) return true;
            if (!playTerminalRingtone()) return false;
            if (!getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putLong(COMPLETION_SEQUENCE_KEY, sequence).commit()) return false;
            acknowledgeCompletionTone(supervisorPort, sequence);
            return true;
        }
    }

    private short[] buildTerminalRingtone() {
        int sampleCount = RINGTONE_SAMPLE_RATE * RINGTONE_DURATION_MS / 1000;
        short[] samples = new short[sampleCount];
        int noteSamples = sampleCount / RINGTONE_NOTES.length;
        int audibleSamples = (int) (noteSamples * 0.90);
        int fadeSamples = RINGTONE_SAMPLE_RATE / 100;
        for (int index = 0; index < sampleCount; index++) {
            int position = index % noteSamples;
            if (position >= audibleSamples) continue;
            double gain = 0.72;
            if (position < fadeSamples) gain *= (double) position / fadeSamples;
            int remaining = audibleSamples - position;
            if (remaining < fadeSamples) gain *= (double) remaining / fadeSamples;
            double frequency = RINGTONE_NOTES[Math.min(index / noteSamples, RINGTONE_NOTES.length - 1)];
            samples[index] = (short) Math.round(
                    Math.sin(2.0 * Math.PI * frequency * position / RINGTONE_SAMPLE_RATE)
                            * Short.MAX_VALUE * gain);
        }
        return samples;
    }

    private boolean playTerminalRingtone() {
        AudioTrack track = null;
        try {
            short[] samples = buildTerminalRingtone();
            AudioAttributes attributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            AudioFormat format = new AudioFormat.Builder()
                    .setSampleRate(RINGTONE_SAMPLE_RATE)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build();
            int minimumBuffer = AudioTrack.getMinBufferSize(
                    RINGTONE_SAMPLE_RATE,
                    AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT);
            if (minimumBuffer <= 0) return false;
            int bufferBytes = Math.max(minimumBuffer, RINGTONE_SAMPLE_RATE / 5);
            track = new AudioTrack(attributes, format, bufferBytes,
                    AudioTrack.MODE_STREAM, AudioManager.AUDIO_SESSION_ID_GENERATE);
            if (track.getState() != AudioTrack.STATE_INITIALIZED) return false;
            track.setVolume(RINGTONE_VOLUME);
            track.play();
            int written = 0;
            while (written < samples.length) {
                int count = track.write(
                        samples, written, samples.length - written, AudioTrack.WRITE_BLOCKING);
                if (count <= 0) return false;
                written += count;
            }
            long deadline = SystemClock.elapsedRealtime() + 1500L;
            while (track.getPlaybackHeadPosition() < samples.length
                    && SystemClock.elapsedRealtime() < deadline) {
                SystemClock.sleep(10L);
            }
            if (track.getPlaybackHeadPosition() < samples.length) return false;
            track.stop();
            return true;
        } catch (RuntimeException error) {
            Log.w(TAG, "Terminal ringtone playback failed", error);
            return false;
        } finally {
            if (track != null) {
                try { track.release(); } catch (RuntimeException ignored) { }
            }
        }
    }

    private void acknowledgeCompletionTone(int supervisorPort, long sequence) {
        if (!isPort(supervisorPort) || sequence < 1L) return;
        HttpURLConnection connection = null;
        try {
            byte[] body = ("{\"sequence\":" + sequence + "}").getBytes(StandardCharsets.UTF_8);
            connection = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + supervisorPort + "/ack").openConnection();
            connection.setConnectTimeout(500);
            connection.setReadTimeout(1000);
            connection.setUseCaches(false);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(body.length);
            OutputStream output = connection.getOutputStream();
            output.write(body);
            output.close();
            if (connection.getResponseCode() != 200) return;
            connection.getInputStream().close();
        } catch (Exception ignored) {
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private int discoverGuiPort() {
        int rememberedProxy = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getInt(PROXY_PORT_KEY, 0);
        if (rememberedProxy >= DEFAULT_PROXY_PORT && rememberedProxy <= MAX_PROXY_PORT) {
            int rememberedGui = probeProxyPort(rememberedProxy);
            if (rememberedGui > 0) return rememberedGui;
        }
        for (int proxyPort = DEFAULT_PROXY_PORT; proxyPort <= MAX_PROXY_PORT; proxyPort++) {
            if (proxyPort == rememberedProxy) continue;
            int guiPort = probeProxyPort(proxyPort);
            if (guiPort > 0) return guiPort;
        }
        return 0;
    }

    private int probeProxyPort(int proxyPort) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + proxyPort + "/vault-health").openConnection();
            connection.setConnectTimeout(350);
            connection.setReadTimeout(750);
            connection.setUseCaches(false);
            if (connection.getResponseCode() != 200) return 0;
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && body.length() < 4096) body.append(line);
            reader.close();
            JSONObject health = new JSONObject(body.toString());
            String expectedBaseUrl = "http://127.0.0.1:" + proxyPort + "/v1";
            String sourceHash = health.optString("sourceHash");
            if (!"ok".equals(health.optString("status"))
                    || !"OpenRouter".equals(health.optString("provider"))
                    || !APP_ID.equals(health.optString("app"))
                    || health.optInt("proxyPort", 0) != proxyPort
                    || !expectedBaseUrl.equals(health.optString("providerBaseUrl"))
                    || !expectedBaseUrl.equals(health.optString("effectiveBaseUrl"))
                    || !(health.opt("credentialConfigured") instanceof Boolean)
                    || !isSha256(sourceHash)
                    || !health.optString("credentialSourceFingerprint").matches("[0-9a-f]{16,64}")) return 0;
            int guiPort = health.optInt("guiPort", 0);
            int supervisorPort = health.optInt("supervisorPort", 0);
            String supervisorSourceHash = health.optString("supervisorSourceHash");
            if (!isPort(guiPort) || !isPort(supervisorPort)
                    || guiPort == proxyPort || supervisorPort == proxyPort
                    || supervisorPort == guiPort || !isSha256(supervisorSourceHash)
                    || !isOurGui(guiPort, proxyPort)
                    || !isOurSupervisor(supervisorPort, supervisorSourceHash)) return 0;
            lastCredentialConfigured = health.optBoolean("credentialConfigured", false);
            rememberRuntimeEndpoint(this, guiPort, proxyPort, supervisorPort);
            return guiPort;
        } catch (Exception ignored) {
            return 0;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static boolean isPort(int port) {
        return port >= 1 && port <= 65535;
    }

    private static boolean isSha256(String value) {
        return value != null && value.matches("[0-9a-f]{64}");
    }

    private static boolean isOurSupervisor(int supervisorPort, String expectedSourceHash) {
        if (!isPort(supervisorPort) || !isSha256(expectedSourceHash)) return false;
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + supervisorPort + "/health").openConnection();
            connection.setConnectTimeout(500);
            connection.setReadTimeout(1000);
            connection.setUseCaches(false);
            if (connection.getResponseCode() != 200) return false;
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && body.length() < 4096) body.append(line);
            reader.close();
            JSONObject health = new JSONObject(body.toString());
            return "ok".equals(health.optString("status"))
                    && APP_ID.equals(health.optString("app"))
                    && health.optInt("port", 0) == supervisorPort
                    && expectedSourceHash.equals(health.optString("sourceSha256"));
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    static boolean isOurGui(int guiPort) {
        return isOurGui(guiPort, 0);
    }

    static boolean isOurGui(int guiPort, int proxyPort) {
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
            if (connection.getResponseCode() != 200) return false;
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                if (body.length() + line.length() > MAX_CONFIG_RESPONSE_CHARACTERS) {
                    reader.close();
                    return false;
                }
                body.append(line);
            }
            reader.close();
            JSONObject payload = new JSONObject(body.toString());
            JSONObject result = payload.optJSONObject("result");
            JSONObject config = result == null ? null : result.optJSONObject("config");
            JSONObject providers = config == null ? null : config.optJSONObject("model_providers");
            JSONObject custom = providers == null ? null : providers.optJSONObject("custom_endpoint");
            String expectedGuiBase = "http://127.0.0.1:" + guiPort + "/codex-api/custom-proxy/v1";
            if (config == null || custom == null
                    || !"custom_endpoint".equals(config.optString("model_provider"))
                    || !expectedGuiBase.equals(custom.optString("base_url"))
                    || !config.optString("developer_instructions").contains("isolated Nemotron Autonomy runtime using OpenRouter")) {
                return false;
            }
            return verifyCustomProvider(guiPort, proxyPort);
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static boolean verifyCustomProvider(int guiPort, int proxyPort) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + guiPort + "/codex-api/free-mode/status").openConnection();
            connection.setConnectTimeout(1000);
            connection.setReadTimeout(2000);
            connection.setUseCaches(false);
            if (connection.getResponseCode() != 200) return false;
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && body.length() < 16384) body.append(line);
            reader.close();
            JSONObject status = new JSONObject(body.toString());
            String baseUrl = status.optString("customBaseUrl");
            if (proxyPort == 0) {
                URL parsed = new URL(baseUrl);
                if (!"http".equals(parsed.getProtocol()) || !"127.0.0.1".equals(parsed.getHost())
                        || !"/v1".equals(parsed.getPath()) || !isPort(parsed.getPort())) return false;
                proxyPort = parsed.getPort();
            }
            return status.optBoolean("enabled", false)
                    && "custom".equals(status.optString("provider"))
                    && "chat".equals(status.optString("wireApi"))
                    && ("http://127.0.0.1:" + proxyPort + "/v1").equals(baseUrl);
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private void dispatchTermuxRuntime() {
        if (watchdog == null || watchdog.isShutdown()) return;
        long now = SystemClock.elapsedRealtime();
        if (now - lastRuntimeDispatchAt < 5000L) return;
        if (!runtimeStartQueued.compareAndSet(false, true)) return;
        lastRuntimeDispatchAt = now;
        watchdog.execute(new Runnable() {
            @Override public void run() {
                try { startTermuxRuntime(); }
                finally { runtimeStartQueued.set(false); }
            }
        });
    }

    private void startTermuxRuntime() {
        if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission(TERMUX_PERMISSION) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "Termux RUN_COMMAND permission has not been granted");
            return;
        }
        Intent command = new Intent("com.termux.RUN_COMMAND");
        command.setClassName(TERMUX_PACKAGE, TERMUX_SERVICE);
        command.putExtra("com.termux.RUN_COMMAND_PATH", START_SCRIPT);
        command.putExtra("com.termux.RUN_COMMAND_WORKDIR", PROJECT_ROOT);
        command.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
        command.putExtra("com.termux.RUN_COMMAND_SESSION_ACTION", "0");
        command.putExtra("com.termux.RUN_COMMAND_LABEL", "Nemotron Unrestricted runtime");
        command.putExtra("com.termux.RUN_COMMAND_DESCRIPTION", "Starts the isolated Nemotron Unrestricted runtime");
        try {
            startService(command);
            Log.i(TAG, "Termux RUN_COMMAND dispatched");
        } catch (Exception error) {
            Log.e(TAG, "Termux RUN_COMMAND request failed", error);
        }
    }

    private void updateNotification(String text) {
        if (text != null && text.equals(lastNotificationText)) return;
        lastNotificationText = text == null ? "" : text;
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager != null) manager.notify(NOTIFICATION_ID, buildNotification(lastNotificationText));
    }
}
