"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const SOURCE = fs.readFileSync("web/nemotron-autonomy-progress.js", "utf8");
const HASH = "a".repeat(64);

function fakeResponse(payload, status) {
  const code = status === undefined ? 200 : status;
  return {
    ok: code >= 200 && code < 300,
    status: code,
    async text() { return JSON.stringify(payload); },
    async json() { return payload; },
  };
}

function createEnvironment(options) {
  const settings = options || {};
  const clock = settings.clock || { now: 1_700_000_000_000 };
  const storageValues = settings.storageValues || new Map();
  const intervals = [];
  const timeouts = new Map();
  const elements = new Map();
  const fetchCalls = [];
  const eventSources = [];
  const webSockets = [];
  const repositoryNodes = settings.repositoryNodes || [{ textContent: "Detached HEAD" }];
  const documentListeners = {};
  let nextTimerId = 1;
  let rpcHandler = settings.rpcHandler || (async () => ({}));

  class FakeDate extends Date {
    static now() { return clock.now; }
  }

  class FakeClassList {
    constructor() { this.values = new Set(); }
    add(value) { this.values.add(value); }
    remove(value) { this.values.delete(value); }
    toggle(value, enabled) {
      if (enabled === undefined ? !this.values.has(value) : enabled) this.values.add(value);
      else this.values.delete(value);
    }
  }

  function fakeElement(tagName) {
    const element = {
      nodeType: 1,
      tagName: String(tagName).toUpperCase(),
      dataset: {},
      style: {},
      parentNode: null,
      nextSibling: null,
      innerHTML: "",
      textContent: "",
      isConnected: false,
      childNodes: [],
      setAttribute() {},
      addEventListener() {},
      appendChild(child) {
        child.parentNode = element;
        child.isConnected = true;
        element.childNodes.push(child);
        return child;
      },
      insertBefore(child) {
        child.parentNode = element;
        child.isConnected = true;
        element.childNodes.push(child);
        return child;
      },
      querySelector(selector) {
        if (selector === ".na-header") return { addEventListener() {} };
        return null;
      },
      querySelectorAll() { return []; },
    };
    element.classList = new FakeClassList();
    Object.defineProperty(element, "id", {
      get() { return element._id || ""; },
      set(value) {
        element._id = value;
        if (value) elements.set(value, element);
      },
    });
    return element;
  }

  const body = fakeElement("body");
  const head = fakeElement("head");
  const document = {
    nodeType: 9,
    body,
    head,
    documentElement: {},
    hidden: false,
    getElementById(id) { return elements.get(id) || null; },
    createElement: fakeElement,
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === ".header-git-trigger span,.header-git-branch-meta") return repositoryNodes;
      return [];
    },
    createTreeWalker() { return { nextNode() { return null; } }; },
    addEventListener(name, callback) {
      if (!documentListeners[name]) documentListeners[name] = [];
      documentListeners[name].push(callback);
    },
  };

  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.listeners = {};
      webSockets.push(this);
    }
    addEventListener(name, callback) {
      if (!this.listeners[name]) this.listeners[name] = [];
      this.listeners[name].push(callback);
    }
    emit(name, payload) {
      (this.listeners[name] || []).forEach((callback) => callback(payload));
    }
  }
  FakeWebSocket.CONNECTING = 0;
  FakeWebSocket.OPEN = 1;
  FakeWebSocket.CLOSING = 2;
  FakeWebSocket.CLOSED = 3;

  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.listeners = {};
      this.readyState = 0;
      eventSources.push(this);
    }
    addEventListener(name, callback) {
      if (!this.listeners[name]) this.listeners[name] = [];
      this.listeners[name].push(callback);
    }
    emit(name, payload) {
      (this.listeners[name] || []).forEach((callback) => callback(payload));
    }
    close() { this.readyState = 2; }
  }
  FakeEventSource.CONNECTING = 0;
  FakeEventSource.OPEN = 1;
  FakeEventSource.CLOSED = 2;

  const localStorage = {
    getItem(key) { return storageValues.has(key) ? storageValues.get(key) : null; },
    setItem(key, value) {
      const serialized = String(value);
      if (settings.storageQuotaBytes && serialized.length > settings.storageQuotaBytes) {
        throw new Error("QuotaExceededError");
      }
      storageValues.set(String(key), serialized);
    },
    removeItem(key) { storageValues.delete(String(key)); },
    clear() { storageValues.clear(); },
  };

  const nativeFetch = async (input, init) => {
    const url = typeof input === "string" ? input : String(input && input.url || "");
    let rpc = null;
    if (url.includes("/codex-api/rpc") && init && typeof init.body === "string") {
      rpc = JSON.parse(init.body);
    }
    fetchCalls.push({ url, init: init || {}, rpc });
    if (rpc) {
      const result = await rpcHandler(rpc.method, rpc.params || {});
      if (result && result.__httpError) {
        return fakeResponse({ error: { message: result.message || "fixture failure" } }, result.__httpError);
      }
      return fakeResponse({ result });
    }
    return fakeResponse({});
  };

  const pathname = settings.pathname || "/thread/thread-a";
  const windowObject = {
    WebSocket: FakeWebSocket,
    EventSource: FakeEventSource,
    fetch: nativeFetch,
    location: { href: "http://127.0.0.1:5903" + pathname, pathname },
    setInterval(callback, delay) {
      intervals.push({ callback, delay });
      return intervals.length;
    },
    setTimeout(callback, delay) {
      const id = nextTimerId++;
      timeouts.set(id, { callback, delay });
      return id;
    },
    clearTimeout(id) { timeouts.delete(id); },
    addEventListener() {},
    dispatchEvent() {},
    requestAnimationFrame(callback) { callback(); return 1; },
    prompt() { return settings.promptResponse || ""; },
    confirm() { return false; },
  };
  if (settings.indexedDB) windowObject.indexedDB = settings.indexedDB;
  if (settings.throwingStorage) {
    Object.defineProperty(windowObject, "localStorage", {
      get() { throw new Error("storage disabled"); },
    });
  } else {
    windowObject.localStorage = localStorage;
  }

  const context = {
    window: windowObject,
    document,
    Date: FakeDate,
    URL,
    Set,
    Map,
    Promise,
    JSON,
    Math,
    String,
    Number,
    Boolean,
    Object,
    Array,
    RegExp,
    Node: { ELEMENT_NODE: 1, TEXT_NODE: 3, DOCUMENT_NODE: 9 },
    NodeFilter: { SHOW_TEXT: 4 },
    MutationObserver: class { observe() {} },
    CustomEvent: class {
      constructor(name, eventOptions) {
        this.name = name;
        this.detail = eventOptions && eventOptions.detail;
      }
    },
    decodeURIComponent,
    console,
  };
  vm.createContext(context);
  vm.runInContext(SOURCE, context, { filename: "nemotron-autonomy-progress.js" });

  return {
    api: windowObject.NemotronAutonomyProgress,
    window: windowObject,
    document,
    clock,
    storageValues,
    fetchCalls,
    eventSources,
    webSockets,
    repositoryNodes,
    setRpcHandler(handler) { rpcHandler = handler; },
    setRoute(nextPathname) {
      windowObject.location.pathname = nextPathname;
      windowObject.location.href = "http://127.0.0.1:5903" + nextPathname;
    },
    clickText(textContent) {
      (documentListeners.click || []).forEach((callback) => callback({ target: { textContent } }));
    },
    dispatchDocument(name) {
      (documentListeners[name] || []).forEach((callback) => callback({ type: name }));
    },
    runIntervals(delay) {
      intervals.filter((entry) => entry.delay === delay).forEach((entry) => entry.callback());
    },
    runTimeouts(maxDelay) {
      const limit = maxDelay === undefined ? Infinity : maxDelay;
      const queued = Array.from(timeouts.entries())
        .filter(([, entry]) => entry.delay <= limit)
        .sort((left, right) => left[1].delay - right[1].delay);
      queued.forEach(([id, entry]) => {
        if (!timeouts.has(id)) return;
        timeouts.delete(id);
        entry.callback();
      });
    },
  };
}

function startEvent(threadId, turnId, objective, startedAt) {
  return {
    method: "turn/started",
    params: {
      threadId,
      turn: {
        id: turnId,
        status: "inProgress",
        startedAt,
        items: [
          {
            id: "user-" + turnId,
            type: "userMessage",
            content: [{ type: "input_text", text: objective }],
          },
        ],
      },
    },
  };
}

function itemEvent(method, threadId, turnId, item) {
  return { method, params: { threadId, turnId, item } };
}

async function main() {
  const storageValues = new Map();
  const clock = { now: 1_700_000_000_000 };
  const env = createEnvironment({ storageValues, clock });
  const api = env.api;
  assert(api, "overlay API was not exported");
  assert.strictEqual(api.VERSION, "4.3.0");
  assert.strictEqual(api.transientFailure("stream disconnected before completion: error sending request"), true);

  const pendingRequest = env.window.fetch("/codex-api/rpc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      method: "turn/start",
      params: {
        threadId: "thread-a",
        effort: "Extra high",
        input: [{ type: "text", text: "Inspect the exact runtime identity and preserve every project" }],
      },
    }),
  });
  let snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.active, true);
  assert.strictEqual(snapshot.selectedEffort, "xhigh");
  assert.strictEqual(snapshot.activeTurnEffort, "xhigh");
  assert.strictEqual(env.fetchCalls[0].rpc.params.effort, "xhigh");
  assert.strictEqual(snapshot.objective, "Inspect the exact runtime identity and preserve every project");
  assert(snapshot.html.includes("Inspect the exact runtime identity"), snapshot.html);
  await pendingRequest;

  const authoritativeStartedAt = clock.now - 2_000;
  api.handleEvent(startEvent(
    "thread-a",
    "turn-a",
    "Inspect the exact runtime identity and preserve every project",
    authoritativeStartedAt,
  ));
  snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.turnId, "turn-a");
  assert.strictEqual(snapshot.startedAtEpochMs, authoritativeStartedAt);
  env.clickText("Low");
  snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.activeTurnEffort, "xhigh");
  assert.strictEqual(snapshot.queuedEffort, "low");
  assert(snapshot.html.includes("queued for the next turn"), snapshot.html);

  clock.now += 7_000;
  env.runIntervals(1000);
  snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.elapsedMs, 9_000);
  assert(snapshot.html.includes("0:09"), snapshot.html);

  const reloaded = createEnvironment({ storageValues, clock });
  let reloadedSnapshot = reloaded.api.progressSnapshot();
  assert.strictEqual(reloadedSnapshot.active, true);
  assert.strictEqual(reloadedSnapshot.turnId, "turn-a");
  assert.strictEqual(reloadedSnapshot.startedAtEpochMs, authoritativeStartedAt);
  assert.strictEqual(reloadedSnapshot.objective, "Inspect the exact runtime identity and preserve every project");
  assert(reloadedSnapshot.html.includes("0:09"), reloadedSnapshot.html);

  const liveCommand = {
    id: "cmd-live",
    type: "commandExecution",
    command: "curl http://127.0.0.1:18774/vault-health",
    status: "inProgress",
  };
  reloaded.api.handleEvent(itemEvent("item/started", "thread-a", "turn-a", liveCommand));
  reloaded.setRpcHandler(async (method) => {
    assert.strictEqual(method, "thread/read");
    return {
      thread: {
        id: "thread-a",
        status: "active",
        repository: { present: false },
        turns: [{
          id: "turn-a",
          status: "inProgress",
          startedAt: authoritativeStartedAt,
          items: [liveCommand],
        }],
      },
    };
  });
  const beforePoll = reloaded.api.progressSnapshot();
  clock.now += 5_000;
  await reloaded.api.reconcileActiveThread();
  await reloaded.api.reconcileActiveThread();
  const afterPoll = reloaded.api.progressSnapshot();
  assert.strictEqual(afterPoll.lastRealEventAt, beforePoll.lastRealEventAt, "unchanged polling fabricated activity");
  assert.strictEqual(afterPoll.actionCount, beforePoll.actionCount, "unchanged polling changed action count");
  assert.strictEqual(afterPoll.meaningfulUpdates.length, beforePoll.meaningfulUpdates.length, "unchanged polling added updates");
  assert.strictEqual(reloaded.repositoryNodes[0].textContent, "No repository");

  reloaded.repositoryNodes[0].textContent = "No repository";
  reloaded.setRpcHandler(async () => ({
    thread: {
      id: "thread-a",
      status: "active",
      repository: { present: true, detached: true },
      turns: [{ id: "turn-a", status: "inProgress", items: [liveCommand] }],
    },
  }));
  await reloaded.api.reconcileActiveThread();
  assert.strictEqual(reloaded.repositoryNodes[0].textContent, "Detached HEAD");
  assert.strictEqual(reloaded.api.authoritativeRepositoryState({ repository: { present: false } }), "none");
  assert.strictEqual(
    reloaded.api.authoritativeRepositoryState({ repository: { present: true, detached: true } }),
    "detached",
  );
  reloaded.repositoryNodes[0].textContent = "Detached HEAD";
  reloaded.setRpcHandler(async () => ({
    thread: {
      id: "thread-a",
      status: "active",
      repository: { present: true, detached: false, branch: "main" },
      turns: [{ id: "turn-a", status: "inProgress", items: [liveCommand] }],
    },
  }));
  await reloaded.api.reconcileActiveThread();
  assert.strictEqual(reloaded.repositoryNodes[0].textContent, "main");

  const scopedBefore = reloaded.api.progressSnapshot();
  reloaded.api.handleEvent({ method: "item/started", params: { turnId: "turn-a", item: { id: "unscoped", type: "reasoning" } } });
  reloaded.api.handleEvent(itemEvent(
    "item/started",
    "thread-foreign",
    "turn-a",
    { id: "foreign", type: "reasoning" },
  ));
  reloaded.api.handleEvent(itemEvent(
    "item/started",
    "thread-a",
    "turn-foreign",
    { id: "wrong-turn", type: "reasoning" },
  ));
  const scopedAfter = reloaded.api.progressSnapshot();
  assert.strictEqual(scopedAfter.lastRealEventAt, scopedBefore.lastRealEventAt);
  assert.strictEqual(scopedAfter.meaningfulUpdates.length, scopedBefore.meaningfulUpdates.length);

  for (let index = 0; index < 8; index += 1) {
    reloaded.api.handleEvent(itemEvent(
      "item/started",
      "thread-a",
      "turn-a",
      { id: "reason-" + index, type: "reasoning", status: "inProgress" },
    ));
  }
  reloadedSnapshot = reloaded.api.progressSnapshot();
  assert.strictEqual((reloadedSnapshot.html.match(/class="na-step"/g) || []).length, 5);

  const evidence = createEnvironment({ pathname: "/thread/evidence", clock: { now: clock.now } });
  evidence.api.handleEvent(startEvent("evidence", "turn-evidence", "Verify concrete readback only", clock.now));
  const invalidFixtures = [
    { id: "bare-hash", command: "echo checksum", stdout: HASH + "  /data/data/com.termux/files/home/project/dist/App.apk" },
    { id: "bare-sha-output", command: "sha256sum /data/data/com.termux/files/home/project/dist/App.apk", stdout: HASH },
    { id: "package-list", command: "pm list packages", stdout: "package:com.example.app" },
    { id: "non-apk-package-path", command: "pm path com.example.app", stdout: "package:com.example.app" },
    { id: "bare-success", command: "pm install -r app.apk", stdout: "Success" },
    { id: "echoed-marker", command: "echo VERIFY_ONLY_OK", stdout: "VERIFY_ONLY_OK" },
  ];
  invalidFixtures.forEach((fixture) => {
    const started = {
      id: fixture.id,
      type: "commandExecution",
      command: fixture.command,
      status: "inProgress",
    };
    evidence.api.handleEvent(itemEvent("item/started", "evidence", "turn-evidence", started));
    evidence.api.handleEvent(itemEvent("item/completed", "evidence", "turn-evidence", {
      ...started,
      status: "completed",
      exitCode: 0,
      stdout: fixture.stdout,
    }));
  });
  assert.strictEqual(evidence.api.progressSnapshot().latestVerifiedResult, "");

  const checksumCommand = {
    id: "real-checksum",
    type: "commandExecution",
    command: "sha256sum /data/data/com.termux/files/home/nemotron-unrestricted-app/dist/App.apk",
    status: "inProgress",
  };
  evidence.api.handleEvent(itemEvent("item/started", "evidence", "turn-evidence", checksumCommand));
  evidence.api.handleEvent(itemEvent("item/completed", "evidence", "turn-evidence", {
    ...checksumCommand,
    status: "completed",
    exitCode: 0,
    stdout: HASH + "  /data/data/com.termux/files/home/nemotron-unrestricted-app/dist/App.apk",
  }));
  assert(evidence.api.progressSnapshot().latestVerifiedResult.includes("SHA-256 read back"));

  const ordinaryPath = "/data/data/com.termux/files/home/nemotron-unrestricted-app/dist/App.apk";
  assert(evidence.api.redactSensitive(ordinaryPath).includes(ordinaryPath), "ordinary project/APK path was redacted");
  assert(evidence.api.redactSensitive(
    "/data/data/com.termux/files/home/nemotron-unrestricted-app/runtime/.codex/openrouter.env",
  ).includes("<credential-path>"));
  const bearerFixture = "Bear" + "er fixture-token";
  assert(!evidence.api.redactSensitive(bearerFixture).includes("fixture-token"));

  evidence.api.scheduleRecovery("evidence", "transient provider failure", "turn-evidence");
  const replayBlocked = evidence.api.progressSnapshot();
  assert.strictEqual(replayBlocked.active, false);
  assert.strictEqual(replayBlocked.phase, "failed");
  assert.strictEqual(replayBlocked.possibleSideEffect, true);
  assert.strictEqual(
    evidence.fetchCalls.filter((call) => call.rpc && call.rpc.method === "turn/start").length,
    0,
    "a possible side effect was replayed",
  );

  const eventClock = { now: 1_800_000_000_000 };
  const eventFallback = createEnvironment({ pathname: "/thread/events", clock: eventClock });
  eventFallback.api.handleEvent(startEvent("events", "turn-events", "Recover missing live events", eventClock.now));
  eventFallback.setRpcHandler(async () => ({
    thread: {
      id: "events",
      status: "active",
      turns: [{ id: "turn-events", status: "inProgress", items: [] }],
    },
  }));
  eventClock.now += 31_000;
  eventFallback.runIntervals(3000);
  assert(eventFallback.eventSources.length >= 1, "inactivity did not open EventSource fallback");
  assert.strictEqual(eventFallback.api.progressSnapshot().inactivityStage, 2);
  eventFallback.eventSources[0].emit("message", {
    data: JSON.stringify({
      method: "turn/plan/updated",
      params: {
        threadId: "events",
        turnId: "turn-events",
        plan: [
          { step: "Inspect state", status: "completed" },
          { step: "Resume stream", status: "in_progress" },
          { step: "Verify result", status: "pending" },
        ],
      },
    }),
  });
  assert.strictEqual(eventFallback.api.progressSnapshot().plannedSteps, 3);
  eventFallback.eventSources[0].readyState = eventFallback.window.EventSource.CLOSED;
  eventFallback.eventSources[0].emit("error", {});
  eventFallback.runTimeouts(1000);
  assert(eventFallback.eventSources.length >= 2, "closed EventSource did not reopen");

  const staleClock = { now: 1_850_000_000_000 };
  const staleStorage = new Map();
  staleStorage.set("nemotron-autonomy-progress:v1:stale", JSON.stringify({
    version: 1,
    savedAt: staleClock.now,
    threadId: "stale",
    active: true,
    completed: false,
    phase: "working",
    hidden: false,
    startedAtEpochMs: staleClock.now - 120_000,
    turnId: "turn-stale",
    objective: "Keep truthful progress visible during renderer recovery",
    lastActivityAt: staleClock.now - 90_000,
    lastRealEventAt: staleClock.now - 90_000,
  }));
  const stale = createEnvironment({
    pathname: "/thread/stale",
    clock: staleClock,
    storageValues: staleStorage,
    rpcHandler: async () => { throw new Error("runtime still reconnecting"); },
  });
  await stale.api.reconcileActiveThread();
  const staleSnapshot = stale.api.progressSnapshot();
  assert.strictEqual(staleSnapshot.active, true, "stale persisted work disappeared before authoritative reconciliation");
  assert.strictEqual(staleSnapshot.hidden, false, "stale persisted work was hidden during recovery");
  assert.strictEqual(staleSnapshot.phase, "retry");

  const disconnect = createEnvironment({ pathname: "/thread/disconnect" });
  disconnect.api.handleEvent(startEvent(
    "disconnect",
    "turn-disconnect",
    "Recover the live stream immediately",
    disconnect.clock.now,
  ));
  disconnect.setRpcHandler(async () => ({
    thread: {
      id: "disconnect",
      status: "active",
      turns: [{ id: "turn-disconnect", status: "inProgress", items: [] }],
    },
  }));
  const observedSocket = new disconnect.window.WebSocket("/codex-api/ws");
  observedSocket.emit("close", {});
  await Promise.resolve();
  assert(disconnect.eventSources.length >= 1, "stream close did not immediately open the EventSource fallback");
  assert(
    disconnect.fetchCalls.some((call) => call.rpc && call.rpc.method === "thread/read"),
    "stream close did not immediately reconcile authoritative thread state",
  );
  assert.strictEqual(
    disconnect.fetchCalls.filter((call) => call.rpc && call.rpc.method === "turn/start").length,
    0,
    "stream reconnect created a replacement turn",
  );

  const lifecycleStorage = new Map();
  const lifecycle = createEnvironment({ pathname: "/thread/lifecycle", storageValues: lifecycleStorage });
  lifecycle.api.handleEvent(startEvent(
    "lifecycle",
    "turn-lifecycle",
    "Continue one authoritative task across background transitions",
    lifecycle.clock.now,
  ));
  lifecycle.document.hidden = true;
  lifecycle.dispatchDocument("visibilitychange");
  lifecycle.document.hidden = false;
  lifecycle.setRpcHandler(async () => ({
    thread: {
      id: "lifecycle",
      status: "active",
      turns: [{ id: "turn-lifecycle", status: "inProgress", items: [] }],
    },
  }));
  lifecycle.dispatchDocument("visibilitychange");
  await Promise.resolve();
  assert.strictEqual(lifecycle.api.progressSnapshot().turnId, "turn-lifecycle");
  assert.strictEqual(
    lifecycle.fetchCalls.filter((call) => call.rpc && call.rpc.method === "turn/start").length,
    0,
    "background/foreground transition created a replacement turn",
  );

  const recreated = createEnvironment({
    pathname: "/thread/lifecycle",
    storageValues: lifecycleStorage,
    rpcHandler: async () => ({
      thread: {
        id: "lifecycle",
        status: "active",
        turns: [{ id: "turn-lifecycle", status: "inProgress", items: [] }],
      },
    }),
  });
  await recreated.api.reconcileActiveThread();
  assert.strictEqual(recreated.api.progressSnapshot().turnId, "turn-lifecycle");
  assert.strictEqual(
    recreated.fetchCalls.filter((call) => call.rpc && call.rpc.method === "turn/start").length,
    0,
    "WebView recreation created a replacement turn",
  );

  const quotaClock = { now: 1_900_000_000_000 };
  const quotaStorage = new Map();
  const quotaKey = "nemotron-autonomy-progress:v1:quota";
  quotaStorage.set(quotaKey, JSON.stringify({
    version: 1,
    savedAt: quotaClock.now,
    threadId: "quota",
    active: true,
    completed: false,
    phase: "working",
    hidden: false,
    startedAtEpochMs: quotaClock.now - 2_000,
    turnId: "turn-quota",
    objective: "Bound durable progress storage",
    eventFingerprints: Array.from(
      { length: 3_000 },
      (_, index) => "x".repeat(700) + String(index).padStart(20, "0"),
    ),
  }));
  const quota = createEnvironment({
    pathname: "/thread/quota",
    clock: quotaClock,
    storageValues: quotaStorage,
    storageQuotaBytes: 180_000,
  });
  quota.api.handleEvent(itemEvent(
    "item/started",
    "quota",
    "turn-quota",
    { id: "quota-reasoning", type: "reasoning", status: "inProgress" },
  ));
  const compactedStorage = quotaStorage.get(quotaKey);
  assert(compactedStorage.length < 180_000, "durable progress exceeded its quota-safe budget");
  const compactedPayload = JSON.parse(compactedStorage);
  assert(compactedPayload.eventFingerprints.length <= 2_048);
  assert(compactedPayload.eventFingerprints.every((entry) => /^[a-f0-9]{16}$/.test(entry)));

  const terminal = createEnvironment({ pathname: "/thread/terminal" });
  terminal.api.handleEvent(startEvent("terminal", "turn-terminal", "Finish safely", terminal.clock.now));
  terminal.api.handleEvent({
    method: "turn/completed",
    params: {
      threadId: "terminal",
      turnId: "turn-terminal",
      turn: {
        id: "turn-terminal",
        status: "completed",
        items: [{ id: "answer", type: "agentMessage", content: [{ type: "output_text", text: "Verified final answer" }] }],
      },
    },
  });
  await Promise.resolve();
  const completed = terminal.api.progressSnapshot();
  assert.strictEqual(completed.active, false);
  assert.strictEqual(completed.completed, true);
  assert.strictEqual(completed.hidden, false);
  assert(completed.html.includes("Final response delivered"), completed.html);
  terminal.api.handleEvent(itemEvent(
    "item/completed",
    "terminal",
    "turn-terminal",
    { id: "late", type: "agentMessage", status: "completed" },
  ));
  assert.strictEqual(terminal.api.progressSnapshot().active, false, "late event resurrected a completed turn");

  const silent = createEnvironment({
    pathname: "/thread/silent",
    rpcHandler: async (method) => {
      if (method === "thread/read") {
        return {
          thread: {
            id: "silent",
            status: "idle",
            turns: [{ id: "turn-silent", status: "completed", items: [] }],
          },
        };
      }
      return {};
    },
  });
  silent.api.handleEvent(startEvent("silent", "turn-silent", "Never finish with an empty answer", silent.clock.now));
  silent.api.handleEvent({
    method: "turn/completed",
    params: { threadId: "silent", turnId: "turn-silent", turn: { id: "turn-silent", status: "completed", items: [] } },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const silentSnapshot = silent.api.progressSnapshot();
  assert.strictEqual(silentSnapshot.active, false);
  assert.strictEqual(silentSnapshot.phase, "failed");
  assert.strictEqual(silentSnapshot.hidden, false);
  assert(silentSnapshot.html.includes("original turn is preserved"), silentSnapshot.html);
  const responseOnly = silent.fetchCalls.find((call) => call.rpc && call.rpc.method === "turn/start");
  assert.strictEqual(responseOnly, undefined, "empty terminal response created a replacement turn");

  const activeCleanup = createEnvironment({
    pathname: "/thread/cleanup-active",
    rpcHandler: async (method) => {
      if (method === "thread/list") return { data: [{ id: "active-thread", status: "active" }], nextCursor: null };
      return {};
    },
  });
  await assert.rejects(
    activeCleanup.api.deleteAllSessionsAndThreads(),
    /active session\(s\) must finish or be stopped/,
  );
  assert.strictEqual(
    activeCleanup.fetchCalls.filter((call) => call.rpc && call.rpc.method === "thread/delete").length,
    0,
    "cleanup deleted an active session",
  );

  const backupRecords = [];
  const fakeIndexedDB = {
    open() {
      const request = {};
      const database = {
        objectStoreNames: { contains() { return true; } },
        createObjectStore() {},
        transaction() {
          const transaction = {
            objectStore() {
              return {
                put(record) {
                  backupRecords.push(record);
                  queueMicrotask(() => transaction.oncomplete && transaction.oncomplete());
                },
              };
            },
          };
          return transaction;
        },
        close() {},
      };
      queueMicrotask(() => {
        request.result = database;
        if (request.onsuccess) request.onsuccess();
      });
      return request;
    },
  };
  const deletedFixtureIds = new Set();
  const disposableCleanup = createEnvironment({
    pathname: "/thread/disposable-cleanup",
    promptResponse: "DELETE ALL SESSIONS AND THREADS",
    indexedDB: fakeIndexedDB,
    rpcHandler: async (method, params) => {
      if (method === "thread/list") {
        const rows = params.archived ? [{ id: "fixture-b", status: "completed" }] : [{ id: "fixture-a", status: "completed" }];
        return { data: rows.filter((row) => !deletedFixtureIds.has(row.id)), nextCursor: null };
      }
      if (method === "thread/read") return { thread: { id: params.threadId, status: "completed", turns: [] } };
      if (method === "thread/delete") { deletedFixtureIds.add(params.threadId); return {}; }
      return {};
    },
  });
  const cleanupResult = await disposableCleanup.api.deleteAllSessionsAndThreads();
  assert.strictEqual(cleanupResult.deleted, 2);
  assert.strictEqual(deletedFixtureIds.size, 2);
  assert.strictEqual(backupRecords.length, 1);
  assert.strictEqual(backupRecords[0].threadCount, 2);
  assert.strictEqual(backupRecords[0].snapshots.length, 2);

  const storageDisabled = createEnvironment({ pathname: "/thread/no-storage", throwingStorage: true });
  storageDisabled.api.handleEvent(startEvent(
    "no-storage",
    "turn-no-storage",
    "Continue without DOM storage",
    storageDisabled.clock.now,
  ));
  assert.strictEqual(storageDisabled.api.progressSnapshot().active, true);

  const transcript = createEnvironment({ pathname: "/thread/transcript" });
  const rawTranscript = [
    "/data/data/com.termux/files/home/nemotron-unrestricted-app/bin/codex-search",
    "/data/data/com.termux/files/home/nemotron-unrestricted-app/bin/codex-fetch",
    "/data/data/com.termux/files/home/nemotron-unrestricted-app/bin/codex-android",
    "/data/data/com.termux/files/home/nemotron-unrestricted-app/bin/codex-gallery",
    '{"count":2,"items":[{"kind":"image"},{"kind":"image"}],"ok":true,"verified":true}',
  ].join("\n");
  const friendlyTranscript = transcript.api.humanizeVerboseTranscriptText(rawTranscript);
  assert(friendlyTranscript.includes("Verified 4 automation and development tools"), friendlyTranscript);
  assert(friendlyTranscript.includes("Gallery scan completed: found 2 matching images"), friendlyTranscript);
  assert(!friendlyTranscript.includes("/data/data/"), friendlyTranscript);
  assert(!friendlyTranscript.includes('{"count"'), friendlyTranscript);
  assert.strictEqual(
    transcript.api.humanizeVerboseTranscriptText("The verified project is ready at /data/data/com.termux/files/home/project."),
    "",
    "ordinary prose with one useful path must remain visible",
  );
  const malformedToolMarkup = [
    "<function=exec_command>",
    "<parameter=cmd>",
    "codex-gallery semantic --query woman --limit 1",
    "</parameter>",
    "</function>",
    "</tool_call>",
  ].join("\n");
  const friendlyToolMarkup = transcript.api.humanizeVerboseTranscriptText(malformedToolMarkup);
  assert(friendlyToolMarkup.includes("Scanning the Android gallery and verifying matching images"), friendlyToolMarkup);
  assert(friendlyToolMarkup.includes("repaired runtime now converts that format automatically"), friendlyToolMarkup);
  assert(!friendlyToolMarkup.includes("<function="), friendlyToolMarkup);

  console.log("PROGRESS_OVERLAY_HARNESS_OK");
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
