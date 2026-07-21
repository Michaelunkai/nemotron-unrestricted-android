(function nemotronAutonomyProgressBootstrap() {
  'use strict';

  if (window.__NEMOTRON_AUTONOMY_PROGRESS__) return;
  window.__NEMOTRON_AUTONOMY_PROGRESS__ = true;

  const VERSION = '4.3.0';
  const PANEL_ID = 'nemotron-autonomy-progress';
  const NativeWebSocket = window.WebSocket;
  const NativeEventSource = window.EventSource;
  const NativeFetch = window.fetch.bind(window);
  const STORAGE_VERSION = 1;
  const STORAGE_PREFIX = `nemotron-autonomy-progress:v${STORAGE_VERSION}:`;
  const STORAGE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
  const RPC_TIMEOUT_MS = 10000;
  const MAX_EVENT_FINGERPRINTS = 32768;
  const MAX_PERSISTED_FINGERPRINTS = 2048;
  const MAX_MEANINGFUL_UPDATES = 40;
  const HUMAN_CHECKPOINT_MS = 55000;
  const MAX_RESPONSE_ONLY_RECOVERIES = 3;
  const VISUAL_HUMANIZATION_SWEEP_MS = 1000;
  const completedTurns = new Set();
  const registeredActiveTurns = new Set();
  const recoveryAttempts = new Map();
  const recoveryTimers = new Map();
  const recoveringTerminalTurns = new Set();
  let liveSocketGeneration = 0;
  let liveSocketWarningTimer = null;
  let liveEventSourceGeneration = 0;
  let recoveryEventSource = null;
  let recoveryEventSourceTimer = null;
  let recoveryEventSourceAttempts = 0;
  let pageUnloading = false;
  let toolbarFrame = 0;
  const state = {
    active: false,
    completed: false,
    phase: 'idle',
    collapsed: false,
    hidden: true,
    startedAtEpochMs: 0,
    turnId: '',
    objective: '',
    steps: [],
    meaningfulUpdates: [],
    panel: null,
    hideTimer: null,
    currentThreadId: '',
    selectedEffort: 'high',
    activeTurnEffort: '',
    queuedEffort: '',
    lastCompletedAt: 0,
    toolbar: null,
    toolbarStatus: 'Ready',
    compactionPending: false,
    compactionRecoveryTimer: null,
    completedCommands: 0,
    actionCount: 0,
    failedCommands: 0,
    plannedSteps: 0,
    completedPlanSteps: 0,
    latestVerifiedResult: '',
    nextBoundedAction: '',
    technicalEvents: [],
    lastActivityAt: 0,
    lastRealEventAt: 0,
    lastHumanCheckpointAt: 0,
    lastAuthoritativeReadAt: 0,
    responseOnlyRecoveries: 0,
    activeCommandKey: '',
    activeCommandKeys: new Map(),
    consecutiveFailureKey: '',
    consecutiveFailureCount: 0,
    interruptionRequested: false,
    eventFingerprints: new Set(),
    reconcileInFlight: false,
    lastReconcileAt: 0,
    lastSocketEventAt: 0,
    hydrateInFlight: false,
    possibleSideEffect: false,
    expectedTurnStart: false,
    inactivityStage: 0,
    repositoryState: 'unknown',
  };

  function clean(value) {
    return String(value == null ? '' : value).replace(/\s+/gu, ' ').trim();
  }

  function redactSensitive(value) {
    let text = String(value == null ? '' : value).slice(0, 16000);
    text = text
        .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/giu, '$1[REDACTED]')
        .replace(/\b(?:sk-or-v1-|github_pat_|gh[pousr]_|xox[baprs]-)[A-Za-z0-9_-]{8,}\b/gu, '[REDACTED]')
        .replace(/((?:api[_-]?key|access[_-]?token|auth(?:orization)?|cookie|password|secret|token)\s*["']?\s*[:=]\s*["']?)[^\s,"'};]+/giu, '$1[REDACTED]')
        .replace(/([?&](?:api[_-]?key|access[_-]?token|auth|key|secret|token)=)[^&#\s]+/giu, '$1[REDACTED]')
        .replace(/(window\.__NEMOTRON_BRIDGE_TOKEN__\s*=\s*)[^;]+/gu, '$1[REDACTED]')
        .replace(/\/data\/data\/com\.termux\/files\/home\/[^\s"'<>)}\]]*(?:openrouter\.env|signing\.properties|[^/\s]+\.keystore|\/(?:\.ssh|\.aws|\.azure|\.gnupg|vault|credentials?|tokens?|secrets?)(?:\/|$))[^\s"'<>)}\]]*/giu, '<credential-path>')
        .replace(/\b[A-Za-z]:\\Users\\[^\\\s]+\\(?:AppData|\.ssh|\.aws|\.azure|\.gnupg|Documents\\Codex)(?:\\[^\s"'<>)}\]]*)?/giu, '<private-path>');
    return text;
  }

  function safeText(value, limit = 320) {
    return clean(redactSensitive(value)).slice(0, Math.max(0, limit));
  }

  function escapeTechnical(value) {
    return String(value == null ? '' : value)
        .replace(/&/gu, '&amp;')
        .replace(/</gu, '&lt;')
        .replace(/>/gu, '&gt;')
        .replace(/"/gu, '&quot;')
        .replace(/'/gu, '&#39;');
  }

  function escapeHtml(value) {
    return clean(value)
        .replace(/&/gu, '&amp;')
        .replace(/</gu, '&lt;')
        .replace(/>/gu, '&gt;')
        .replace(/"/gu, '&quot;')
        .replace(/'/gu, '&#39;');
  }

  function formatElapsed(milliseconds) {
    const seconds = Math.max(0, Math.floor(milliseconds / 1000));
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
  }

  function humanizeCommand(command) {
    const value = clean(command).toLowerCase();
    if (!value) return 'Running the next verified task step';
    if (/\bcommand\s+-v\b|\bwhich\s+(?:-[a-z]+\s+)?/u.test(value)) {
      return 'Checking which automation tools are installed and ready';
    }
    if (/\bcodex-gallery\s+(?:recent|search|inspect|faces|semantic)\b/u.test(value)) {
      return 'Scanning the Android gallery and verifying matching images';
    }
    if (/\bcodex-gallery\s+(?:trash|restore)\b/u.test(value)) {
      return 'Updating the selected gallery items with recoverable MediaStore changes';
    }
    if (/(codex-research|codex-search|search_query|duckduckgo|google search)/u.test(value)) {
      return 'Searching online and comparing current sources';
    }
    if (/(codex-fetch|fetch_url|curl\s|read.*https?:\/\/)/u.test(value)) {
      return 'Reading and verifying source details';
    }
    if (/(codex-download|wget\s|download)/u.test(value)) {
      return 'Downloading and verifying the requested files';
    }
    if (/(codex-install|pm\s+install|install-multiple)/u.test(value)) {
      return 'Installing and independently verifying the app';
    }
    if (/(apksigner|zipalign|\baapt\b|\bd8\b|\bjavac\b)/u.test(value)) {
      return 'Building and signing the Android release';
    }
    if (/(python.*unittest|pytest|vitest|npm\s+test|pnpm\s+test|gradle.*test)/u.test(value)) {
      return 'Running automated verification checks';
    }
    if (/(codex-identity|vault-health|custom-proxy.*models)/u.test(value)) {
      return 'Verifying the NEMOTRON provider and model';
    }
    if (/(codex-wifi-scan|iwlist|cmd\s+wifi|termux-wifi-scaninfo)/u.test(value)) {
      return 'Reading nearby Wi-Fi security information safely';
    }
    if (/(\brish\b|codex-shizuku)/u.test(value)) {
      return 'Using the Android system service bridge';
    }
    if (/(\bnmap\b|codex-lan-discover)/u.test(value)) {
      return 'Running a bounded, authorized network diagnostic';
    }
    if (/(\bscapy\b|socket\.af_packet|\bsrp\()/u.test(value)) {
      return 'Checking supported packet-analysis capabilities';
    }
    if (/(codex-android|\bam\s+(start|force-stop)|uiautomator|ui automation)/u.test(value)) {
      return 'Automating and verifying the requested Android step';
    }
    if (/(apply_patch|git\s+(apply|diff)|patch\s)/u.test(value)) {
      return 'Applying the verified project changes';
    }
    if (/(grep\s|find\s|sed\s|ls\s|stat\s|sha256sum|dumpsys|pm\s+path)/u.test(value)) {
      return 'Inspecting the relevant files and device state';
    }
    const executable = safeText(clean(command).split(/\s+/u)[0].replace(/^.*\//u, ''), 48) || 'the requested tool';
    const objective = safeText(state.objective, 150) || 'the active request';
    return `Using ${executable} to advance: ${objective}`;
  }

  function itemType(event) {
    const params = event && event.params && typeof event.params === 'object' ? event.params : {};
    const item = params.item && typeof params.item === 'object' ? params.item : {};
    return clean(item.type).toLowerCase();
  }

  function explicitEventTurnId(event) {
    const params = event && event.params && typeof event.params === 'object' ? event.params : {};
    const turn = params.turn && typeof params.turn === 'object' ? params.turn : {};
    return clean(turn.id || params.turnId || params.turn_id);
  }

  function eventTurnId(event) {
    return explicitEventTurnId(event) || state.turnId || 'unknown-turn';
  }

  function eventThreadId(event) {
    const params = event && event.params && typeof event.params === 'object' ? event.params : {};
    const turn = params.turn && typeof params.turn === 'object' ? params.turn : {};
    return clean(params.threadId || params.thread_id || turn.threadId || turn.thread_id);
  }

  function routeThreadId() {
    const match = String(window.location.pathname || '').match(/\/(?:thread|threads)\/([^/?#]+)/u);
    if (!match) return '';
    try {
      return clean(decodeURIComponent(match[1]));
    } catch (_) {
      return clean(match[1]);
    }
  }

  function validThreadId(value) {
    const id = clean(value);
    return /^[A-Za-z0-9._:-]{1,256}$/u.test(id) ? id : '';
  }

  function storageKey(threadId) {
    const id = validThreadId(threadId);
    return id ? `${STORAGE_PREFIX}${id}` : '';
  }

  function storageGet(key) {
    if (!key) return null;
    try {
      const storage = window.localStorage;
      return storage ? storage.getItem(key) : null;
    } catch (_) {
      return null;
    }
  }

  function storageSet(key, value) {
    if (!key) return;
    try {
      const storage = window.localStorage;
      if (storage) storage.setItem(key, value);
    } catch (_) {
    }
  }

  function sanitizedUpdate(entry) {
    return {
      id: safeText(entry && entry.id, 360),
      label: safeText(entry && entry.label, 320),
      status: /^(?:active|completed|failed|retry)$/u.test(clean(entry && entry.status)) ? clean(entry.status) : 'active',
      evidence: safeText(entry && entry.evidence, 320),
      at: Math.max(0, Number(entry && entry.at) || 0),
      attempts: Math.max(1, Math.min(999, Number(entry && entry.attempts) || 1)),
    };
  }

  function compactEventFingerprints(values) {
    const candidates = Array.isArray(values) ? values : Array.from(values || []);
    return candidates.slice(-MAX_PERSISTED_FINGERPRINTS)
        .map((entry) => clean(entry).toLowerCase())
        .filter((entry) => /^[a-f0-9]{16}$/u.test(entry));
  }

  function persistProgress() {
    const threadId = validThreadId(state.currentThreadId);
    const key = storageKey(threadId);
    if (!key) return;
    const payload = {
      version: STORAGE_VERSION,
      savedAt: Date.now(),
      threadId,
      active: Boolean(state.active),
      completed: Boolean(state.completed),
      phase: /^(?:idle|working|retry|failed|complete)$/u.test(state.phase) ? state.phase : 'idle',
      hidden: Boolean(state.hidden),
      startedAtEpochMs: Math.max(0, Number(state.startedAtEpochMs) || 0),
      turnId: safeText(state.turnId, 256),
      objective: safeText(state.objective, 420),
      selectedEffort: safeText(state.selectedEffort, 32),
      activeTurnEffort: safeText(state.activeTurnEffort, 32),
      queuedEffort: safeText(state.queuedEffort, 32),
      completedCommands: Math.max(0, Number(state.completedCommands) || 0),
      actionCount: Math.max(0, Number(state.actionCount) || 0),
      failedCommands: Math.max(0, Number(state.failedCommands) || 0),
      plannedSteps: Math.max(0, Number(state.plannedSteps) || 0),
      completedPlanSteps: Math.max(0, Number(state.completedPlanSteps) || 0),
      latestVerifiedResult: safeText(state.latestVerifiedResult, 320),
      nextBoundedAction: safeText(state.nextBoundedAction, 320),
      lastActivityAt: Math.max(0, Number(state.lastActivityAt) || 0),
      lastRealEventAt: Math.max(0, Number(state.lastRealEventAt) || 0),
      lastHumanCheckpointAt: Math.max(0, Number(state.lastHumanCheckpointAt) || 0),
      lastAuthoritativeReadAt: Math.max(0, Number(state.lastAuthoritativeReadAt) || 0),
      responseOnlyRecoveries: Math.max(0, Math.min(MAX_RESPONSE_ONLY_RECOVERIES, Number(state.responseOnlyRecoveries) || 0)),
      possibleSideEffect: Boolean(state.possibleSideEffect),
      repositoryState: /^(?:unknown|present|detached|none)$/u.test(state.repositoryState) ? state.repositoryState : 'unknown',
      steps: state.steps.slice(-12).map((entry) => ({
        label: safeText(entry && entry.label, 320),
        identity: safeText(entry && entry.identity, 360),
        status: /^(?:active|completed|failed|retry)$/u.test(clean(entry && entry.status)) ? clean(entry.status) : 'active',
        attempts: Math.max(1, Math.min(999, Number(entry && entry.attempts) || 1)),
        updatedAt: Math.max(0, Number(entry && entry.updatedAt) || 0),
      })),
      meaningfulUpdates: state.meaningfulUpdates.slice(-MAX_MEANINGFUL_UPDATES).map(sanitizedUpdate),
      technicalEvents: state.technicalEvents.slice(-5).map((entry) => ({
        command: safeText(entry && entry.command, 1200),
        output: safeText(entry && entry.output, 2400),
        status: safeText(entry && entry.status, 32),
      })),
      eventFingerprints: compactEventFingerprints(state.eventFingerprints),
      recoveringTerminalTurns: Array.from(recoveringTerminalTurns).slice(-64).map((entry) => safeText(entry, 256)),
    };
    storageSet(key, JSON.stringify(payload));
  }

  function hydratePersistedProgress(threadId) {
    const id = validThreadId(threadId);
    const raw = storageGet(storageKey(id));
    if (!id || !raw) return false;
    let saved;
    try {
      saved = JSON.parse(raw);
    } catch (_) {
      return false;
    }
    const savedAt = Number(saved && saved.savedAt) || 0;
    if (!saved || saved.version !== STORAGE_VERSION || saved.threadId !== id || savedAt <= 0
        || Date.now() - savedAt > STORAGE_MAX_AGE_MS || savedAt - Date.now() > 60000) return false;
    state.currentThreadId = id;
    state.active = Boolean(saved.active);
    state.completed = Boolean(saved.completed);
    state.phase = /^(?:idle|working|retry|failed|complete)$/u.test(saved.phase) ? saved.phase : 'idle';
    state.hidden = Boolean(saved.hidden);
    const startedAt = Number(saved.startedAtEpochMs) || 0;
    state.startedAtEpochMs = startedAt > Date.now() - STORAGE_MAX_AGE_MS && startedAt <= Date.now() + 60000
      ? startedAt : Date.now();
    state.turnId = safeText(saved.turnId, 256);
    state.objective = safeText(saved.objective, 420);
    state.selectedEffort = safeText(saved.selectedEffort, 32) || 'high';
    state.activeTurnEffort = safeText(saved.activeTurnEffort, 32);
    state.queuedEffort = safeText(saved.queuedEffort, 32);
    for (const key of ['completedCommands', 'actionCount', 'failedCommands', 'plannedSteps', 'completedPlanSteps']) {
      state[key] = Math.max(0, Math.min(1000000, Number(saved[key]) || 0));
    }
    state.latestVerifiedResult = safeText(saved.latestVerifiedResult, 320);
    state.nextBoundedAction = safeText(saved.nextBoundedAction, 320);
    state.lastActivityAt = Math.max(0, Number(saved.lastActivityAt) || savedAt);
    state.lastRealEventAt = Math.max(0, Number(saved.lastRealEventAt) || state.lastActivityAt);
    state.lastHumanCheckpointAt = Math.max(0, Number(saved.lastHumanCheckpointAt) || state.lastRealEventAt);
    state.lastAuthoritativeReadAt = Math.max(0, Number(saved.lastAuthoritativeReadAt) || 0);
    state.responseOnlyRecoveries = Math.max(0, Math.min(MAX_RESPONSE_ONLY_RECOVERIES, Number(saved.responseOnlyRecoveries) || 0));
    state.possibleSideEffect = Boolean(saved.possibleSideEffect);
    state.repositoryState = /^(?:unknown|present|detached|none)$/u.test(saved.repositoryState) ? saved.repositoryState : 'unknown';
    state.steps = Array.isArray(saved.steps) ? saved.steps.slice(-12).map((entry) => ({
      label: safeText(entry && entry.label, 320),
      identity: safeText(entry && entry.identity, 360),
      status: /^(?:active|completed|failed|retry)$/u.test(clean(entry && entry.status)) ? clean(entry.status) : 'active',
      attempts: Math.max(1, Math.min(999, Number(entry && entry.attempts) || 1)),
      updatedAt: Math.max(0, Number(entry && entry.updatedAt) || savedAt),
    })) : [];
    state.meaningfulUpdates = Array.isArray(saved.meaningfulUpdates)
      ? saved.meaningfulUpdates.slice(-MAX_MEANINGFUL_UPDATES).map(sanitizedUpdate) : [];
    state.technicalEvents = Array.isArray(saved.technicalEvents) ? saved.technicalEvents.slice(-5).map((entry) => ({
      command: safeText(entry && entry.command, 1200),
      output: safeText(entry && entry.output, 2400),
      status: safeText(entry && entry.status, 32),
    })) : [];
    state.eventFingerprints = new Set(compactEventFingerprints(
        Array.isArray(saved.eventFingerprints) ? saved.eventFingerprints : []));
    if (Array.isArray(saved.recoveringTerminalTurns)) {
      saved.recoveringTerminalTurns.slice(-64).map((entry) => safeText(entry, 256)).filter(Boolean)
          .forEach((entry) => recoveringTerminalTurns.add(entry));
    }
    if (state.completed && state.turnId) completedTurns.add(state.turnId);
    markPersistedActiveTurnForRecovery();
    return true;
  }

  function eventMatchesVisibleThread(event) {
    const visible = routeThreadId();
    const incoming = eventThreadId(event);
    return Boolean(visible && incoming && visible === incoming && state.currentThreadId === visible);
  }

  function fingerprintDigest(value) {
    const text = String(value == null ? '' : value);
    let first = 2166136261;
    let second = 2246822519;
    for (let index = 0; index < text.length; index += 1) {
      const code = text.charCodeAt(index);
      first = Math.imul(first ^ code, 16777619) >>> 0;
      second = Math.imul(second ^ code, 3266489917) >>> 0;
    }
    return `${first.toString(16).padStart(8, '0')}${second.toString(16).padStart(8, '0')}`;
  }

  function eventFingerprint(event, method) {
    const params = event && event.params && typeof event.params === 'object' ? event.params : {};
    const item = params.item && typeof params.item === 'object' ? params.item : {};
    const plan = Array.isArray(params.plan) ? params.plan.map((entry) => [safeText(entry && entry.step, 320), clean(entry && entry.status)]) : [];
    return fingerprintDigest(JSON.stringify([
      method,
      eventThreadId(event),
      explicitEventTurnId(event),
      eventItemId(event),
      clean(item.type),
      clean(item.status),
      item.exitCode ?? item.exit_code ?? null,
      safeText(item.command, 1200),
      safeText(itemOutput(item), 2400),
      plan,
      clean(params.status || (params.turn && params.turn.status)),
    ]));
  }

  function rememberEventFingerprint(event, method) {
    const fingerprint = eventFingerprint(event, method);
    if (state.eventFingerprints.has(fingerprint)) return true;
    state.eventFingerprints.add(fingerprint);
    while (state.eventFingerprints.size > MAX_EVENT_FINGERPRINTS) {
      state.eventFingerprints.delete(state.eventFingerprints.values().next().value);
    }
    return false;
  }

  function markRealEvent() {
    const now = Date.now();
    state.lastActivityAt = now;
    state.lastRealEventAt = now;
    state.lastHumanCheckpointAt = now;
    state.inactivityStage = 0;
  }

  function markPersistedActiveTurnForRecovery() {
    if (!state.active || state.completed || !state.lastRealEventAt
        || Date.now() - state.lastRealEventAt <= 30000) return;
    state.phase = 'retry';
    state.hidden = false;
    state.inactivityStage = Math.max(state.inactivityStage, 2);
    recordMeaningfulUpdate(
        'Restored active work — verifying authoritative thread state',
        'retry',
        'persistence:authoritative-recovery');
  }

  function resetForVisibleThread(threadId) {
    const previousThreadId = state.currentThreadId;
    if (previousThreadId) persistProgress();
    closeRecoveryEventSource();
    if (state.hideTimer) window.clearTimeout(state.hideTimer);
    if (state.compactionRecoveryTimer) window.clearTimeout(state.compactionRecoveryTimer);
    state.hideTimer = null;
    state.compactionRecoveryTimer = null;
    state.active = false;
    state.completed = false;
    state.phase = 'idle';
    state.hidden = true;
    state.startedAtEpochMs = 0;
    state.turnId = '';
    state.objective = '';
    state.steps = [];
    state.meaningfulUpdates = [];
    state.completedCommands = 0;
    state.actionCount = 0;
    state.failedCommands = 0;
    state.plannedSteps = 0;
    state.completedPlanSteps = 0;
    state.latestVerifiedResult = '';
    state.nextBoundedAction = '';
    state.technicalEvents = [];
    state.lastActivityAt = 0;
    state.lastRealEventAt = 0;
    state.lastHumanCheckpointAt = 0;
    state.lastAuthoritativeReadAt = 0;
    state.responseOnlyRecoveries = 0;
    state.activeCommandKey = '';
    state.activeCommandKeys.clear();
    state.compactionPending = false;
    state.consecutiveFailureKey = '';
    state.consecutiveFailureCount = 0;
    state.interruptionRequested = false;
    state.possibleSideEffect = false;
    state.expectedTurnStart = false;
    state.inactivityStage = 0;
    state.repositoryState = 'unknown';
    state.activeTurnEffort = '';
    state.queuedEffort = '';
    state.reconcileInFlight = false;
    state.hydrateInFlight = false;
    state.currentThreadId = validThreadId(threadId);
    if (previousThreadId) recoveryAttempts.delete(previousThreadId);
    state.eventFingerprints.clear();
    hydratePersistedProgress(state.currentThreadId);
    render();
    if (state.active && state.phase === 'retry') {
      openRecoveryEventSource();
      void reconcileActiveThread();
    }
  }

  function synchronizeVisibleThread() {
    const visible = routeThreadId();
    if (visible === state.currentThreadId) return false;
    if (!visible && !state.currentThreadId && !state.active && state.hidden) return false;
    resetForVisibleThread(visible);
    void hydrateVisibleThread();
    return true;
  }

  function progressSnapshot() {
    return {
      version: VERSION,
      active: state.active,
      completed: state.completed,
      hidden: state.hidden,
      startedAt: state.startedAtEpochMs,
      startedAtEpochMs: state.startedAtEpochMs,
      elapsedMs: state.startedAtEpochMs ? Math.max(0, Date.now() - state.startedAtEpochMs) : 0,
      turnId: state.turnId,
      threadId: state.currentThreadId,
      objective: state.objective,
      completedCommands: state.completedCommands,
      actionCount: state.actionCount,
      failedCommands: state.failedCommands,
      plannedSteps: state.plannedSteps,
      completedPlanSteps: state.completedPlanSteps,
      latestVerifiedResult: state.latestVerifiedResult,
      nextBoundedAction: state.nextBoundedAction,
      phase: state.phase,
      selectedEffort: state.selectedEffort,
      activeTurnEffort: state.activeTurnEffort,
      queuedEffort: state.queuedEffort,
      lastRealEventAt: state.lastRealEventAt,
      possibleSideEffect: state.possibleSideEffect,
      repositoryState: state.repositoryState,
      inactivityStage: state.inactivityStage,
      meaningfulUpdates: state.meaningfulUpdates.map((entry) => ({...entry})),
      technicalEvents: state.technicalEvents.map((entry) => ({...entry})),
      steps: state.steps.map((step) => ({...step})),
      html: state.panel ? state.panel.innerHTML : '',
    };
  }

  function eventItemId(event) {
    const params = event && event.params && typeof event.params === 'object' ? event.params : {};
    const item = params.item && typeof params.item === 'object' ? params.item : {};
    return clean(item.id || item.itemId || item.item_id);
  }

  function injectStyle() {
    if (document.getElementById(`${PANEL_ID}-style`)) return;
    const style = document.createElement('style');
    style.id = `${PANEL_ID}-style`;
    style.textContent = `
      #${PANEL_ID} { list-style:none; width:100%; max-width:min(45rem,calc(100vw - 20px)); margin:12px auto; padding:0 10px; box-sizing:border-box; font-family:Inter,system-ui,-apple-system,sans-serif; }
      #${PANEL_ID}.na-hidden { display:none !important; }
      #${PANEL_ID}.na-floating { position:fixed; left:50%; top:92px; transform:translateX(-50%); z-index:2147483000; pointer-events:none; }
      #${PANEL_ID} .na-card { pointer-events:auto; overflow:hidden; border:1px solid rgba(156,255,71,.34); border-radius:18px; background:linear-gradient(145deg,rgba(5,16,12,.97),rgba(5,10,18,.96)); box-shadow:0 18px 48px rgba(0,0,0,.42),inset 0 1px 0 rgba(255,255,255,.05); color:#eefcf3; backdrop-filter:blur(18px); }
      #${PANEL_ID} .na-header { width:100%; border:0; background:transparent; color:inherit; display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:10px; padding:13px 15px 11px; text-align:left; }
      #${PANEL_ID} .na-orb { width:12px; height:12px; border-radius:50%; background:#9cff47; box-shadow:0 0 0 5px rgba(156,255,71,.10),0 0 16px rgba(156,255,71,.65); }
      #${PANEL_ID}[data-state="working"] .na-orb { background:#9cff47; }
      #${PANEL_ID}[data-state="complete"] .na-orb { background:#39e6c5; box-shadow:0 0 0 5px rgba(57,230,197,.10),0 0 16px rgba(57,230,197,.55); }
      #${PANEL_ID} .na-kicker { display:block; color:#9cff47; font-size:11px; font-weight:800; letter-spacing:.11em; text-transform:uppercase; }
      #${PANEL_ID} .na-current { display:block; margin-top:2px; color:#f3fff6; font-size:14px; font-weight:650; line-height:1.35; }
      #${PANEL_ID} .na-time { color:#9fb2a8; font-size:12px; font-variant-numeric:tabular-nums; }
      #${PANEL_ID} .na-body { padding:0 15px 14px 37px; }
      #${PANEL_ID} .na-meta { margin:0 0 10px; color:#9fb2a8; font-size:11.5px; font-variant-numeric:tabular-nums; }
      #${PANEL_ID} .na-count { color:#dfffc9; font-weight:750; }
      #${PANEL_ID}.na-collapsed .na-body { display:none; }
      #${PANEL_ID} .na-steps { display:flex; flex-direction:column; gap:7px; margin:0; padding:0; list-style:none; }
      #${PANEL_ID} .na-step { display:grid; grid-template-columns:16px 1fr; gap:8px; align-items:start; color:#adbbb4; font-size:12.5px; line-height:1.4; }
      #${PANEL_ID} .na-step[data-status="active"] { color:#effff4; }
      #${PANEL_ID} .na-step[data-status="failed"] { color:#ffb4b4; }
      #${PANEL_ID} .na-mark { color:#39e6c5; font-weight:900; }
      #${PANEL_ID} .na-step[data-status="active"] .na-mark { color:#9cff47; }
      #${PANEL_ID} .na-step[data-status="failed"] .na-mark { color:#ff7474; }
    #${PANEL_ID}[data-state="retry"] .na-orb { background:#ffc857; box-shadow:0 0 0 5px rgba(255,200,87,.10),0 0 16px rgba(255,200,87,.55); }
    #${PANEL_ID}[data-state="failed"] .na-orb { background:#ff7474; box-shadow:0 0 0 5px rgba(255,116,116,.10),0 0 16px rgba(255,116,116,.55); }
    #${PANEL_ID} .na-fact { margin:7px 0 0; color:#cae4d6; font-size:12px; line-height:1.4; }
    #${PANEL_ID} .na-fact strong { color:#9cff47; }
    #${PANEL_ID} details { margin-top:10px; color:#9fb2a8; font-size:11px; }
    #${PANEL_ID} summary { cursor:pointer; color:#b9d6c5; }
    #${PANEL_ID} pre { max-height:220px; overflow:auto; padding:9px; border-radius:10px; background:#020806; color:#cce4d6; white-space:pre-wrap; overflow-wrap:anywhere; }
      #nemotron-autonomy-tools { position:fixed; right:10px; top:76px; z-index:2147482999; display:flex; flex-wrap:wrap; justify-content:flex-end; gap:6px; max-width:calc(100vw - 20px); font-family:Inter,system-ui,sans-serif; }
      #nemotron-autonomy-tools button,#nemotron-autonomy-tools .na-tool-status { border:1px solid rgba(118,185,0,.42); border-radius:999px; padding:7px 10px; background:rgba(5,16,12,.92); color:#eaffdf; font-size:11px; font-weight:700; box-shadow:0 7px 20px rgba(0,0,0,.28); backdrop-filter:blur(14px); }
      #nemotron-autonomy-tools button:disabled { opacity:.48; }
      #nemotron-autonomy-tools .na-tool-status { border-color:rgba(57,230,197,.35); color:#9fe9dc; }
      .na-repaired-notice { margin:8px 0; padding:10px 12px; border:1px solid rgba(118,185,0,.35); border-radius:12px; background:rgba(12,25,16,.88); color:#ccefb6; font-size:13px; }
      .na-provider-error { display:block; margin:10px 0; padding:12px 14px; border:1px solid rgba(255,153,102,.38); border-radius:14px; background:linear-gradient(145deg,rgba(41,18,15,.92),rgba(20,12,18,.94)); color:#ffd8c8; font-size:14px; line-height:1.45; white-space:normal; }
      .conversation-item.na-internal-compaction { display:none !important; }
      #nemotron-session-cleanup-card { margin:12px 10px; padding:16px; border:1px solid rgba(255,67,110,.52); border-radius:16px; background:linear-gradient(145deg,rgba(55,10,25,.94),rgba(24,10,18,.96)); color:#ffe9ef; }
      #nemotron-session-cleanup-card h3 { margin:0 0 8px; font-size:16px; }
      #nemotron-session-cleanup-card p { margin:0 0 12px; color:#f0cbd5; font-size:12px; line-height:1.5; }
      #nemotron-session-cleanup-card button { width:100%; border:0; border-radius:12px; padding:12px; background:#db0038; color:white; font-weight:800; }
      #nemotron-session-cleanup-card button:disabled { opacity:.55; }
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function ensurePanel() {
    injectStyle();
    if (!state.panel) {
      state.panel = document.createElement('li');
      state.panel.id = PANEL_ID;
      state.panel.setAttribute('role', 'status');
      state.panel.setAttribute('aria-live', 'polite');
      state.panel.className = 'na-hidden';
    }
    const anchor = document.querySelector('.conversation-bottom-anchor');
    if (anchor && anchor.parentNode) {
      if (state.panel.parentNode !== anchor.parentNode || state.panel.nextSibling !== anchor) {
        anchor.parentNode.insertBefore(state.panel, anchor);
      }
      state.panel.classList.remove('na-floating');
    } else if (document.body && state.panel.parentNode !== document.body) {
      document.body.appendChild(state.panel);
      state.panel.classList.add('na-floating');
    }
    return state.panel;
  }

  function currentLabel() {
    const active = [...state.steps].reverse().find((step) => step.status === 'active');
    if (active) return active.label;
    if (state.completed) return 'Mission complete';
    return state.objective || 'Preparing the next step';
  }

  function render() {
    if (!document.documentElement) return;
    const panel = ensurePanel();
    panel.classList.toggle('na-hidden', state.hidden);
    panel.classList.toggle('na-collapsed', state.collapsed);
    panel.dataset.state = state.phase;
    if (state.hidden) return;
    const elapsed = state.startedAtEpochMs ? formatElapsed(Date.now() - state.startedAtEpochMs) : '0:00';
    const updates = state.meaningfulUpdates.slice(-5);
    const steps = updates.map((step) => {
                                         const mark = step.status === 'completed' ? '✓' : step.status === 'failed' ? '!' :
                                                                                                                     '●';
                                         const attempts = Number(step.attempts || 1);
                                         const suffix = attempts > 1 ? ` <span class="na-count">×${attempts}</span>` : '';
                                         return `<li class="na-step" data-status="${step.status}"><span class="na-mark">${mark}</span><span>${escapeHtml(step.label)}${suffix}</span></li>`;
                                       })
                      .join('');
    const completedSteps = state.steps.filter((step) => step.status === 'completed').length;
    const updateAge = state.lastRealEventAt ? Math.max(0, Math.floor((Date.now() - state.lastRealEventAt) / 1000)) : 0;
    const stepCount = state.plannedSteps ? `${state.completedPlanSteps}/${state.plannedSteps} planned steps complete` : `${completedSteps} steps complete`;
    const counts = `${stepCount} · ${state.actionCount} actions${state.failedCommands ? ` · ${state.failedCommands} failed` : ''} · live ${updateAge}s ago`;
    const latest = state.latestVerifiedResult ? `<p class="na-fact"><strong>Latest verified result:</strong> ${escapeHtml(state.latestVerifiedResult)}</p>` : '';
    const next = state.nextBoundedAction ? `<p class="na-fact"><strong>Next bounded action:</strong> ${escapeHtml(state.nextBoundedAction)}</p>` : '';
    const technical = state.technicalEvents.slice(-5).map((entry) => {
                                                       const output = entry.output ? `\n${entry.output}` : '';
                                                       return `[${entry.status}] ${entry.command}${output}`;
                                                     })
                          .join('\n\n');
    const details = technical ? `<details><summary>Technical details (${state.technicalEvents.length})</summary><pre>${escapeTechnical(technical)}</pre></details>` : '';
    const kicker = state.phase === 'failed' ? 'NEMOTRON stopped' : state.phase === 'retry' ? 'NEMOTRON retrying' :
        state.completed                                                                    ? 'NEMOTRON finished' :
                                                                                             'NEMOTRON working';
    panel.innerHTML = `<div class="na-card"><button class="na-header" type="button" aria-label="Toggle live progress"><span class="na-orb"></span><span><span class="na-kicker">${kicker}</span><span class="na-current">${escapeHtml(currentLabel())}</span></span><span class="na-time">${elapsed}</span></button><div class="na-body"><div class="na-meta">${escapeHtml(counts)}</div>${latest}${next}<ol class="na-steps">${steps}</ol>${details}</div></div>`;
    const header = panel.querySelector('.na-header');
    if (header) header.addEventListener('click', () => {
      state.collapsed = !state.collapsed;
      render();
    });
  }

  function recordMeaningfulUpdate(label, status = 'active', identity = '', evidence = '') {
    const safeLabel = safeText(label, 320);
    const safeIdentity = safeText(identity, 360) || fingerprintDigest(`${status}:${safeLabel}`);
    const safeEvidence = safeText(evidence, 320);
    if (!safeLabel) return;
    let existingIndex = -1;
    for (let index = state.meaningfulUpdates.length - 1; index >= 0; index -= 1) {
      if (state.meaningfulUpdates[index].id === safeIdentity) {
        existingIndex = index;
        break;
      }
    }
    const previous = existingIndex >= 0 ? state.meaningfulUpdates.splice(existingIndex, 1)[0] : null;
    state.meaningfulUpdates.push({
      id: safeIdentity,
      label: safeLabel,
      status: /^(?:active|completed|failed|retry)$/u.test(status) ? status : 'active',
      evidence: safeEvidence,
      at: Date.now(),
      attempts: previous ? Math.max(1, Number(previous.attempts || 1) + (previous.status === status ? 1 : 0)) : 1,
    });
    if (state.meaningfulUpdates.length > MAX_MEANINGFUL_UPDATES) {
      state.meaningfulUpdates = state.meaningfulUpdates.slice(-MAX_MEANINGFUL_UPDATES);
    }
  }

  function completeActiveStep() {
    for (let index = state.steps.length - 1; index >= 0; index -= 1) {
      if (state.steps[index].status === 'active') {
        state.steps[index].status = 'completed';
        recordMeaningfulUpdate(state.steps[index].label, 'completed', state.steps[index].identity || state.steps[index].label);
        return;
      }
    }
  }

  function addStep(label, identity) {
    const safeLabel = safeText(label, 320);
    const stableIdentity = safeText(identity, 360);
    if (!safeLabel) return;
    const last = state.steps[state.steps.length - 1];
    const sameStep = last && (stableIdentity ? last.identity === stableIdentity : !last.identity && last.label === safeLabel);
    if (sameStep && Date.now() - Number(last.updatedAt || 0) < 120000) {
      last.attempts = Number(last.attempts || 1) + 1;
      last.status = 'active';
      last.updatedAt = Date.now();
      markRealEvent();
      state.hidden = false;
      recordMeaningfulUpdate(safeLabel, 'active', stableIdentity || safeLabel);
      persistProgress();
      render();
      return;
    }
    completeActiveStep();
    state.steps.push({label: safeLabel, identity: stableIdentity, status: 'active', attempts: 1, updatedAt: Date.now()});
    if (state.steps.length > 12) state.steps = state.steps.slice(-12);
    markRealEvent();
    recordMeaningfulUpdate(safeLabel, 'active', stableIdentity || safeLabel);
    state.hidden = false;
    state.completed = false;
    state.phase = 'working';
    persistProgress();
    render();
  }

  function startTurn(turnId, objective = '', startedAtEpochMs = Date.now()) {
    if (state.hideTimer) window.clearTimeout(state.hideTimer);
    if (state.compactionRecoveryTimer) window.clearTimeout(state.compactionRecoveryTimer);
    closeRecoveryEventSource();
    state.compactionRecoveryTimer = null;
    state.compactionPending = false;
    state.active = true;
    state.completed = false;
    state.phase = 'working';
    state.hidden = false;
    state.collapsed = false;
    state.startedAtEpochMs = Number(startedAtEpochMs) > 0 ? Number(startedAtEpochMs) : Date.now();
    state.turnId = safeText(turnId, 256) || `turn-${state.startedAtEpochMs}`;
    state.objective = safeText(objective, 420) || 'Starting the requested task';
    state.steps = [{label: state.objective, identity: 'objective', status: 'active', attempts: 1, updatedAt: Date.now()}];
    state.meaningfulUpdates = [];
    recordMeaningfulUpdate(state.objective, 'active', 'objective');
    state.completedCommands = 0;
    state.actionCount = 0;
    state.failedCommands = 0;
    state.plannedSteps = 0;
    state.completedPlanSteps = 0;
    state.latestVerifiedResult = '';
    state.nextBoundedAction = '';
    state.technicalEvents = [];
    markRealEvent();
    state.activeCommandKey = '';
    state.activeCommandKeys.clear();
    state.consecutiveFailureKey = '';
    state.consecutiveFailureCount = 0;
    state.interruptionRequested = false;
    state.lastReconcileAt = 0;
    state.lastSocketEventAt = 0;
    state.lastHumanCheckpointAt = Date.now();
    state.lastAuthoritativeReadAt = 0;
    state.responseOnlyRecoveries = 0;
    state.activeTurnEffort = normalizeEffort(state.activeTurnEffort || state.selectedEffort);
    state.possibleSideEffect = false;
    state.expectedTurnStart = false;
    state.repositoryState = 'unknown';
    persistProgress();
    render();
  }

  function normalizeEffort(value) {
    const normalized = clean(value).toLowerCase().replace(/[ _-]+/gu, '');
    const aliases = {
      none: 'none', minimal: 'minimal', low: 'low', medium: 'medium', high: 'high',
      xhigh: 'xhigh', extrahigh: 'xhigh',
    };
    return aliases[normalized] || 'high';
  }

  function effortLabel(value) {
    const effort = normalizeEffort(value);
    return effort === 'xhigh' ? 'Extra high' : `${effort.charAt(0).toUpperCase()}${effort.slice(1)}`;
  }

  function failActiveStep() {
    for (let index = state.steps.length - 1; index >= 0; index -= 1) {
      if (state.steps[index].status === 'active') {
        state.steps[index].status = 'failed';
        state.steps[index].updatedAt = Date.now();
        recordMeaningfulUpdate(state.steps[index].label, 'failed', state.steps[index].identity || state.steps[index].label);
        return;
      }
    }
  }

  function commandKey(command) {
    return safeText(command, 1200).toLowerCase();
  }

  function itemOutput(item) {
    const values = [];
    for (const key of ['aggregatedOutput', 'output', 'stdout', 'stderr', 'error']) {
      const value = item && item[key];
      if (typeof value === 'string' && value) values.push(`${key}:\n${value}`);
    }
    const joined = redactSensitive(values.join('\n'));
    return joined.length > 12000 ? `${joined.slice(0, 12000)}\n[…truncated in progress panel…]` : joined;
  }

  function rememberTechnical(item, status) {
    const command = safeText(item && item.command, 1200);
    if (!command) return;
    state.technicalEvents.push({command, output: itemOutput(item), status});
    if (state.technicalEvents.length > 24) state.technicalEvents = state.technicalEvents.slice(-24);
  }

  function verifiedEvidence(item) {
    const command = safeText(item && item.command, 1200);
    const normalizedCommand = command.toLowerCase();
    const rawOutput = itemOutput(item);
    if (/\bcommand\s+-v\b|\bwhich\s+(?:-[a-z]+\s+)?/u.test(normalizedCommand)) {
      const paths = new Set(rawOutput.match(/\/data\/data\/com\.termux\/files\/[^\s,"'}]+/gu) || []);
      if (paths.size) return `Verified ${paths.size} automation and development tools are installed and ready`;
    }
    if (/\bcodex-gallery\s+(?:recent|search|inspect|faces|semantic)\b/u.test(normalizedCommand)) {
      const count = rawOutput.match(/"count"\s*:\s*(\d+)/u);
      if (count) return `Gallery scan returned ${count[1]} verified matching image record${count[1] === '1' ? '' : 's'}`;
    }
    const checksum = rawOutput.match(/(?:^|\n)([a-f0-9]{64})[ \t]+[*]?([^\r\n]*\/[^\r\n]+)$/imu);
    if (checksum && /\bsha256sum\b|\b(?:apksigner|keytool)\b|build-nemotron-unrestricted\.sh/u.test(normalizedCommand)) {
      return `SHA-256 read back for ${safeText(checksum[2], 100)}: ${checksum[1].slice(0, 16)}…`;
    }
    const signerDigest = rawOutput.match(/SHA-256\s+(?:certificate\s+)?digest\s*:\s*([a-f0-9]{64})/iu);
    const apkArgument = command.match(/(?:^|\s|["'])([^\s"']+\.apk)(?=$|\s|["'])/iu);
    if (signerDigest && apkArgument && /\bapksigner\b/u.test(normalizedCommand)) {
      return `Signer digest read back for ${safeText(apkArgument[1], 100)}: ${signerDigest[1].slice(0, 16)}…`;
    }
    const buildHash = rawOutput.match(/\b(?:APK_)?SHA256\s*[:=]\s*([a-f0-9]{64})\b/iu);
    const buildPath = rawOutput.match(/\b(?:APK_)?PATH\s*[:=]\s*([^\r\n]+\.apk)\b/iu);
    if (buildHash && buildPath && /build-nemotron-unrestricted\.sh/u.test(normalizedCommand)) {
      return `Built APK hash read back for ${safeText(buildPath[1], 100)}: ${buildHash[1].slice(0, 16)}…`;
    }
    const marker = rawOutput.match(/\b([A-Z][A-Z0-9_]{3,}_OK)\b/u);
    const markerCommand = /(?:^|\s)(?:bash\s+)?(?:\.\/)?(?:isolation-preflight|build-nemotron-unrestricted)\.sh(?:\s|$)|\b(?:python(?:3)?\s+(?:-m\s+)?(?:unittest|pytest)|node\s+\S*(?:harness|test)\S*|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test)\b/u;
    if (marker && markerCommand.test(normalizedCommand)) return `Verified marker: ${marker[1]}`;
    const tests = rawOutput.match(/\b(\d+\s+(?:tests?\s+)?(?:passed|successful|succeeded)|OK\s*\(.*?tests?)/iu);
    if (tests && /(?:unittest|pytest|vitest|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|gradle\S*\s+test)/u.test(normalizedCommand)) {
      return `Test readback: ${safeText(tests[1], 120)}`;
    }
    const packagePath = rawOutput.match(/\bpackage:(\/[\w./+,:=@%~-]+\.apk)\b/u);
    if (packagePath && /(?:\bpm|\bcodex-pm)\s+path\b|\bcodex-package\s+(?:inspect|verify)\b/u.test(normalizedCommand)) {
      return `Installed APK path read back: ${safeText(packagePath[1], 120)}`;
    }
    const jsonStart = rawOutput.indexOf('{');
    if (jsonStart >= 0 && /(?:\/vault-health|\/health\b|free-mode\/status|codex-identity)/u.test(normalizedCommand)) {
      try {
        const decoded = JSON.parse(rawOutput.slice(jsonStart));
        if (decoded && decoded.status === 'ok') {
          const identity = safeText(decoded.app || decoded.provider || decoded.service || 'service', 80);
          return `${identity} health returned status ok`;
        }
      } catch (_) {
      }
    }
    return '';
  }

  function commandFailed(item) {
    const status = clean(item && item.status).toLowerCase();
    const exitCode = Number(item && (item.exitCode ?? item.exit_code));
    if (/failed|error|cancelled|canceled/u.test(status)) return true;
    if (Number.isFinite(exitCode) && exitCode !== 0) return true;
    return /process exited with code [1-9]|failed to parse function arguments|\baborted\b/iu.test(JSON.stringify(item || {}));
  }

  async function recoverRepeatedFailureLoop() {
    if (state.interruptionRequested) return;
    state.interruptionRequested = true;
    state.active = true;
    state.phase = 'retry';
    const recoveryLabel = state.possibleSideEffect
      ? 'Three identical failures detected — preserving state without replaying possible side effects'
      : 'Switching strategy after three identical failures — progress is preserved';
    state.steps.push({label: recoveryLabel, identity: 'three-failure-recovery', status: 'active', attempts: 1, updatedAt: Date.now()});
    recordMeaningfulUpdate(recoveryLabel, 'retry', 'three-failure-recovery');
    if (state.steps.length > 12) state.steps = state.steps.slice(-12);
    setToolbarStatus(state.possibleSideEffect ? 'Unsafe replay blocked · reconciling only' : 'Changing strategy · session preserved');
    persistProgress();
    render();
    if (!state.currentThreadId || !state.turnId || state.turnId === 'unknown-turn') return;
    try {
      await rpc('thread/read', {threadId: state.currentThreadId, includeTurns: true});
      state.lastAuthoritativeReadAt = Date.now();
      state.nextBoundedAction = 'The active agent must choose a materially different strategy without creating a replacement turn';
      setToolbarStatus('Repeated failure detected · original turn remains authoritative');
      openRecoveryEventSource();
      await reconcileActiveThread();
    } catch (_) {
      state.phase = 'retry';
      setToolbarStatus('Repeated failure detected · waiting for authoritative thread state');
      openRecoveryEventSource();
      persistProgress();
      render();
    }
  }

  function notifyCompletion(turnId, outcome) {
    const id = clean(turnId || state.turnId || 'unknown-turn');
    if (completedTurns.has(id)) return;
    completedTurns.add(id);
    if (completedTurns.size > 64) completedTurns.delete(completedTurns.values().next().value);
    try {
      if (window.NemotronAutonomy && typeof window.NemotronAutonomy.missionComplete === 'function') {
        window.NemotronAutonomy.missionComplete(window.__NEMOTRON_BRIDGE_TOKEN__ || '', JSON.stringify({
          turnId: id,
          threadId: state.currentThreadId,
          outcome,
          durationMs: Math.round(state.startedAtEpochMs ? Date.now() - state.startedAtEpochMs : 0),
          effort: state.activeTurnEffort || state.selectedEffort,
          actionCount: state.actionCount,
          completedActions: state.completedCommands,
          failureCount: state.failedCommands,
          plannedSteps: state.plannedSteps,
        }));
      }
    } catch (_) {
    }
    window.dispatchEvent(new CustomEvent('nemotron-autonomy:mission-complete', {detail: {turnId: id, outcome}}));
  }

  function notifyMissionStarted(turnId) {
    const id = safeText(turnId, 256);
    if (!id || id.startsWith('pending-') || registeredActiveTurns.has(id)) return;
    registeredActiveTurns.add(id);
    if (registeredActiveTurns.size > 64) registeredActiveTurns.delete(registeredActiveTurns.values().next().value);
    try {
      if (window.NemotronAutonomy && typeof window.NemotronAutonomy.missionStarted === 'function') {
        window.NemotronAutonomy.missionStarted(window.__NEMOTRON_BRIDGE_TOKEN__ || '', JSON.stringify({
          turnId: id,
          threadId: state.currentThreadId,
          effort: state.activeTurnEffort || state.selectedEffort,
          startedAt: state.startedAtEpochMs,
        }));
      }
    } catch (_) {
    }
  }

  function completeTurn(turnId) {
    completeActiveStep();
    closeRecoveryEventSource();
    state.active = false;
    state.completed = true;
    state.phase = 'complete';
    state.lastCompletedAt = Date.now();
    if (state.currentThreadId) {
      recoveryAttempts.delete(state.currentThreadId);
      const timer = recoveryTimers.get(state.currentThreadId);
      if (timer) window.clearTimeout(timer);
      recoveryTimers.delete(state.currentThreadId);
    }
    state.hidden = false;
    recordMeaningfulUpdate('Final response delivered — the turn reached a verified terminal state', 'completed', `terminal:${turnId || state.turnId}`);
    persistProgress();
    render();
    notifyCompletion(turnId, 'completed');
    if (state.hideTimer) window.clearTimeout(state.hideTimer);
    state.hideTimer = null;
  }

  function textFromMessageContent(value) {
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(textFromMessageContent).filter(Boolean).join(' ');
    if (!value || typeof value !== 'object') return '';
    for (const key of ['text', 'content', 'message', 'output_text']) {
      const text = textFromMessageContent(value[key]);
      if (text) return text;
    }
    return '';
  }

  function substantiveAgentMessage(turn) {
    const items = Array.isArray(turn && turn.items) ? turn.items : [];
    return items.some((item) => {
      if (clean(item && item.type).toLowerCase() !== 'agentmessage') return false;
      const text = clean(textFromMessageContent(item));
      return text.length >= 2 && !/^(?:null|undefined|\[object object\])$/iu.test(text);
    });
  }

  async function verifyTerminalCompletion(event) {
    const params = event && event.params && typeof event.params === 'object' ? event.params : {};
    const suppliedTurn = params.turn && typeof params.turn === 'object' ? params.turn : null;
    const terminalTurnId = eventTurnId(event);
    if (substantiveAgentMessage(suppliedTurn)) {
      completeTurn(terminalTurnId);
      return;
    }
    let authoritativeTurn = suppliedTurn;
    try {
      const result = await rpc('thread/read', {threadId: state.currentThreadId, includeTurns: true});
      const thread = result && result.thread && typeof result.thread === 'object' ? result.thread : null;
      const turns = Array.isArray(thread && thread.turns) ? thread.turns : [];
      authoritativeTurn = turns.find((turn) => clean(turn && turn.id) === terminalTurnId)
        || (turns.length ? turns[turns.length - 1] : authoritativeTurn);
      state.lastAuthoritativeReadAt = Date.now();
    } catch (_) {
      state.phase = 'retry';
      state.hidden = false;
      recordMeaningfulUpdate('Terminal event received without a response — authoritative thread read is retrying', 'retry', `missing-response-read:${terminalTurnId}`);
      persistProgress();
      render();
      openRecoveryEventSource();
      return;
    }
    if (substantiveAgentMessage(authoritativeTurn)) {
      completeTurn(terminalTurnId);
      return;
    }
    state.responseOnlyRecoveries = Math.min(MAX_RESPONSE_ONLY_RECOVERIES, state.responseOnlyRecoveries + 1);
    state.active = false;
    state.completed = false;
    state.phase = 'failed';
    state.hidden = false;
    state.expectedTurnStart = false;
    state.nextBoundedAction = 'A later explicit user message may continue this thread; lifecycle recovery will never submit one automatically';
    recordMeaningfulUpdate(
        'The provider ended without a substantive answer — the original turn is preserved and was not replayed',
        'failed', `missing-response:${terminalTurnId}`);
    setToolbarStatus('Empty provider response · original turn preserved without replay');
    persistProgress();
    render();
  }

  function failTurn(turnId) {
    completeActiveStep();
    closeRecoveryEventSource();
    state.active = false;
    state.completed = false;
    state.phase = 'failed';
    state.hidden = false;
    state.steps.push({label: 'The task stopped before completion', identity: 'terminal-failure', status: 'failed'});
    recordMeaningfulUpdate('The task stopped before completion', 'failed', 'terminal-failure');
    persistProgress();
    render();
    notifyCompletion(turnId, 'failed');
  }

  async function rpc(method, params) {
    const controller = typeof window.AbortController === 'function' ? new window.AbortController() : null;
    let timeoutId = null;
    const request = NativeFetch('/codex-api/rpc', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({method, params}),
      ...(controller ? {signal: controller.signal} : {}),
    });
    const timeout = new Promise((_, reject) => {
      timeoutId = window.setTimeout(() => {
        if (controller) controller.abort();
        reject(new Error(`RPC ${method} timed out after ${RPC_TIMEOUT_MS}ms`));
      }, RPC_TIMEOUT_MS);
    });
    let response;
    try {
      response = await Promise.race([request, timeout]);
    } finally {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    }
    const text = await response.text();
    let envelope = null;
    try {
      envelope = JSON.parse(text);
    } catch (_) {
    }
    if (!response.ok || !envelope || !('result' in envelope)) {
      throw new Error((envelope && envelope.error && envelope.error.message) || text.slice(0, 300) || `RPC ${method} failed`);
    }
    return envelope.result;
  }

  function setToolbarStatus(value) {
    state.toolbarStatus = safeText(value, 180) || 'Ready';
    const status = state.toolbar && state.toolbar.querySelector('.na-tool-status');
    if (status) status.textContent = state.toolbarStatus;
  }

  function threadIsActive(thread) {
    const status = thread && thread.status;
    const activeStates = new Set(['active', 'inprogress', 'in_progress', 'running', 'pending']);
    if (activeStates.has(clean(status).toLowerCase())) return true;
    if (status && typeof status === 'object') {
      return activeStates.has(clean(status.type || status.status || Object.keys(status)[0]).toLowerCase());
    }
    const turns = Array.isArray(thread && thread.turns) ? thread.turns : [];
    return turns.some((turn) => activeStates.has(clean(turn && turn.status).toLowerCase()));
  }

  async function archiveIdleThreads() {
    const button = state.toolbar && state.toolbar.querySelector('[data-action="archive"]');
    if (button) button.disabled = true;
    try {
      setToolbarStatus('Inventory…');
      const all = [];
      let cursor = null;
      do {
        const page = await rpc('thread/list', {archived: false, limit: 100, sortKey: 'updated_at', modelProviders: [], cursor});
        all.push(...(Array.isArray(page.data) ? page.data : []));
        cursor = typeof page.nextCursor === 'string' && page.nextCursor ? page.nextCursor : null;
      } while (cursor);
      const skipped = all.filter(threadIsActive);
      const candidates = all.filter((thread) => thread && thread.id && !threadIsActive(thread));
      if (!candidates.length) {
        setToolbarStatus(`0 cleaned · ${skipped.length} active`);
        return;
      }
      let next = 0, archived = 0, failed = 0;
      async function worker() {
        while (next < candidates.length) {
          const item = candidates[next++];
          try {
            await rpc('thread/archive', {threadId: item.id});
            archived += 1;
          } catch (_) {
            failed += 1;
          }
          setToolbarStatus(`${archived}/${candidates.length} cleaned`);
        }
      }
      await Promise.all([worker(), worker(), worker(), worker(), worker(), worker(), worker(), worker()]);
      setToolbarStatus(`${archived} cleaned · ${skipped.length} active · ${failed} failed`);
      window.setTimeout(() => { void refreshWorkspace(); }, 900);
    } catch (error) {
      setToolbarStatus(`Archive error: ${clean(error.message).slice(0, 80)}`);
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function listThreadsByArchiveState(archived) {
    const all = [];
    let cursor = null;
    do {
      const page = await rpc('thread/list', {archived: Boolean(archived), limit: 100, sortKey: 'updated_at', modelProviders: [], cursor});
      all.push(...(Array.isArray(page.data) ? page.data : []));
      cursor = typeof page.nextCursor === 'string' && page.nextCursor ? page.nextCursor : null;
    } while (cursor);
    return all;
  }

  function openCleanupBackupDatabase() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        reject(new Error('IndexedDB backup storage is unavailable'));
        return;
      }
      const request = window.indexedDB.open('nemotron-session-cleanup-backups', 1);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains('backups')) database.createObjectStore('backups', {keyPath: 'id'});
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('Could not open session backup storage'));
    });
  }

  async function backupThreadsForCleanup(threads) {
    const snapshots = [];
    for (const thread of threads) {
      snapshots.push(await rpc('thread/read', {threadId: thread.id, includeTurns: true}));
    }
    const id = `sessions-${new Date(Date.now()).toISOString().replace(/[:.]/gu, '-')}`;
    const database = await openCleanupBackupDatabase();
    await new Promise((resolve, reject) => {
      const transaction = database.transaction('backups', 'readwrite');
      transaction.objectStore('backups').put({id, createdAt: Date.now(), threadCount: threads.length, snapshots});
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error || new Error('Session backup transaction failed'));
      transaction.onabort = () => reject(transaction.error || new Error('Session backup transaction aborted'));
    });
    database.close();
    return id;
  }

  async function deleteAllSessionsAndThreads() {
    const button = document.querySelector && document.querySelector('#nemotron-session-cleanup-card button');
    if (button) button.disabled = true;
    try {
      setToolbarStatus('Checking every active and archived session…');
      const inventory = [...await listThreadsByArchiveState(false), ...await listThreadsByArchiveState(true)];
      const unique = Array.from(new Map(inventory.filter((thread) => thread && thread.id).map((thread) => [thread.id, thread])).values());
      const active = unique.filter(threadIsActive);
      if (active.length) throw new Error(`${active.length} active session(s) must finish or be stopped before cleanup`);
      if (!unique.length) {
        setToolbarStatus('No sessions or threads exist · projects and data are unchanged');
        return {deleted: 0, backupId: ''};
      }
      const confirmation = clean(window.prompt(
          `This deletes ${unique.length} chat session(s) and thread(s) only. Projects, project files, skills, plugins, accounts, settings, models, memories, and automations remain intact. Type DELETE ALL SESSIONS AND THREADS to continue.`) || '');
      if (confirmation !== 'DELETE ALL SESSIONS AND THREADS') throw new Error('Cleanup cancelled because the exact confirmation was not entered');
      setToolbarStatus(`Backing up ${unique.length} session(s) before deletion…`);
      const backupId = await backupThreadsForCleanup(unique);
      let deleted = 0;
      for (const thread of unique) {
        await rpc('thread/delete', {threadId: thread.id});
        deleted += 1;
        setToolbarStatus(`Deleted ${deleted}/${unique.length} sessions · backup ${backupId}`);
      }
      const remaining = [...await listThreadsByArchiveState(false), ...await listThreadsByArchiveState(true)];
      if (remaining.some((thread) => thread && thread.id)) throw new Error('Cleanup verification found remaining sessions');
      setToolbarStatus(`${deleted} sessions deleted and verified · projects and data preserved · backup ${backupId}`);
      window.setTimeout(() => { void refreshWorkspace(); }, 900);
      return {deleted, backupId};
    } catch (error) {
      setToolbarStatus(`Session cleanup stopped safely: ${clean(error.message).slice(0, 110)}`);
      throw error;
    } finally {
      if (button) button.disabled = false;
    }
  }

  function ensureSessionCleanupCard() {
    if (!document.querySelector || document.getElementById('nemotron-session-cleanup-card')) return;
    const panel = document.querySelector('.sidebar-settings-panel');
    if (!panel) return;
    const card = document.createElement('section');
    card.id = 'nemotron-session-cleanup-card';
    card.innerHTML = '<h3>Clean sessions and threads</h3><p>Deletes every chat session and thread after a durable origin-private browser backup. Projects, project files, plugins, skills, accounts, settings, models, memories, and automations stay intact. Active work is always refused.</p><button type="button">Delete all sessions and threads</button>';
    const button = card.querySelector('button');
    if (button) button.addEventListener('click', () => { void deleteAllSessionsAndThreads().catch(() => {}); });
    panel.appendChild(card);
  }

  async function addProject() {
    const path = clean(window.prompt('Absolute folder path to add as a project. Existing folders only; no files will be changed.') || '');
    if (!path) return;
    if (!path.startsWith('/data/data/com.termux/files/home/')) {
      setToolbarStatus('Project must be an absolute Termux-home folder');
      return;
    }
    try {
      const response = await NativeFetch('/codex-api/project-root', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path, createIfMissing: false, label: ''})});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'project validation failed');
      setToolbarStatus('Project added');
      window.setTimeout(() => { void refreshWorkspace(); }, 700);
    } catch (error) {
      setToolbarStatus(`Project error: ${clean(error.message).slice(0, 80)}`);
    }
  }

  async function removeProject() {
    try {
      const response = await NativeFetch('/codex-api/workspace-roots-state');
      const envelope = await response.json();
      const roots = envelope && envelope.data && Array.isArray(envelope.data.order) ? envelope.data.order : [];
      const path = clean(window.prompt(`Exact project path to remove from the GUI only (no files will be deleted):\n${roots.join('\n')}`) || '');
      if (!path) return;
      if (!roots.includes(path)) throw new Error('path is not an active GUI project');
      if (!window.confirm(`Remove ${path} from the project list? Its folder, Git data, sessions, skills, and files will remain untouched.`)) return;
      const data = envelope.data;
      const labels = {...(data.labels || {})};
      delete labels[path];
      const next = {
        order: roots.filter((item) => item !== path),
        labels,
        active: (data.active || []).filter((item) => item !== path),
        projectOrder: (data.projectOrder || []).filter((item) => item !== path),
        remoteProjects: data.remoteProjects || [],
      };
      const saved = await NativeFetch('/codex-api/workspace-roots-state', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(next)});
      if (!saved.ok) throw new Error('workspace metadata update failed');
      setToolbarStatus('Project removed from GUI');
      window.setTimeout(() => { void refreshWorkspace(); }, 700);
    } catch (error) {
      setToolbarStatus(`Project error: ${clean(error.message).slice(0, 80)}`);
    }
  }

  async function refreshWorkspace() {
    setToolbarStatus('Synchronizing current thread…');
    synchronizeVisibleThread();
    try {
      await rpc('config/read', {});
      if (state.active) await reconcileActiveThread();
      else await hydrateVisibleThread();
      setToolbarStatus('Current thread synchronized · draft and route preserved');
      window.dispatchEvent(new CustomEvent('nemotron-autonomy:soft-refresh', {detail: {threadId: state.currentThreadId}}));
    } catch (error) {
      setToolbarStatus(`Synchronization retry queued: ${clean(error.message).slice(0, 60)}`);
      if (state.currentThreadId) scheduleRecovery(state.currentThreadId, 'manual soft refresh');
    }
  }

  function ensureToolbar() {
    if (!document.body) return;
    if (!state.toolbar) {
      state.toolbar = document.createElement('div');
      state.toolbar.id = 'nemotron-autonomy-tools';
      state.toolbar.innerHTML = '<button type="button" data-action="refresh" title="Reconnect and reload the isolated NEMOTRON workspace">↻ Refresh</button><button type="button" data-action="archive" title="Immediately remove every non-running thread from the GUI while preserving projects, files, skills, and archived session data">Force-clean idle threads</button><button type="button" data-action="add">+ Project</button><button type="button" data-action="remove">− Project</button><span class="na-tool-status">Ready</span>';
      state.toolbar.querySelector('[data-action="refresh"]').addEventListener('click', refreshWorkspace);
      state.toolbar.querySelector('[data-action="archive"]').addEventListener('click', archiveIdleThreads);
      state.toolbar.querySelector('[data-action="add"]').addEventListener('click', addProject);
      state.toolbar.querySelector('[data-action="remove"]').addEventListener('click', removeProject);
    }
    if (!state.toolbar.isConnected) document.body.appendChild(state.toolbar);
  }

  function transientFailure(value) {
    return /(server\s*overloaded|overloaded|429|connection\s*failed|stream\s*disconnected|error\s+sending\s+request|network\s+error|connection\s+reset|broken\s+pipe|timeout|temporar|unavailable|tool_choice|tools must be set|502|503|504)/iu.test(clean(value));
  }

  function isLiveEventSocket(url) {
    try {
      return new URL(String(url), window.location.href).pathname === '/codex-api/ws';
    } catch (_) {
      return false;
    }
  }

  function scheduleLiveSocketWarning(generation) {
    if (liveSocketWarningTimer) window.clearTimeout(liveSocketWarningTimer);
    liveSocketWarningTimer = window.setTimeout(() => {
      liveSocketWarningTimer = null;
      if (!pageUnloading && generation === liveSocketGeneration) {
        setToolbarStatus('Live updates reconnecting · Refresh available');
      }
    }, 30000);
  }

  function friendlyProviderError(value) {
    const text = String(value == null ? '' : value).trim();
    if (transientFailure(text) && !text.startsWith('{')) {
      return 'The connection was interrupted before the provider finished. NEMOTRON is preserving this session and resuming automatically from verified thread state.';
    }
    if (!text.startsWith('{') || text.length > 4000) return '';
    try {
      const parsed = JSON.parse(text);
      const message = clean(parsed && parsed.error && parsed.error.message);
      if (!message) return '';
      if (/when using tool_choice, tools must be set/iu.test(message)) {
        return 'NEMOTRON encountered a temporary tool-routing mismatch. The repaired runtime will retry with a valid tool configuration.';
      }
      return `NEMOTRON request paused: ${safeText(message, 300)}`;
    } catch (_) {
      return '';
    }
  }

  function humanizeProviderErrorTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const parent = node.parentElement;
    if (!parent || /^(SCRIPT|STYLE|TEXTAREA|INPUT)$/u.test(parent.tagName)) return;
    const friendly = friendlyProviderError(node.nodeValue);
    if (!friendly) return;
    node.nodeValue = friendly;
    parent.classList.add('na-provider-error');
  }

  function humanizeProviderErrors(root) {
    if (!root || !document.createTreeWalker) return;
    if (root.nodeType === Node.TEXT_NODE) {
      humanizeProviderErrorTextNode(root);
      return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) humanizeProviderErrorTextNode(node);
  }

  function humanizeCommandSummaryTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const parent = node.parentElement;
    if (!parent || !parent.closest('button') || parent.closest('pre,code,textarea,input')) return;
    const value = clean(node.nodeValue);
    if (!value || value.length > 320 || !/\/data\/data\/com\.termux\/files\//u.test(value)) return;
    const latest = value.match(/^(.*?latest:\s*)(\/data\/data\/com\.termux\/files\/.*)$/iu);
    node.nodeValue = latest ? `${latest[1]}${humanizeCommand(latest[2])}` : humanizeCommand(value);
  }

  function humanizeCommandSummaries(root) {
    if (!root || !document.createTreeWalker) return;
    if (root.nodeType === Node.TEXT_NODE) {
      humanizeCommandSummaryTextNode(root);
      return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) humanizeCommandSummaryTextNode(node);
  }

  function humanizeVerboseTranscriptText(value) {
    const raw = String(value == null ? '' : value);
    const trimmed = raw.trim();
    if (!trimmed) return '';
    const functionName = raw.match(/<function=([A-Za-z_][A-Za-z0-9_.-]*)>/u);
    const commandParameter = raw.match(/<parameter=cmd>\s*([\s\S]*?)\s*<\/parameter>/u);
    if (functionName && /<\/tool_call>/u.test(trimmed)) {
      const action = commandParameter ? humanizeCommand(commandParameter[1]) : 'Executing the requested supported tool action';
      return `${action}. This historical provider response used malformed tool markup; the repaired runtime now converts that format automatically.`;
    }
    const paths = new Set(raw.match(/\/data\/data\/com\.termux\/files\/[^\s,"'}]+/gu) || []);
    const count = raw.match(/"count"\s*:\s*(\d+)/u);
    const structured = /^\s*\{/u.test(raw) || /\{\s*"count"\s*:/u.test(raw);
    const rawDominated = paths.size >= 4 || (structured && /"(?:items|verified|ok)"\s*:/u.test(raw));
    if (!rawDominated) return '';
    const summaries = [];
    if (paths.size >= 4) {
      summaries.push(`Verified ${paths.size} automation and development tools are installed and ready.`);
    }
    if (count) {
      const amount = Number(count[1]);
      summaries.push(`Gallery scan completed: found ${amount} matching image${amount === 1 ? '' : 's'} with verified metadata.`);
    } else if (structured) {
      summaries.push('The structured command result was verified successfully.');
    }
    return summaries.join(' ');
  }

  function humanizeVerboseAssistantItem(item) {
    if (!item || item.nodeType !== Node.ELEMENT_NODE || item.dataset.naHumanizedTranscript === 'true') return;
    const nodes = [];
    const walker = document.createTreeWalker(item, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || parent.closest('button,pre,code,details,textarea,input')) continue;
      if (clean(node.nodeValue)) nodes.push(node);
    }
    if (!nodes.length) return;
    const summary = humanizeVerboseTranscriptText(nodes.map((entry) => entry.nodeValue).join('\n'));
    if (!summary) return;
    nodes[0].nodeValue = summary;
    for (let index = 1; index < nodes.length; index += 1) nodes[index].nodeValue = '';
    item.dataset.naHumanizedTranscript = 'true';
    item.classList.add('na-humanized-transcript');
  }

  function humanizeVerboseAssistantTranscripts(root) {
    if (!root || root.nodeType === Node.TEXT_NODE) return;
    const items = [];
    const owner = root.closest && root.closest('.conversation-item[data-role="assistant"]');
    if (owner) items.push(owner);
    if (root.matches && root.matches('.conversation-item[data-role="assistant"]')) items.push(root);
    if (root.querySelectorAll) items.push(...root.querySelectorAll('.conversation-item[data-role="assistant"]'));
    [...new Set(items)].forEach(humanizeVerboseAssistantItem);
  }

  function humanizeVerboseFromTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const seed = String(node.nodeValue || '');
    if (!/(?:<function=|<parameter=|<\/tool_call>|\/data\/data\/com\.termux\/files\/|\{\s*"count"\s*:)/u.test(seed)) return;
    let candidate = node.parentElement;
    for (let depth = 0; candidate && depth < 10; depth += 1, candidate = candidate.parentElement) {
      if (candidate.dataset && candidate.dataset.naHumanizedTranscript === 'true') return;
      if (/^(?:BODY|HTML)$/u.test(candidate.tagName)) return;
      const combined = String(candidate.innerText || candidate.textContent || '');
      if (!combined || combined.length > 12000) continue;
      const summary = humanizeVerboseTranscriptText(combined);
      if (!summary) continue;
      const nodes = [];
      const walker = document.createTreeWalker(candidate, NodeFilter.SHOW_TEXT);
      let current;
      while ((current = walker.nextNode())) {
        const parent = current.parentElement;
        if (!parent || parent.closest('button,pre,code,details,textarea,input')) continue;
        if (clean(current.nodeValue)) nodes.push(current);
      }
      if (!nodes.length) return;
      nodes[0].nodeValue = summary;
      for (let index = 1; index < nodes.length; index += 1) nodes[index].nodeValue = '';
      candidate.dataset.naHumanizedTranscript = 'true';
      candidate.classList.add('na-humanized-transcript');
      return;
    }
  }

  function humanizeVerboseFromTree(root) {
    if (!root || !document.createTreeWalker) return;
    if (root.nodeType === Node.TEXT_NODE) {
      humanizeVerboseFromTextNode(root);
      return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let node;
    while ((node = walker.nextNode())) nodes.push(node);
    nodes.forEach(humanizeVerboseFromTextNode);
  }

  function internalCompactionText(value) {
    return /(NEMOTRON_INTERNAL_CONTEXT_CHECKPOINT|Context Checkpoint Handoff Summary|^\s*#{0,3}\s*(?:Context\s+)?(?:Checkpoint\s+)?Handoff\s+Summary|Another language model started to solve this problem)/imu.test(String(value == null ? '' : value));
  }

  function hideInternalCompactionTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE || !internalCompactionText(node.nodeValue)) return;
    const parent = node.parentElement;
    const item = parent && parent.closest('.conversation-item[data-role="assistant"]');
    if (!item) return;
    item.classList.add('na-internal-compaction');
    item.setAttribute('aria-hidden', 'true');
    state.compactionPending = true;
    if (state.active) addStep('Context checkpoint saved internally — continuing automatically');
  }

  function hideInternalCompaction(root) {
    if (!root || !document.createTreeWalker) return;
    if (root.nodeType === Node.TEXT_NODE) {
      hideInternalCompactionTextNode(root);
      return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) hideInternalCompactionTextNode(node);
  }

  function hideIncompleteCompactionTail() {
    const items = document.querySelectorAll('.conversation-item[data-role="assistant"]:not(.na-internal-compaction)');
    const item = items.length ? items[items.length - 1] : null;
    if (!item) return;
    const value = clean(item.textContent);
    if (!value || value.length > 400 || /[.!?…)\]}'"]$/u.test(value)) return;
    item.classList.add('na-internal-compaction');
    item.setAttribute('aria-hidden', 'true');
  }

  function scheduleToolbarEnsure() {
    if (toolbarFrame) return;
    toolbarFrame = window.requestAnimationFrame(() => {
      toolbarFrame = 0;
      ensureToolbar();
    });
  }

  function scheduleRecovery(threadId, reason, sourceTurnId) {
    const id = validThreadId(threadId || state.currentThreadId);
    if (!id || routeThreadId() !== id || state.currentThreadId !== id) return;
    if (state.possibleSideEffect) {
      state.active = false;
      state.phase = 'failed';
      state.hidden = false;
      state.nextBoundedAction = 'Reconcile verified state before any further action';
      recordMeaningfulUpdate('Automatic replay blocked after a possible side effect', 'failed', `unsafe-replay:${sourceTurnId || state.turnId}`);
      setToolbarStatus('Possible side effect detected · replay blocked');
      persistProgress();
      render();
      return;
    }
    if (recoveryTimers.has(id)) return;
    const attempts = recoveryAttempts.get(id) || 0;
    recoveryAttempts.set(id, attempts + 1);
    addStep(`Waiting safely after ${safeText(reason, 60)}`, `recovery-wait:${sourceTurnId || state.turnId}`);
    const delay = Math.min(60000, 3000 * (2 ** Math.min(attempts, 4)));
    setToolbarStatus(`Authoritative check ${attempts + 1} queued · reading state in ${Math.ceil(delay / 1000)}s`);
    const timer = window.setTimeout(async () => {
      recoveryTimers.delete(id);
      if (routeThreadId() !== id || state.currentThreadId !== id) return;
      try {
        const result = await rpc('thread/read', {threadId: id, includeTurns: true});
        if (routeThreadId() !== id || state.currentThreadId !== id) return;
        const thread = result && result.thread;
        const turns = Array.isArray(thread && thread.turns) ? thread.turns : [];
        const latest = turns.length ? turns[turns.length - 1] : null;
        if (threadIsActive(thread)) {
          state.active = true;
          state.phase = 'working';
          state.lastAuthoritativeReadAt = Date.now();
          setToolbarStatus('Original turn is still running · live state reattached');
          openRecoveryEventSource();
          await reconcileActiveThread();
          return;
        }
        if (sourceTurnId && latest && clean(latest.id) && clean(latest.id) !== clean(sourceTurnId)) {
          setToolbarStatus('A newer turn superseded recovery');
          return;
        }
        if (sourceTurnId) recoveringTerminalTurns.delete(clean(sourceTurnId));
        state.active = false;
        state.completed = false;
        state.phase = 'failed';
        state.expectedTurnStart = false;
        state.nextBoundedAction = 'The preserved terminal turn requires a new explicit user instruction; it will not be replayed automatically';
        recordMeaningfulUpdate('The original turn is no longer active — automatic replay remained blocked', 'failed', `terminal-reconcile:${sourceTurnId || state.turnId}`);
        persistProgress();
        render();
        setToolbarStatus('Original turn ended · no replacement turn was created');
      } catch (error) {
        setToolbarStatus(`Authoritative state read unavailable: ${clean(error.message).slice(0, 55)}`);
        if (attempts < 5) scheduleRecovery(id, reason, sourceTurnId);
        else {
          state.phase = 'retry';
          state.nextBoundedAction = 'Keep the preserved turn visible until the local runtime becomes reachable';
          persistProgress();
          render();
        }
      }
    }, delay);
    recoveryTimers.set(id, timer);
  }

  function pauseForTransientRecovery(event, threadId, reason) {
    const terminalTurnId = explicitEventTurnId(event);
    if (!terminalTurnId || recoveringTerminalTurns.has(terminalTurnId)) return;
    recoveringTerminalTurns.add(terminalTurnId);
    completeActiveStep();
    state.active = !state.possibleSideEffect;
    state.completed = false;
    state.phase = state.possibleSideEffect ? 'failed' : 'retry';
    state.hidden = false;
    const label = state.possibleSideEffect
      ? 'Provider interrupted after a possible side effect — automatic replay is blocked'
      : 'Provider connection changed — the original turn is being reconciled without replay';
    state.steps.push({label, identity: `transient:${terminalTurnId}`, status: state.possibleSideEffect ? 'failed' : 'active'});
    recordMeaningfulUpdate(label, state.possibleSideEffect ? 'failed' : 'retry', `transient:${terminalTurnId}`);
    setToolbarStatus(state.possibleSideEffect ? 'Replay blocked · verified state preserved' : 'Connection changed · reconciling the original turn');
    persistProgress();
    render();
    if (!state.possibleSideEffect) scheduleRecovery(threadId, reason, terminalTurnId);
  }

  function awaitCompactionContinuation(threadId) {
    const id = clean(threadId || state.currentThreadId);
    if (!id || routeThreadId() !== id) return;
    state.compactionPending = false;
    state.active = true;
    state.completed = false;
    state.phase = 'retry';
    hideIncompleteCompactionTail();
    addStep('Reattaching to the same mission after context compaction');
    setToolbarStatus('Context checkpoint observed · verifying the same turn');
    if (state.compactionRecoveryTimer) window.clearTimeout(state.compactionRecoveryTimer);
    state.compactionRecoveryTimer = window.setTimeout(() => {
      state.compactionRecoveryTimer = null;
      if (state.active && routeThreadId() === id && state.currentThreadId === id) {
        openRecoveryEventSource();
        void reconcileActiveThread();
      }
    }, 15000);
  }

  function handlePlan(event) {
    const params = event.params && typeof event.params === 'object' ? event.params : {};
    const plan = Array.isArray(params.plan) ? params.plan : [];
    state.plannedSteps = plan.length;
    state.completedPlanSteps = plan.filter((entry) => clean(entry && entry.status).toLowerCase() === 'completed').length;
    const active = plan.find((entry) => clean(entry && entry.status).toLowerCase().includes('progress'));
    const activeIndex = plan.indexOf(active);
    const next = plan.slice(activeIndex >= 0 ? activeIndex + 1 : 0).find((entry) => clean(entry && entry.status).toLowerCase() === 'pending');
    state.nextBoundedAction = safeText(next && next.step, 320);
    if (active && clean(active.step))
      addStep(`Working on: ${safeText(active.step, 300)}`, `plan:${safeText(active.step, 300)}`);
    else {
      persistProgress();
      render();
    }
  }

  function eventBelongsToActiveTurn(event, method) {
    const incoming = explicitEventTurnId(event);
    if (!incoming) return false;
    if (method === 'turn/started') {
      if (!state.active) return true;
      return incoming === state.turnId || state.turnId.startsWith('pending-') || state.expectedTurnStart;
    }
    return Boolean(state.active && state.turnId && (state.turnId.startsWith('pending-') || incoming === state.turnId));
  }

  function handleEvent(event, source = 'live') {
    if (!event || typeof event !== 'object') return;
    const method = clean(event.method);
    if (!method || !eventMatchesVisibleThread(event)) return;
    const incomingTurnId = explicitEventTurnId(event);
    if (incomingTurnId && completedTurns.has(incomingTurnId)) return;
    if (!eventBelongsToActiveTurn(event, method)) return;
    const fingerprinted = method === 'turn/started' || method === 'turn/plan/updated' || method === 'turn/completed'
      || method === 'turn/failed' || method === 'turn/interrupted' || method === 'turn/cancelled'
      || method === 'thread/compacted' || method === 'item/started' || method === 'item/completed';
    if (fingerprinted && rememberEventFingerprint(event, method)) return;
    markRealEvent();
    if (source === 'live') state.lastSocketEventAt = Date.now();

    if (method === 'turn/started') {
      const params = event.params && typeof event.params === 'object' ? event.params : {};
      const turn = params.turn && typeof params.turn === 'object' ? params.turn : {};
      const authoritativeObjective = objectiveFromTurn(turn);
      const authoritativeStartedAt = parseEpochMilliseconds(
          turn.startedAt || turn.started_at || turn.createdAt || turn.created_at);
      state.currentThreadId = validThreadId(params.threadId || params.thread_id || state.currentThreadId);
      const id = eventTurnId(event);
      if (state.active && state.turnId === id) {
        if (authoritativeObjective) state.objective = authoritativeObjective;
        if (authoritativeStartedAt) state.startedAtEpochMs = authoritativeStartedAt;
        persistProgress();
        render();
        notifyMissionStarted(id);
        return;
      }
      if (state.active && (state.turnId.startsWith('pending-') || state.expectedTurnStart) && id !== 'unknown-turn') {
        state.turnId = id;
        if (authoritativeObjective) state.objective = authoritativeObjective;
        if (authoritativeStartedAt) state.startedAtEpochMs = authoritativeStartedAt;
        state.expectedTurnStart = false;
        persistProgress();
        render();
        notifyMissionStarted(id);
        return;
      }
      state.expectedTurnStart = false;
      startTurn(id, authoritativeObjective || state.objective || 'Active task', authoritativeStartedAt || Date.now());
      notifyMissionStarted(id);
      return;
    }
    if (method === 'thread/compacted') {
      state.compactionPending = true;
      addStep('Context checkpoint saved internally — continuing automatically', 'context-checkpoint');
      return;
    }
    if (method === 'turn/plan/updated') {
      handlePlan(event);
      return;
    }
    if (method === 'item/started') {
      const type = itemType(event);
      const params = event.params && typeof event.params === 'object' ? event.params : {};
      const item = params.item && typeof params.item === 'object' ? params.item : {};
      const itemId = eventItemId(event);
      if (type === 'contextcompaction') {
        state.compactionPending = true;
        addStep('Saving an internal context checkpoint', `compaction:${itemId}`);
      } else if (type === 'reasoning') {
        addStep('Planning the next verified step', `reasoning:${itemId}`);
      } else if (type === 'commandexecution') {
        state.possibleSideEffect = true;
        const key = commandKey(item.command);
        state.activeCommandKey = key;
        if (itemId) state.activeCommandKeys.set(itemId, key);
        state.actionCount += 1;
        rememberTechnical(item, 'started');
        addStep(humanizeCommand(item.command), key || `command:${itemId}`);
      } else if (type === 'filechange') {
        state.possibleSideEffect = true;
        state.actionCount += 1;
        addStep('Applying the verified project changes', `filechange:${itemId}`);
      } else if (/(mcp|toolcall|collab|browser|computer)/u.test(type)) {
        state.possibleSideEffect = true;
        state.actionCount += 1;
        addStep('Executing a structured tool action', `tool:${itemId || type}`);
      } else if (type === 'agentmessage') {
        addStep('Preparing the clear final answer', `message:${itemId}`);
      }
      persistProgress();
      return;
    }
    if (method === 'item/reasoning/textDelta' || method === 'item/reasoning/summaryTextDelta') {
      if (!state.steps.some((step) => step.status === 'active')) addStep('Evaluating the latest evidence', 'reasoning-delta');
      return;
    }
    if (method === 'item/completed') {
      const params = event.params && typeof event.params === 'object' ? event.params : {};
      const item = params.item && typeof params.item === 'object' ? params.item : {};
      const type = itemType(event);
      if (type === 'contextcompaction') {
        state.compactionPending = true;
        addStep('Context checkpoint saved internally — continuing automatically', `compaction:${eventItemId(event)}`);
        return;
      }
      if (type === 'commandexecution') {
        state.possibleSideEffect = true;
        const id = eventItemId(event);
        const key = (id && state.activeCommandKeys.get(id)) || commandKey(item.command) || state.activeCommandKey;
        if (commandFailed(item)) {
          state.failedCommands += 1;
          state.phase = 'failed';
          rememberTechnical(item, 'failed');
          failActiveStep();
          if (key && key === state.consecutiveFailureKey) state.consecutiveFailureCount += 1;
          else {
            state.consecutiveFailureKey = key;
            state.consecutiveFailureCount = 1;
          }
          if (state.consecutiveFailureCount >= 3) void recoverRepeatedFailureLoop();
        } else {
          state.completedCommands += 1;
          state.phase = 'working';
          const evidence = verifiedEvidence(item);
          if (evidence) {
            state.latestVerifiedResult = evidence;
            recordMeaningfulUpdate(evidence, 'completed', `evidence:${id || key}`, evidence);
          }
          rememberTechnical(item, 'completed');
          state.consecutiveFailureKey = '';
          state.consecutiveFailureCount = 0;
          completeActiveStep();
        }
        state.activeCommandKey = '';
        if (id) state.activeCommandKeys.delete(id);
      } else {
        if (type === 'filechange' || /(mcp|toolcall|collab|browser|computer)/u.test(type)) state.possibleSideEffect = true;
        completeActiveStep();
      }
      persistProgress();
      render();
      return;
    }
    if (method === 'turn/completed') {
      const params = event.params && typeof event.params === 'object' ? event.params : {};
      const encoded = JSON.stringify(params);
      if (state.compactionPending) {
        awaitCompactionContinuation(params.threadId || params.thread_id || state.currentThreadId);
        return;
      }
      if (/"status"\s*:\s*"(?:failed|interrupted|cancelled|canceled)"/iu.test(encoded)) {
        if (transientFailure(encoded)) pauseForTransientRecovery(event, params.threadId || params.thread_id, 'temporary provider failure');
        else failTurn(eventTurnId(event));
      } else void verifyTerminalCompletion(event);
      return;
    }
    if (method === 'turn/failed' || method === 'turn/interrupted' || method === 'turn/cancelled' || method === 'error') {
      const encoded = JSON.stringify(event.params || {});
      if (transientFailure(encoded)) pauseForTransientRecovery(event, state.currentThreadId, 'temporary runtime failure');
      else failTurn(eventTurnId(event));
    }
  }

  function itemLifecycleMethod(item) {
    const status = clean(item && item.status).toLowerCase();
    if (/failed|error|cancelled|canceled|completed|complete|success|succeeded/u.test(status)) return 'item/completed';
    if (/active|inprogress|in_progress|running|pending|started/u.test(status)) return 'item/started';
    const type = clean(item && item.type).toLowerCase();
    if (type === 'agentmessage' || type === 'usermessage') return 'item/completed';
    return 'item/started';
  }

  function parseEpochMilliseconds(value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value < 100000000000 ? value * 1000 : value;
    if (typeof value === 'string' && value) {
      const parsed = Date.parse(value);
      if (Number.isFinite(parsed)) return parsed;
    }
    return 0;
  }

  function objectiveFromInput(input) {
    const entries = Array.isArray(input) ? input : [];
    const text = entries.map((entry) => {
      if (!entry || typeof entry !== 'object') return '';
      if (typeof entry.text === 'string') return entry.text;
      if (typeof entry.content === 'string') return entry.content;
      return '';
    }).filter(Boolean).join(' ');
    const marker = text.toLowerCase().lastIndexOf('my request for codex:');
    return safeText(marker >= 0 ? text.slice(marker + 'my request for codex:'.length) : text, 420);
  }

  function objectiveFromTurn(turn) {
    const items = Array.isArray(turn && turn.items) ? turn.items : [];
    for (const item of items) {
      if (clean(item && item.type).toLowerCase() !== 'usermessage') continue;
      const input = Array.isArray(item.content) ? item.content : [item];
      const objective = objectiveFromInput(input);
      if (objective) return objective;
    }
    return '';
  }

  function authoritativeRepositoryState(metadata) {
    if (!metadata || typeof metadata !== 'object') return 'unknown';
    const candidates = [metadata, metadata.repository, metadata.repo, metadata.git, metadata.gitInfo, metadata.git_info]
        .filter((entry) => entry && typeof entry === 'object');
    for (const candidate of candidates) {
      const present = [candidate.hasRepository, candidate.isRepository, candidate.present, candidate.exists]
          .find((value) => typeof value === 'boolean');
      if (present === false) return 'none';
      if (present === true) {
        const detached = [candidate.detached, candidate.isDetached, candidate.is_detached]
            .find((value) => typeof value === 'boolean');
        return detached === true ? 'detached' : 'present';
      }
    }
    return 'unknown';
  }

  function authoritativeRepositoryBranch(metadata) {
    if (!metadata || typeof metadata !== 'object') return '';
    const candidates = [metadata, metadata.repository, metadata.repo, metadata.git, metadata.gitInfo, metadata.git_info]
        .filter((entry) => entry && typeof entry === 'object');
    for (const candidate of candidates) {
      for (const key of ['branch', 'branchName', 'currentBranch', 'head', 'ref']) {
        const value = safeText(candidate[key], 160);
        if (value && value !== 'Detached HEAD') return value;
      }
    }
    return '';
  }

  function applyRepositoryMetadata(metadata) {
    const repositoryState = authoritativeRepositoryState(metadata);
    if (repositoryState === 'unknown') return;
    state.repositoryState = repositoryState;
    const repositoryBranch = repositoryState === 'present' ? authoritativeRepositoryBranch(metadata) : '';
    if (!document.querySelectorAll) return;
    document.querySelectorAll('.header-git-trigger span,.header-git-branch-meta').forEach((node) => {
      const value = clean(node && node.textContent);
      if (repositoryState === 'none' && value === 'Detached HEAD') node.textContent = 'No repository';
      else if (repositoryState === 'detached' && value === 'No repository') node.textContent = 'Detached HEAD';
      else if (repositoryState === 'present' && (value === 'Detached HEAD' || value === 'No repository'))
        node.textContent = repositoryBranch || 'Repository ready';
    });
    persistProgress();
  }

  async function reconcileActiveThread() {
    if (!state.active || !state.currentThreadId || state.reconcileInFlight) return;
    const requestedThreadId = state.currentThreadId;
    state.reconcileInFlight = true;
    state.lastReconcileAt = Date.now();
    try {
      const result = await rpc('thread/read', {threadId: requestedThreadId, includeTurns: true});
      if (routeThreadId() !== requestedThreadId || state.currentThreadId !== requestedThreadId) return;
      const thread = result && result.thread && typeof result.thread === 'object' ? result.thread : null;
      state.lastAuthoritativeReadAt = Date.now();
      applyRepositoryMetadata(thread || result);
      const turns = Array.isArray(thread && thread.turns) ? thread.turns : [];
      const latest = turns.length ? turns[turns.length - 1] : null;
      if (!latest) return;
      const latestId = clean(latest.id);
      if (latestId && state.turnId && !state.turnId.startsWith('pending-') && latestId !== state.turnId) {
        if (threadIsActive(thread) && state.expectedTurnStart)
          handleEvent({method: 'turn/started', params: {threadId: requestedThreadId, turn: latest}}, 'reconcile');
        else return;
      }
      if (latestId && (!state.turnId || state.turnId.startsWith('pending-'))) {
        state.expectedTurnStart = true;
        handleEvent({method: 'turn/started', params: {threadId: requestedThreadId, turn: latest}}, 'reconcile');
      }
      const items = Array.isArray(latest.items) ? latest.items : [];
      items.forEach((item) => {
        if (!item || typeof item !== 'object') return;
        handleEvent({
          method: itemLifecycleMethod(item),
          params: {threadId: state.currentThreadId, turnId: latestId || state.turnId, item},
        }, 'reconcile');
      });
      const status = clean(latest.status).toLowerCase();
      if (state.active && /completed|complete|failed|interrupted|cancelled|canceled/u.test(status)) {
        handleEvent({
          method: 'turn/completed',
          params: {threadId: state.currentThreadId, turn: latest, turnId: latestId || state.turnId},
        }, 'reconcile');
      }
    } catch (_) {
      if (state.active) setToolbarStatus('Live events delayed · reconciling automatically');
    } finally {
      state.reconcileInFlight = false;
    }
  }

  async function hydrateVisibleThread() {
    const threadId = routeThreadId();
    if (!threadId || state.active || state.hydrateInFlight || state.reconcileInFlight) return;
    state.hydrateInFlight = true;
    try {
      const result = await rpc('thread/read', {threadId, includeTurns: true});
      if (routeThreadId() !== threadId || (state.currentThreadId && state.currentThreadId !== threadId)) return;
      const thread = result && result.thread && typeof result.thread === 'object' ? result.thread : null;
      applyRepositoryMetadata(thread || result);
      const turns = Array.isArray(thread && thread.turns) ? thread.turns : [];
      const latest = turns.length ? turns[turns.length - 1] : null;
      if (!latest || !threadIsActive(thread)) return;
      state.currentThreadId = threadId;
      const latestId = clean(latest.id);
      if (state.turnId && state.turnId === latestId && state.startedAtEpochMs) {
        state.active = true;
        state.completed = false;
        state.hidden = false;
        state.phase = 'working';
        persistProgress();
        render();
      } else {
        const epoch = parseEpochMilliseconds(latest.startedAt || latest.started_at || latest.createdAt || latest.created_at) || Date.now();
        startTurn(latestId, objectiveFromTurn(latest) || 'Active task', epoch);
      }
      await reconcileActiveThread();
    } catch (_) {
      setToolbarStatus('Waiting for live thread state…');
    } finally {
      state.hydrateInFlight = false;
    }
  }

  function consume(value, source = 'live') {
    if (Array.isArray(value)) {
      value.forEach((entry) => consume(entry, source));
      return;
    }
    if (!value || typeof value !== 'object') return;
    if (value.method) handleEvent(value, source);
    if (value.event && value.event !== value) consume(value.event, source);
    if (value.message && typeof value.message === 'object' && value.message !== value) consume(value.message, source);
  }

  function observeSocket(socket, url) {
    socket.addEventListener('message', (message) => {
      const processText = (text) => {
        try {
          consume(JSON.parse(text));
        } catch (_) {
        }
      };
      if (typeof message.data === 'string')
        processText(message.data);
      else if (message.data && typeof message.data.text === 'function')
        message.data.text().then(processText).catch(() => {});
    });
    if (!isLiveEventSocket(url)) return;
    const generation = ++liveSocketGeneration;
    socket.addEventListener('open', () => {
      if (generation !== liveSocketGeneration) return;
      if (liveSocketWarningTimer) window.clearTimeout(liveSocketWarningTimer);
      liveSocketWarningTimer = null;
      if (/reconnect|interrupt/iu.test(state.toolbarStatus)) setToolbarStatus('Connected');
    });
    socket.addEventListener('close', () => {
      if (pageUnloading || generation !== liveSocketGeneration) return;
      setToolbarStatus('Reconnecting live updates…');
      if (state.active) {
        openRecoveryEventSource();
        void reconcileActiveThread();
      }
      scheduleLiveSocketWarning(generation);
    });
    socket.addEventListener('error', () => {
      if (!pageUnloading && generation === liveSocketGeneration) {
        setToolbarStatus('Live updates reconnecting…');
        if (state.active) void reconcileActiveThread();
      }
    });
  }

  function installSocketTap() {
    if (typeof NativeWebSocket !== 'function') return;
    function NemotronObservedWebSocket(url, protocols) {
      const socket = protocols === undefined ? new NativeWebSocket(url) : new NativeWebSocket(url, protocols);
      observeSocket(socket, url);
      return socket;
    }
    NemotronObservedWebSocket.prototype = NativeWebSocket.prototype;
    try {
      Object.setPrototypeOf(NemotronObservedWebSocket, NativeWebSocket);
    } catch (_) {
    }
    ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach((key) => {
      if (key in NativeWebSocket) NemotronObservedWebSocket[key] = NativeWebSocket[key];
    });
    window.WebSocket = NemotronObservedWebSocket;
  }

  function isLiveEventSource(url) {
    try {
      return new URL(String(url), window.location.href).pathname === '/codex-api/events';
    } catch (_) {
      return false;
    }
  }

  function observeEventSource(source, url) {
    if (!source || !isLiveEventSource(url)) return;
    const generation = ++liveEventSourceGeneration;
    source.addEventListener('open', () => {
      if (generation !== liveEventSourceGeneration) return;
      if (liveSocketWarningTimer) window.clearTimeout(liveSocketWarningTimer);
      liveSocketWarningTimer = null;
      setToolbarStatus('Connected through event-stream fallback');
    });
    source.addEventListener('message', (message) => {
      try {
        consume(JSON.parse(String(message.data)), 'eventsource');
      } catch (_) {
      }
    });
    source.addEventListener('ready', () => {
      if (generation === liveEventSourceGeneration) setToolbarStatus('Event-stream fallback ready');
    });
    source.addEventListener('error', () => {
      if (!pageUnloading && generation === liveEventSourceGeneration) {
        setToolbarStatus('Event-stream fallback reconnecting…');
      }
    });
  }

  function installEventSourceTap() {
    if (typeof NativeEventSource !== 'function') return;
    function NemotronObservedEventSource(url, options) {
      const source = options === undefined ? new NativeEventSource(url) : new NativeEventSource(url, options);
      observeEventSource(source, url);
      return source;
    }
    NemotronObservedEventSource.prototype = NativeEventSource.prototype;
    try {
      Object.setPrototypeOf(NemotronObservedEventSource, NativeEventSource);
    } catch (_) {
    }
    ['CONNECTING', 'OPEN', 'CLOSED'].forEach((key) => {
      if (key in NativeEventSource) NemotronObservedEventSource[key] = NativeEventSource[key];
    });
    window.EventSource = NemotronObservedEventSource;
  }

  function openRecoveryEventSource() {
    if (recoveryEventSource || typeof NativeEventSource !== 'function' || pageUnloading) return;
    try {
      const source = new NativeEventSource('/codex-api/events');
      recoveryEventSource = source;
      observeEventSource(source, '/codex-api/events');
      source.addEventListener('open', () => {
        if (source !== recoveryEventSource) return;
        recoveryEventSourceAttempts = 0;
        if (recoveryEventSourceTimer) window.clearTimeout(recoveryEventSourceTimer);
        recoveryEventSourceTimer = null;
      });
      source.addEventListener('error', () => {
        const closed = typeof NativeEventSource.CLOSED === 'number' ? NativeEventSource.CLOSED : 2;
        if (source === recoveryEventSource && source.readyState === closed) {
          source.close();
          recoveryEventSource = null;
          scheduleRecoveryEventSource();
        }
      });
    } catch (_) {
      recoveryEventSource = null;
      scheduleRecoveryEventSource();
    }
  }

  function scheduleRecoveryEventSource() {
    if (pageUnloading || !state.active || recoveryEventSource || recoveryEventSourceTimer) return;
    const delay = Math.min(30000, 1000 * (2 ** Math.min(recoveryEventSourceAttempts, 5)));
    recoveryEventSourceAttempts += 1;
    recoveryEventSourceTimer = window.setTimeout(() => {
      recoveryEventSourceTimer = null;
      openRecoveryEventSource();
    }, delay);
  }

  function closeRecoveryEventSource() {
    if (recoveryEventSourceTimer) window.clearTimeout(recoveryEventSourceTimer);
    recoveryEventSourceTimer = null;
    recoveryEventSourceAttempts = 0;
    if (recoveryEventSource) {
      try {
        recoveryEventSource.close();
      } catch (_) {
      }
      recoveryEventSource = null;
    }
  }

  function handleInactivity() {
    if (!state.active || !state.lastRealEventAt) return;
    const age = Date.now() - state.lastRealEventAt;
    if (age >= 30000 && state.inactivityStage < 2) {
      state.inactivityStage = 2;
      setToolbarStatus(`No new task event for ${Math.floor(age / 1000)}s · using polling and event-stream recovery`);
      recordMeaningfulUpdate('Live events paused — polling and event-stream recovery are active', 'retry', 'inactivity:event-stream');
      persistProgress();
      render();
      openRecoveryEventSource();
      void reconcileActiveThread();
    } else if (age >= 12000 && state.inactivityStage < 1) {
      state.inactivityStage = 1;
      setToolbarStatus(`No new task event for ${Math.floor(age / 1000)}s · verifying authoritative thread state`);
      recordMeaningfulUpdate('Live events paused — verifying authoritative thread state', 'retry', 'inactivity:reconcile');
      persistProgress();
      render();
      void reconcileActiveThread();
    }
    if (age >= 30000 && state.inactivityStage >= 2 && !recoveryEventSource && !recoveryEventSourceTimer) {
      openRecoveryEventSource();
    }
    const checkpointAge = Date.now() - (state.lastHumanCheckpointAt || state.startedAtEpochMs || Date.now());
    if (checkpointAge >= HUMAN_CHECKPOINT_MS && Date.now() - state.lastAuthoritativeReadAt <= 10000) {
      const activeStep = [...state.steps].reverse().find((step) => step.status === 'active');
      const label = safeText(activeStep && activeStep.label, 220) || safeText(state.objective, 220) || 'the active request';
      recordMeaningfulUpdate(`Authoritative thread read confirms work is active — current step: ${label}`, 'active', `authoritative-checkpoint:${Math.floor(Date.now() / HUMAN_CHECKPOINT_MS)}`);
      state.lastHumanCheckpointAt = Date.now();
      persistProgress();
      render();
    }
  }

  function installFetchTap() {
    window.fetch = async function nemotronObservedFetch(input, init) {
      const url = typeof input === 'string' ? input : clean(input && input.url);
      let rpcRequest = null;
      let effectiveInit = init;
      if (url.includes('/codex-api/rpc') && init && typeof init.body === 'string') {
        try {
          rpcRequest = JSON.parse(init.body);
        } catch (_) {
        }
        if (rpcRequest && rpcRequest.method === 'turn/start') {
          const requestedThreadId = validThreadId(rpcRequest.params && rpcRequest.params.threadId);
          if (requestedThreadId !== routeThreadId()) return NativeFetch(input, init);
          state.currentThreadId = requestedThreadId;
          const requestedEffort = normalizeEffort(rpcRequest.params && rpcRequest.params.effort);
          rpcRequest.params.effort = requestedEffort;
          effectiveInit = {...init, body: JSON.stringify(rpcRequest)};
          state.selectedEffort = requestedEffort;
          state.activeTurnEffort = requestedEffort;
          state.queuedEffort = '';
          const objective = objectiveFromInput(rpcRequest.params && rpcRequest.params.input);
          if (!state.active) startTurn(`pending-${Date.now()}`, objective || 'Starting the requested task', Date.now());
          recordMeaningfulUpdate(`Reasoning effort locked for this turn: ${effortLabel(requestedEffort)}`, 'completed', `effort-lock:${state.turnId || Date.now()}`);
          setToolbarStatus(`Effort locked: ${effortLabel(requestedEffort)}`);
          persistProgress();
          render();
        }
      }
      try {
        const response = await NativeFetch(input, effectiveInit);
        if (url.includes('/codex-api/') && response.status >= 500) {
          setToolbarStatus('Runtime recovering…');
        }
        return response;
      } catch (error) {
        if (url.includes('/codex-api/')) {
          setToolbarStatus('Connection interrupted · restoring verified thread state');
          if (state.active) {
            openRecoveryEventSource();
            void reconcileActiveThread();
          }
        }
        throw error;
      }
    };
  }

  function installEffortSelectionObserver() {
    if (!document || typeof document.addEventListener !== 'function') return;
    const labels = new Map([
      ['none', 'none'], ['minimal', 'minimal'], ['low', 'low'], ['medium', 'medium'],
      ['high', 'high'], ['extra high', 'xhigh'],
    ]);
    document.addEventListener('click', (event) => {
      const target = event && event.target;
      const label = clean(target && target.textContent).toLowerCase();
      const selected = labels.get(label);
      if (!selected) return;
      state.selectedEffort = selected;
      if (state.active && state.activeTurnEffort && selected !== state.activeTurnEffort) {
        state.queuedEffort = selected;
        recordMeaningfulUpdate(
            `Current turn remains locked at ${effortLabel(state.activeTurnEffort)}; ${effortLabel(selected)} is queued for the next turn`,
            'active', `effort-queued:${selected}`);
        setToolbarStatus(`Current: ${effortLabel(state.activeTurnEffort)} · next: ${effortLabel(selected)}`);
      } else {
        state.queuedEffort = '';
        setToolbarStatus(`Effort selected: ${effortLabel(selected)}`);
      }
      persistProgress();
      render();
    }, true);
  }

  const initialThreadId = validThreadId(routeThreadId());
  state.currentThreadId = initialThreadId;
  hydratePersistedProgress(initialThreadId);
  installFetchTap();
  installEffortSelectionObserver();
  installSocketTap();
  installEventSourceTap();
  if (!state.hidden) render();
  if (state.active && state.phase === 'retry') {
    openRecoveryEventSource();
    void reconcileActiveThread();
  }
  window.NemotronAutonomyProgress = Object.freeze({VERSION, humanizeCommand, humanizeVerboseTranscriptText, handleEvent, reconcileActiveThread, hydrateVisibleThread, synchronizeVisibleThread, progressSnapshot, archiveIdleThreads, deleteAllSessionsAndThreads, ensureSessionCleanupCard, addProject, removeProject, refreshWorkspace, friendlyProviderError, transientFailure, scheduleRecovery, redactSensitive, authoritativeRepositoryState});
  document.addEventListener('DOMContentLoaded', () => {
    ensureToolbar();
    ensureSessionCleanupCard();
    humanizeProviderErrors(document.body);
    humanizeCommandSummaries(document.body);
    humanizeVerboseAssistantTranscripts(document.body);
    humanizeVerboseFromTree(document.body);
    hideInternalCompaction(document.body);
    void hydrateVisibleThread();
    const observer = new MutationObserver((records) => {
      scheduleToolbarEnsure();
      ensureSessionCleanupCard();
      records.forEach((record) => {
        if (record.type === 'characterData') {
          humanizeProviderErrorTextNode(record.target);
          hideInternalCompactionTextNode(record.target);
          humanizeCommandSummaryTextNode(record.target);
          humanizeVerboseAssistantTranscripts(record.target.parentElement);
          humanizeVerboseFromTextNode(record.target);
        } else
          record.addedNodes.forEach((added) => {
            humanizeProviderErrors(added);
            hideInternalCompaction(added);
            humanizeCommandSummaries(added);
            humanizeVerboseAssistantTranscripts(added);
            humanizeVerboseFromTree(added);
          });
      });
    });
    observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    window.setInterval(() => {
      if (pageUnloading || !document.body) return;
      humanizeProviderErrors(document.body);
      humanizeCommandSummaries(document.body);
      humanizeVerboseAssistantTranscripts(document.body);
      humanizeVerboseFromTree(document.body);
    }, VISUAL_HUMANIZATION_SWEEP_MS);
  }, {once: true});
  window.addEventListener('beforeunload', () => {
    pageUnloading = true;
    persistProgress();
    closeRecoveryEventSource();
  });
  window.addEventListener('pagehide', () => {
    persistProgress();
    closeRecoveryEventSource();
  });
  document.addEventListener('visibilitychange', () => {
    persistProgress();
    if (document.hidden) return;
    pageUnloading = false;
    if (state.active) {
      openRecoveryEventSource();
      void reconcileActiveThread();
    } else {
      void hydrateVisibleThread();
    }
  });
  window.addEventListener('offline', () => setToolbarStatus('Device offline'));
  window.addEventListener('online', () => {
    setToolbarStatus('Device online · restoring current thread');
    if (state.active) void reconcileActiveThread();
    else void hydrateVisibleThread();
  });
  window.setInterval(() => {
    if (synchronizeVisibleThread()) return;
    if (!state.active || state.hidden) return;
    const elapsed = formatElapsed(Date.now() - state.startedAtEpochMs);
    setToolbarStatus(`Working · ${elapsed} · ${state.completedCommands} completed${state.failedCommands ? ` · ${state.failedCommands} failed` : ''}`);
    render();
  }, 1000);
  window.setInterval(() => {
    if (synchronizeVisibleThread()) return;
    if (state.active)
      {
        handleInactivity();
        void reconcileActiveThread();
      }
    else
      void hydrateVisibleThread();
  }, 3000);
})();
