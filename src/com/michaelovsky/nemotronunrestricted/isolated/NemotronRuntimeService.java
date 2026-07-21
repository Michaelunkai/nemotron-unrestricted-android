package com.michaelovsky.nemotronunrestricted.isolated;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Build;
import android.os.IBinder;
import android.os.SystemClock;
import android.util.Log;

import org.json.JSONObject;
import org.json.JSONArray;

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

    private ScheduledExecutorService watchdog;
    private final AtomicBoolean runtimeStartQueued = new AtomicBoolean(false);
    private long lastRuntimeDispatchAt;
    private String lastNotificationText = "";
    private volatile boolean lastCredentialConfigured;

    @Override public void onCreate() {
        super.onCreate();
        createChannel();
        startForeground(NOTIFICATION_ID, buildNotification("Protecting isolated runtime"));
        watchdog = Executors.newScheduledThreadPool(2);
        watchdog.scheduleWithFixedDelay(new Runnable() {
            @Override public void run() { ensureRuntime(); }
        }, 0L, 15L, TimeUnit.SECONDS);
        watchdog.scheduleWithFixedDelay(new Runnable() {
            @Override public void run() { pollCompletionEvents(); }
        }, 1L, 2L, TimeUnit.SECONDS);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        Log.i(TAG, "Starting Nemotron Unrestricted runtime");
        dispatchTermuxRuntime();
        return START_STICKY;
    }

    @Override public void onDestroy() {
        if (watchdog != null) watchdog.shutdownNow();
        super.onDestroy();
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
            updateNotification(lastCredentialConfigured
                    ? "Provider and workspace ready"
                    : "Workspace ready · provider credential required");
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
            JSONArray events = payload.optJSONArray("events");
            long newest = after;
            if (events != null) {
                for (int index = 0; index < events.length(); index++) {
                    JSONObject event = events.optJSONObject(index);
                    if (event == null) continue;
                    long sequence = event.optLong("sequence", 0L);
                    if (sequence <= after) continue;
                    newest = Math.max(newest, sequence);
                    if ("completed".equals(event.optString("outcome")) && playCompletionTone()) {
                        acknowledgeCompletionTone(selected, sequence);
                    }
                }
            }
            newest = Math.max(newest, payload.optLong("sequence", after));
            if (newest > after) getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit().putLong(COMPLETION_SEQUENCE_KEY, newest).apply();
        } catch (Exception ignored) {
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private boolean playCompletionTone() {
        final ToneGenerator tone;
        try {
            tone = new ToneGenerator(AudioManager.STREAM_NOTIFICATION, 50);
            if (!tone.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 3000)) {
                tone.release();
                return false;
            }
        } catch (RuntimeException ignored) {
            return false;
        }
        new Thread(new Runnable() {
            @Override public void run() {
                SystemClock.sleep(3100L);
                try {
                    tone.stopTone();
                    tone.release();
                } catch (RuntimeException ignored) {
                }
            }
        }, "nemotron-completion-tone").start();
        return true;
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
