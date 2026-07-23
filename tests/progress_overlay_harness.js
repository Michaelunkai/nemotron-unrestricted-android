"use strict";

const assert = require("assert");
const nodeCrypto = require("crypto");
const fs = require("fs");
const vm = require("vm");

const SOURCE = fs.readFileSync("web/nemotron-autonomy-progress.js", "utf8");
const FRONTEND_SOURCE = fs.readFileSync(
  "vendor/codexapp-native-npm/node_modules/codexapp/dist/assets/index-BjdL8GKN.js",
  "utf8",
);
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
  const missionPayloads = [];
  const repositoryNodes = settings.repositoryNodes || [{ textContent: "Detached HEAD" }];
  const pendingRequests = settings.pendingRequests || [];
  const documentListeners = {};
  const windowListeners = {};
  let activeElement = null;
  const runtimeSelection = Object.assign({
    status: "ok", app: "nemotron-unrestricted", verificationStatus: "selected",
    provider: "OpenRouter", model: "nvidia/nemotron-3-ultra-550b-a55b", effort: "high",
    requestedProvider: "OpenRouter", requestedModel: "nvidia/nemotron-3-ultra-550b-a55b",
    requestedEffort: "high", requestedReasoningBudget: null,
    effectiveGateway: null, effectiveProvider: null, effectiveModel: null, effectiveEffort: null,
    identityVerified: false, effortVerified: false, verified: false, modelSubstitution: false,
  }, settings.runtimeSelection || {});
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

  function setSubtreeConnection(node, connected) {
    if (!node) return;
    node.isConnected = connected;
    if (node.id) {
      if (connected) elements.set(node.id, node);
      else elements.delete(node.id);
    }
    (node.childNodes || []).forEach((child) => setSubtreeConnection(child, connected));
  }

  function fakeElement(tagName) {
    const listeners = {};
    const attributes = {};
    const element = {
      nodeType: 1,
      tagName: String(tagName).toUpperCase(),
      dataset: {},
      style: {},
      className: "",
      parentNode: null,
      nextSibling: null,
      innerHTML: "",
      textContent: "",
      value: "",
      disabled: false,
      isConnected: false,
      childNodes: [],
      setAttribute(name, value) { attributes[String(name)] = String(value); },
      getAttribute(name) { return attributes[String(name)] ?? null; },
      addEventListener(name, callback) {
        if (!listeners[name]) listeners[name] = [];
        listeners[name].push(callback);
      },
      dispatchEvent(event) {
        const value = Object.assign({target: element, currentTarget: element}, event || {});
        (listeners[value.type] || []).forEach((callback) => callback(value));
        return true;
      },
      click() {
        if (!element.disabled) element.dispatchEvent({type: "click"});
      },
      focus() { activeElement = element; },
      remove() {
        if (element.parentNode) {
          const index = element.parentNode.childNodes.indexOf(element);
          if (index >= 0) element.parentNode.childNodes.splice(index, 1);
        }
        setSubtreeConnection(element, false);
        element.parentNode = null;
      },
      appendChild(child) {
        if (child.parentNode) {
          const index = child.parentNode.childNodes.indexOf(child);
          if (index >= 0) child.parentNode.childNodes.splice(index, 1);
        }
        child.parentNode = element;
        setSubtreeConnection(child, true);
        element.childNodes.push(child);
        return child;
      },
      insertBefore(child, reference) {
        if (child.parentNode) {
          const previousIndex = child.parentNode.childNodes.indexOf(child);
          if (previousIndex >= 0) child.parentNode.childNodes.splice(previousIndex, 1);
        }
        child.parentNode = element;
        setSubtreeConnection(child, true);
        const index = element.childNodes.indexOf(reference);
        if (index < 0) element.childNodes.push(child);
        else element.childNodes.splice(index, 0, child);
        return child;
      },
      querySelector(selector) {
        if (selector === ".na-header") return { addEventListener() {} };
        if (/^\[data-action=/.test(String(selector))) return { addEventListener() {}, disabled: false };
        const classes = String(selector).split(",").map((item) => item.trim()).filter((item) => /^\.[a-z0-9_-]+$/i.test(item));
        if (!classes.length) return null;
        return findDescendant(element, (node) => classes.some((item) => {
          const expected = item.slice(1);
          const names = String(node.className || "").split(/\s+/).filter(Boolean);
          return names.includes(expected) || (node.classList && node.classList.values.has(expected));
        }));
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
  const settingsPanel = settings.withSettingsPanel ? fakeElement("div") : null;
  if (settingsPanel) {
    settingsPanel.className = "sidebar-settings-panel";
    const telegramRow = fakeElement("div");
    telegramRow.className = "sidebar-settings-row sidebar-settings-telegram-row";
    telegramRow.textContent = "Telegram";
    const contextRow = fakeElement("div");
    contextRow.className = "sidebar-settings-row sidebar-settings-context-row";
    contextRow.textContent = "Context";
    const rateLimits = fakeElement("div");
    rateLimits.className = "sidebar-settings-rate-limits";
    const buildLabel = fakeElement("div");
    buildLabel.className = "sidebar-settings-build-label";
    buildLabel.setAttribute("aria-label", "Worktree name and version");
    buildLabel.textContent = "WT codex-web-local · v0.1.90";
    settingsPanel.appendChild(telegramRow);
    settingsPanel.appendChild(contextRow);
    settingsPanel.appendChild(rateLimits);
    settingsPanel.appendChild(buildLabel);
    body.appendChild(settingsPanel);
  }
  function findDescendant(root, predicate) {
    for (const child of root.childNodes || []) {
      if (predicate(child)) return child;
      const nested = findDescendant(child, predicate);
      if (nested) return nested;
    }
    return null;
  }
  const document = {
    nodeType: 9,
    body,
    head,
    documentElement: {},
    readyState: settings.documentReadyState || "loading",
    hidden: false,
    get activeElement() { return activeElement; },
    getElementById(id) { return elements.get(id) || null; },
    createElement: fakeElement,
    querySelector(selector) {
      if (selector === ".sidebar-settings-panel") return settingsPanel;
      if (selector === "#nemotron-session-cleanup-card button") {
        const card = elements.get("nemotron-session-cleanup-card");
        return card ? findDescendant(card, (node) => node.tagName === "BUTTON") : null;
      }
      return null;
    },
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
  Object.defineProperties(FakeWebSocket, {
    CONNECTING: { value: 0, enumerable: true, writable: false, configurable: false },
    OPEN: { value: 1, enumerable: true, writable: false, configurable: false },
    CLOSING: { value: 2, enumerable: true, writable: false, configurable: false },
    CLOSED: { value: 3, enumerable: true, writable: false, configurable: false },
  });

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
  Object.defineProperties(FakeEventSource, {
    CONNECTING: { value: 0, enumerable: true, writable: false, configurable: false },
    OPEN: { value: 1, enumerable: true, writable: false, configurable: false },
    CLOSED: { value: 2, enumerable: true, writable: false, configurable: false },
  });

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
    if (url.includes("/codex-api/custom-proxy/v1/runtime-selection")) {
      if (init && init.method === "POST" && typeof init.body === "string") {
        const selection = JSON.parse(init.body);
        if (selection.threadId) runtimeSelection.threadId = selection.threadId;
        if (selection.turnId) runtimeSelection.turnId = selection.turnId;
        if (selection.model) runtimeSelection.model = runtimeSelection.requestedModel = selection.model;
        if (selection.effort) runtimeSelection.effort = runtimeSelection.requestedEffort = selection.effort;
        runtimeSelection.verificationStatus = "selected";
      }
      return fakeResponse(runtimeSelection, settings.runtimeSelectionStatus);
    }
    if (url.includes("/codex-api/server-requests/pending")) {
      return fakeResponse({ data: pendingRequests });
    }
    if (settings.httpHandler) {
      const handled = await settings.httpHandler(url, init || {});
      if (handled !== undefined) {
        return fakeResponse(handled.payload === undefined ? handled : handled.payload, handled.status);
      }
    }
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
    addEventListener(name, callback) {
      if (!windowListeners[name]) windowListeners[name] = [];
      windowListeners[name].push(callback);
    },
    dispatchEvent(event) {
      (windowListeners[event && (event.type || event.name)] || []).forEach((callback) => callback(event));
      return true;
    },
    requestAnimationFrame(callback) { callback(); return 1; },
    crypto: {
      subtle: {
        async digest(_algorithm, value) {
          const digest = nodeCrypto.createHash("sha256").update(Buffer.from(value)).digest();
          return Uint8Array.from(digest).buffer;
        },
      },
    },
    prompt() { return settings.promptResponse || ""; },
    confirm() { return false; },
    __NEMOTRON_BRIDGE_TOKEN__: "fixture-token",
    NemotronAutonomy: {
      missionStarted() {},
      missionComplete(token, payload) {
        assert.strictEqual(token, "fixture-token");
        missionPayloads.push(JSON.parse(payload));
      },
    },
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
    URLSearchParams,
    TextEncoder,
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
    missionPayloads,
    repositoryNodes,
    settingsPanel,
    setRpcHandler(handler) { rpcHandler = handler; },
    setRoute(nextPathname) {
      windowObject.location.pathname = nextPathname;
      windowObject.location.href = "http://127.0.0.1:5903" + nextPathname;
    },
    dispatchRuntimeSelection(model, effort) {
      (windowListeners["nemotron:runtime-selection"] || []).forEach((callback) => callback({
        type: "nemotron:runtime-selection",
        detail: { model, effort },
      }));
    },
    dispatchDocument(name, values) {
      const event = Object.assign({ type: name }, values || {});
      (documentListeners[name] || []).forEach((callback) => callback(event));
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

async function runOneClickCleanup(environment) {
  const operation = environment.api.deleteAllSessionsAndThreads();
  assert.strictEqual(environment.document.getElementById("nemotron-cleanup-confirmation"), null);
  return operation;
}

async function main() {
  const storageValues = new Map();
  const clock = { now: 1_700_000_000_000 };
  const env = createEnvironment({ storageValues, clock });
  const api = env.api;
  const exactModel = "nvidia/nemotron-3-ultra-550b-a55b";
  assert(api, "overlay API was not exported");
  assert.strictEqual(api.VERSION, "4.9.2");
  assert.strictEqual(env.document.getElementById("nemotron-autonomy-tools"), null);
  assert.strictEqual(env.document.getElementById("nemotron-autonomy-progress"), null);
  assert.strictEqual(api.transientFailure("stream disconnected before completion: error sending request"), true);
  const providerErrorCases = [
    ["model_unavailable_error", "Selected model is unavailable", "exact selected model"],
    ["unsupported_effort_error", "Max effort is unsupported", "Max effort is not supported"],
    ["model_substitution_error", "Provider returned a different model", "response was blocked"],
    ["provider_substitution_error", "Provider returned an unverified route", "route did not match"],
    ["model_identity_missing_error", "Provider response omitted model identity", "did not prove which model"],
    ["invalid_request_error", "Selected model does not support tools", "tool history are preserved"],
    ["catalog_unavailable_error", "catalog cannot verify capabilities", "no unverified model"],
  ];
  for (const [type, message, expected] of providerErrorCases) {
    const friendly = api.friendlyProviderError(JSON.stringify({ error: { type, message } }));
    assert(friendly.includes(expected), `${type}: ${friendly}`);
  }
  const rejectedMax = createEnvironment({
    runtimeSelectionStatus: 422,
    runtimeSelection: { error: { type: "unsupported_effort_error", message: "Max effort is unsupported" } },
  });
  rejectedMax.dispatchRuntimeSelection(exactModel, "Max");
  await new Promise((resolve) => setImmediate(resolve));
  const rejectedSnapshot = rejectedMax.api.progressSnapshot();
  assert(rejectedSnapshot.toolbarStatus.includes("Max effort is not supported"));
  assert.strictEqual(rejectedSnapshot.active, false, "rejected selection must retain the existing session state");
  await api.refreshRuntimeIdentity(true);
  let identitySnapshot = api.progressSnapshot();
  assert.strictEqual(identitySnapshot.runtimeIdentity.requestedModel, "nvidia/nemotron-3-ultra-550b-a55b");
  assert(api.runtimeIdentityText(identitySnapshot.runtimeIdentity).includes("not yet provider-confirmed"));
  assert(api.runtimeIdentityText({
    verificationStatus: "confirmed", requestedProvider: "OpenRouter",
    requestedModel: "nvidia/nemotron-3-ultra-550b-a55b", requestedEffort: "max",
    requestedReasoningBudget: 128000, effectiveGateway: "OpenRouter",
    effectiveProvider: "Together", effectiveModel: "nvidia/nemotron-3-ultra-550b-a55b",
    effectiveEffort: "", identityVerified: true, effortVerified: false,
  }).includes("effective effort unknown"));
  const tracedIdentity = api.runtimeIdentityText({
    verificationStatus: "dispatched", requestedProvider: "OpenRouter",
    requestedModel: exactModel, requestedEffort: "max", requestedReasoningBudget: 128000,
    effectiveGateway: "", effectiveProvider: "", effectiveModel: "", effectiveEffort: "",
    identityVerified: false, effortVerified: false, requestId: "request-42", responseId: "",
    modelSubstitution: true, failureType: "model_substitution_error",
  });
  assert(tracedIdentity.includes("dispatched; awaiting provider evidence"), tracedIdentity);
  assert(tracedIdentity.includes("request request-42"), tracedIdentity);
  assert(tracedIdentity.includes("substitution detected and blocked"), tracedIdentity);
  assert(tracedIdentity.includes("failed: model_substitution_error"), tracedIdentity);

  const pendingRequest = env.window.fetch("/codex-api/rpc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      method: "turn/start",
      params: {
        threadId: "thread-a",
        model: "nvidia/nemotron-3-ultra-550b-a55b",
        effort: "Extra high",
        input: [{ type: "text", text: "Inspect the exact runtime identity and preserve every project" }],
      },
    }),
  });
  await pendingRequest;
  let snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.active, true);
  assert.strictEqual(snapshot.selectedEffort, "xhigh");
  assert.strictEqual(snapshot.activeTurnEffort, "xhigh");
  assert.strictEqual(snapshot.selectedModel, "nvidia/nemotron-3-ultra-550b-a55b");
  assert.strictEqual(env.fetchCalls.find((entry) => entry.rpc).rpc.params.effort, "xhigh");
  const dispatchSelection = env.fetchCalls.filter((entry) => entry.url.includes("runtime-selection")).at(-1);
  assert.deepStrictEqual(JSON.parse(dispatchSelection.init.body), {
    threadId: "thread-a",
    model: "nvidia/nemotron-3-ultra-550b-a55b",
    effort: "xhigh",
  });
  assert.strictEqual(snapshot.objective, "Inspect the exact runtime identity and preserve every project");
  assert.strictEqual(snapshot.html, "", "chat progress UI must remain unmounted");

  const selectionPostsBeforeNoise = env.fetchCalls.filter((entry) =>
    entry.url.includes("runtime-selection") && entry.init.method === "POST").length;
  env.dispatchDocument("click", { target: { textContent: exactModel } });
  env.dispatchRuntimeSelection("", "Max");
  await new Promise((resolve) => setImmediate(resolve));
  assert.strictEqual(
    env.fetchCalls.filter((entry) => entry.url.includes("runtime-selection") && entry.init.method === "POST").length,
    selectionPostsBeforeNoise,
    "document text or incomplete structured events must not change runtime selection",
  );

  const substituted = createEnvironment({
    runtimeSelection: { modelSubstitution: true, verificationStatus: "selected" },
  });
  await assert.rejects(
    substituted.api.updateRuntimeSelection({ model: exactModel, effort: "high" }),
    /did not match/,
  );

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
  api.handleEvent(itemEvent("item/reasoning/summaryTextDelta", "thread-a", "turn-a", {
    id: "reasoning-stream",
    type: "reasoning",
    delta: "checking the next provider continuation",
  }));
  api.handleEvent(itemEvent("item/started", "thread-a", "turn-a", {
    id: "tool-switch-boundary",
    type: "mcpToolCall",
    server: "fixture",
    tool: "read_state",
    status: "inProgress",
  }));
  snapshot = api.progressSnapshot();
  const continuityBeforeSwitch = {
    threadId: snapshot.threadId,
    turnId: snapshot.turnId,
    objective: snapshot.objective,
    active: snapshot.active,
    startedAtEpochMs: snapshot.startedAtEpochMs,
    steps: JSON.parse(JSON.stringify(snapshot.steps)),
    completedCommands: snapshot.completedCommands,
    failedCommands: snapshot.failedCommands,
  };
  const rpcCountBeforeSwitch = env.fetchCalls.filter((entry) => entry.rpc).length;
  env.dispatchRuntimeSelection(exactModel, "Low");
  await new Promise((resolve) => setImmediate(resolve));
  snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.activeTurnEffort, "low");
  assert.strictEqual(snapshot.queuedEffort, "");
  assert.strictEqual(snapshot.threadId, continuityBeforeSwitch.threadId);
  assert.strictEqual(snapshot.turnId, continuityBeforeSwitch.turnId);
  assert.strictEqual(snapshot.objective, continuityBeforeSwitch.objective);
  assert.strictEqual(snapshot.active, continuityBeforeSwitch.active);
  assert.strictEqual(snapshot.startedAtEpochMs, continuityBeforeSwitch.startedAtEpochMs);
  assert.strictEqual(JSON.stringify(snapshot.steps), JSON.stringify(continuityBeforeSwitch.steps));
  assert.strictEqual(snapshot.completedCommands, continuityBeforeSwitch.completedCommands);
  assert.strictEqual(snapshot.failedCommands, continuityBeforeSwitch.failedCommands);
  assert(snapshot.steps.some((step) => step.identity === "tool:tool-switch-boundary" && step.status === "active"));
  assert.strictEqual(
    env.fetchCalls.filter((entry) => entry.rpc).length,
    rpcCountBeforeSwitch,
    "selector changes must not interrupt, resolve approval, execute a tool, or start another turn",
  );
  assert.strictEqual(
    env.fetchCalls.some((entry) => /server-requests|approval|respond|resolve/u.test(entry.url)),
    false,
    "selector changes must not touch approval response endpoints",
  );
  assert(snapshot.meaningfulUpdates.some((entry) => entry.label.includes("next provider continuation")));
  api.handleEvent(itemEvent("item/completed", "thread-a", "turn-a", {
    id: "tool-switch-boundary",
    type: "mcpToolCall",
    server: "fixture",
    tool: "read_state",
    status: "completed",
    result: { content: "state retained" },
  }));
  snapshot = api.progressSnapshot();
  assert(snapshot.steps.some((step) => step.identity === "tool:tool-switch-boundary" && step.status === "completed"));

  env.dispatchRuntimeSelection(exactModel, "Max");
  await new Promise((resolve) => setImmediate(resolve));
  snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.activeTurnEffort, "max");
  const maxSelection = env.fetchCalls.filter((entry) => entry.url.includes("runtime-selection")).at(-1);
  assert.strictEqual(JSON.parse(maxSelection.init.body).effort, "max");

  const switchedIdentity = await api.updateRuntimeSelection({ model: exactModel, effort: "Max" });
  assert.strictEqual(switchedIdentity.model, exactModel);
  assert.strictEqual(switchedIdentity.effort, "max");
  snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.turnId, "turn-a", "runtime switching replaced the active turn");
  assert.strictEqual(snapshot.active, true, "runtime switching stopped active work");
  const switchedSelection = env.fetchCalls.filter((entry) => entry.url.includes("runtime-selection")).at(-1);
  assert.deepStrictEqual(JSON.parse(switchedSelection.init.body), {
    threadId: "thread-a",
    turnId: "turn-a",
    model: exactModel,
    effort: "max",
  });

  const race = createEnvironment();
  race.dispatchRuntimeSelection("provider/model-a", "High");
  race.dispatchRuntimeSelection(exactModel, "Max");
  await race.window.fetch("/codex-api/rpc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      method: "turn/start",
      params: {
        threadId: "thread-a",
        model: exactModel,
        effort: "Max",
        input: [{ type: "text", text: "dispatch only after coherent selection" }],
      },
    }),
  });
  const raceSelections = race.fetchCalls
    .filter((entry) => entry.url.includes("runtime-selection") && entry.init.method === "POST")
    .map((entry) => JSON.parse(entry.init.body));
  assert.deepStrictEqual(raceSelections.map(({ model, effort }) => ({ model, effort })), [
    { model: "provider/model-a", effort: "high" },
    { model: exactModel, effort: "max" },
    { model: exactModel, effort: "max" },
  ], "rapid toggles and immediate dispatch must serialize as coherent model/effort snapshots");
  const raceRpc = race.fetchCalls.find((entry) => entry.rpc && entry.rpc.method === "turn/start");
  assert.strictEqual(raceRpc.rpc.params.model, exactModel);
  assert.strictEqual(raceRpc.rpc.params.effort, "xhigh");

  clock.now += 7_000;
  env.runIntervals(1000);
  snapshot = api.progressSnapshot();
  assert.strictEqual(snapshot.elapsedMs, 9_000);
  assert.strictEqual(snapshot.html, "");

  const reloaded = createEnvironment({ storageValues, clock });
  let reloadedSnapshot = reloaded.api.progressSnapshot();
  assert.strictEqual(reloadedSnapshot.active, true);
  assert.strictEqual(reloadedSnapshot.turnId, "turn-a");
  assert.strictEqual(reloadedSnapshot.startedAtEpochMs, authoritativeStartedAt);
  assert.strictEqual(reloadedSnapshot.objective, "Inspect the exact runtime identity and preserve every project");
  assert.strictEqual(reloadedSnapshot.selectedEffort, "max", "Max effort did not survive process-style recreation");
  assert.strictEqual(reloadedSnapshot.html, "");

  const unknownEffortStorage = new Map(storageValues);
  const unknownEffortKey = "nemotron-autonomy-progress:v1:thread-a";
  const unknownEffortState = JSON.parse(unknownEffortStorage.get(unknownEffortKey));
  unknownEffortState.selectedEffort = "future-unsupported-effort";
  unknownEffortState.activeTurnEffort = "future-unsupported-effort";
  unknownEffortState.queuedEffort = "future-unsupported-effort";
  unknownEffortStorage.set(unknownEffortKey, JSON.stringify(unknownEffortState));
  const migrated = createEnvironment({ storageValues: unknownEffortStorage, clock });
  const migratedSnapshot = migrated.api.progressSnapshot();
  assert.strictEqual(migratedSnapshot.selectedEffort, "high");
  assert.strictEqual(migratedSnapshot.activeTurnEffort, "");
  assert.strictEqual(migratedSnapshot.queuedEffort, "");

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
  assert.strictEqual(reloadedSnapshot.html, "");
  assert(reloadedSnapshot.meaningfulUpdates.length >= 5);

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
  assert(completed.meaningfulUpdates.some((entry) => entry.label.includes("Final response delivered")));
  terminal.api.handleEvent(itemEvent(
    "item/completed",
    "terminal",
    "turn-terminal",
    { id: "late", type: "agentMessage", status: "completed" },
  ));
  assert.strictEqual(terminal.api.progressSnapshot().active, false, "late event resurrected a completed turn");

  const stopped = createEnvironment({ pathname: "/thread/stopped" });
  stopped.api.handleEvent(startEvent("stopped", "turn-stopped", "Stop only when explicitly requested", stopped.clock.now));
  stopped.api.handleEvent({
    method: "turn/interrupted",
    params: { threadId: "stopped", turnId: "turn-stopped", reason: "cancelled by user" },
  });
  const stoppedSnapshot = stopped.api.progressSnapshot();
  assert.strictEqual(stoppedSnapshot.active, false);
  assert.strictEqual(stoppedSnapshot.phase, "failed");
  assert.strictEqual(stopped.missionPayloads.length, 1);
  assert.strictEqual(stopped.missionPayloads[0].outcome, "stopped");
  assert.strictEqual(stopped.missionPayloads[0].turnId, "turn-stopped");

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
  assert(silentSnapshot.meaningfulUpdates.some((entry) => entry.label.includes("original turn is preserved")));
  const responseOnly = silent.fetchCalls.find((call) => call.rpc && call.rpc.method === "turn/start");
  assert.strictEqual(responseOnly, undefined, "empty terminal response created a replacement turn");

  assert(!SOURCE.includes("nemotron-cleanup-confirmation"));
  assert(SOURCE.includes("@media (prefers-color-scheme:light)"));
  const cardEnvironment = createEnvironment({
    pathname: "/thread/card-fixture",
    withSettingsPanel: true,
    rpcHandler: async (method, params) => {
      if (method === "thread/list") {
        return params.archived
          ? {data: [], nextCursor: null}
          : {data: [], nextCursor: null};
      }
      return {};
    },
  });
  cardEnvironment.api.ensureSessionCleanupCard();
  const cleanupCard = cardEnvironment.document.getElementById("nemotron-session-cleanup-card");
  const cleanupHeading = cardEnvironment.document.getElementById("nemotron-session-cleanup-title");
  const cleanupDescription = cardEnvironment.document.getElementById("nemotron-session-cleanup-description");
  const cleanupOpen = cardEnvironment.document.getElementById("nemotron-session-cleanup-open");
  assert(cleanupCard && cleanupHeading && cleanupDescription && cleanupOpen);
  assert.strictEqual(cleanupCard.getAttribute("role"), "region");
  assert.strictEqual(cleanupCard.getAttribute("aria-labelledby"), cleanupHeading.id);
  assert.strictEqual(cleanupCard.getAttribute("aria-describedby"), cleanupDescription.id);
  assert.strictEqual(cleanupHeading.textContent, "Clean sessions and threads");
  assert(cleanupDescription.textContent.includes("One click immediately backs up, deletes, and verifies"));
  assert(cleanupDescription.textContent.includes("Running work and approval-bearing sessions are preserved"));
  assert.strictEqual(cleanupOpen.textContent, "Delete all sessions and threads now");
  const settingsChildren = cardEnvironment.settingsPanel.childNodes;
  const contextRow = settingsChildren.find((node) => String(node.className).includes("sidebar-settings-context-row"));
  assert(contextRow, "real settings Context anchor is missing from the fixture");
  assert.strictEqual(settingsChildren.indexOf(cleanupCard) + 1, settingsChildren.indexOf(contextRow), "cleanup card must be directly before Context");
  cardEnvironment.api.ensureSessionCleanupCard();
  assert.strictEqual(settingsChildren.filter((node) => node.id === "nemotron-session-cleanup-card").length, 1, "cleanup card duplicated");
  cleanupOpen.click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.strictEqual(cardEnvironment.document.getElementById("nemotron-cleanup-confirmation"), null);
  assert.strictEqual(cleanupOpen.disabled, false);
  assert.strictEqual(cardEnvironment.document.getElementById("nemotron-cleanup-result").dataset.outcome, "no-op");
  cleanupCard.remove();
  cardEnvironment.api.ensureSessionCleanupCard();
  const remountedCard = cardEnvironment.document.getElementById("nemotron-session-cleanup-card");
  assert(remountedCard && remountedCard !== cleanupCard, "cleanup card did not remount after navigation replacement");
  assert.strictEqual(
    cardEnvironment.document.getElementById("nemotron-cleanup-result").dataset.outcome,
    "no-op",
    "cleanup receipt was lost when the real settings panel remounted",
  );
  assert.strictEqual(settingsChildren.indexOf(remountedCard) + 1, settingsChildren.indexOf(contextRow));
  remountedCard.remove();
  contextRow.remove();
  cardEnvironment.api.ensureSessionCleanupCard();
  const contextlessCard = cardEnvironment.document.getElementById("nemotron-session-cleanup-card");
  const rateLimits = settingsChildren.find((node) => String(node.className).includes("sidebar-settings-rate-limits"));
  assert.strictEqual(settingsChildren.indexOf(contextlessCard) + 1, settingsChildren.indexOf(rateLimits), "cleanup card must fall back before rate limits");
  contextlessCard.remove();
  rateLimits.remove();
  cardEnvironment.api.ensureSessionCleanupCard();
  const minimalCard = cardEnvironment.document.getElementById("nemotron-session-cleanup-card");
  const buildLabel = settingsChildren.find((node) => String(node.className).includes("sidebar-settings-build-label"));
  assert.strictEqual(settingsChildren.indexOf(minimalCard) + 1, settingsChildren.indexOf(buildLabel), "cleanup card must fall back before the terminal build label");

  const postLoadInjection = createEnvironment({
    pathname: "/thread/post-load-injection",
    withSettingsPanel: true,
    documentReadyState: "complete",
  });
  const postLoadCard = postLoadInjection.document.getElementById("nemotron-session-cleanup-card");
  assert(postLoadCard, "an overlay injected from Android onPageFinished must initialize after DOMContentLoaded");
  assert(
    postLoadInjection.document.getElementById("nemotron-autonomy-progress-style"),
    "cleanup UI must install its own styles even while no progress panel is rendered",
  );

  const activeCleanup = createEnvironment({
    pathname: "/thread/cleanup-active",
    rpcHandler: async (method) => {
      if (method === "thread/list") return { data: [{ id: "active-thread", status: "active" }], nextCursor: null };
      return {};
    },
  });
  const activeCleanupResult = await activeCleanup.api.deleteAllSessionsAndThreads();
  assert.strictEqual(activeCleanupResult.deleted, 0);
  assert.strictEqual(activeCleanupResult.skippedActive, 1);
  assert.strictEqual(
    activeCleanup.fetchCalls.filter((call) => call.rpc && call.rpc.method === "thread/delete").length,
    0,
    "cleanup deleted an active session",
  );
  assert.strictEqual(activeCleanup.document.getElementById("nemotron-cleanup-result").dataset.outcome, "no-op");

  const backupRecords = [];
  const backupById = new Map();
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
                  backupById.set(record.id, record);
                  queueMicrotask(() => transaction.oncomplete && transaction.oncomplete());
                },
                get(id) {
                  const getRequest = {};
                  queueMicrotask(() => {
                    getRequest.result = backupById.get(id);
                    if (getRequest.onsuccess) getRequest.onsuccess();
                  });
                  return getRequest;
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
  const corruptBackupById = new Map();
  const corruptIndexedDB = {
    open() {
      const request = {};
      const database = {
        objectStoreNames: {contains() { return true; }},
        createObjectStore() {},
        transaction() {
          const transaction = {
            objectStore() {
              return {
                put(record) {
                  corruptBackupById.set(record.id, record);
                  queueMicrotask(() => transaction.oncomplete && transaction.oncomplete());
                },
                get(id) {
                  const getRequest = {};
                  queueMicrotask(() => {
                    const stored = corruptBackupById.get(id);
                    getRequest.result = stored && {
                      ...stored,
                      integrity: {...stored.integrity, digest: "0".repeat(64)},
                    };
                    if (getRequest.onsuccess) getRequest.onsuccess();
                  });
                  return getRequest;
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
  function cleanupPageHandler(turnsByThread) {
    return async (url) => {
      if (!url.startsWith("/codex-api/thread-turn-page?")) return undefined;
      const parsed = new URL(url, "http://fixture");
      const threadId = parsed.searchParams.get("threadId");
      const allTurns = turnsByThread.get(threadId) || [];
      const beforeTurnId = parsed.searchParams.get("beforeTurnId") || "";
      const endIndex = beforeTurnId
        ? allTurns.findIndex((turn) => turn.id === beforeTurnId)
        : allTurns.length;
      if (beforeTurnId && endIndex < 0) {
        return {payload: {result: {thread: {id: threadId, status: "completed", turns: []}}, startTurnIndex: 0, hasMoreOlder: false}};
      }
      const startTurnIndex = Math.max(0, endIndex - 50);
      return {payload: {
        result: {thread: {id: threadId, status: "completed", turns: allTurns.slice(startTurnIndex, endIndex)}},
        startTurnIndex,
        hasMoreOlder: startTurnIndex > 0,
      }};
    };
  }
  const deletedFixtureIds = new Set();
  const disposableTurns = new Map([
    ["fixture-a", Array.from({length: 73}, (_, index) => ({id: `fixture-a-turn-${index}`, status: "completed", items: []}))],
    ["fixture-b", Array.from({length: 2}, (_, index) => ({id: `fixture-b-turn-${index}`, status: "completed", items: []}))],
  ]);
  const disposableCleanup = createEnvironment({
    pathname: "/thread/disposable-cleanup",
    indexedDB: fakeIndexedDB,
    httpHandler: cleanupPageHandler(disposableTurns),
    pendingRequests: [{ params: { threadId: "pending-thread" } }],
    rpcHandler: async (method, params) => {
      if (method === "thread/list") {
        const rows = params.archived
          ? [{ id: "fixture-b", status: "completed", archived: true }]
          : [
              { id: "fixture-a", status: "completed" },
              { id: "active-thread", status: "active" },
              { id: "pending-thread", status: "completed" },
            ];
        return { data: rows.filter((row) => !deletedFixtureIds.has(row.id)), nextCursor: null };
      }
      if (method === "thread/read") return { thread: { id: params.threadId, status: "completed", turns: [] } };
      if (method === "thread/delete") { deletedFixtureIds.add(params.threadId); return {}; }
      return {};
    },
  });
  const convergenceEvents = [];
  disposableCleanup.window.addEventListener("nemotron-autonomy:sessions-deleted", (event) => {
    convergenceEvents.push(event.detail);
  });
  const cleanupResult = await runOneClickCleanup(disposableCleanup);
  assert.strictEqual(cleanupResult.deleted, 2);
  assert.strictEqual(cleanupResult.skippedActive, 1);
  assert.strictEqual(cleanupResult.skippedPending, 1);
  assert.strictEqual(deletedFixtureIds.size, 2);
  assert(!deletedFixtureIds.has("active-thread"));
  assert(!deletedFixtureIds.has("pending-thread"));
  assert.strictEqual(backupRecords.length, 1);
  assert.strictEqual(backupRecords[0].threadCount, 2);
  assert.strictEqual(backupRecords[0].turnCount, 75);
  assert.strictEqual(backupRecords[0].snapshots.length, 2);
  assert.deepStrictEqual(backupRecords[0].threadIds.sort(), ["fixture-a", "fixture-b"]);
  assert.strictEqual(backupRecords[0].snapshots[0].thread.turns.length, 73);
  assert.strictEqual(backupRecords[0].snapshots[0].backupVerification.pageCount, 2);
  assert.strictEqual(backupRecords[0].snapshots[0].backupVerification.complete, true);
  assert.match(backupRecords[0].integrity.digest, /^[0-9a-f]{64}$/u);
  assert.deepStrictEqual(
    Array.from(convergenceEvents[0].deletedThreadIds).sort(),
    ["fixture-a", "fixture-b"],
    "deleted IDs were not sent to the real sidebar store",
  );
  assert.deepStrictEqual(
    Array.from(convergenceEvents[0].protectedThreadIds).sort(),
    ["active-thread", "pending-thread"],
    "protected IDs were omitted from the sidebar convergence receipt",
  );
  assert.strictEqual(convergenceEvents[0].clearAllThreads, false);
  assert.strictEqual(
    disposableCleanup.fetchCalls.filter((call) => call.rpc && call.rpc.method === "thread/read").length,
    0,
    "cleanup backup must not use the 10-turn-truncated RPC path",
  );
  const successResult = disposableCleanup.document.getElementById("nemotron-cleanup-result");
  assert.strictEqual(successResult.dataset.outcome, "success");
  assert.strictEqual(successResult.getAttribute("role"), "status");
  const inspectSuccess = disposableCleanup.document.getElementById("nemotron-cleanup-inspect-backup");
  inspectSuccess.click();
  await new Promise((resolve) => setImmediate(resolve));
  const inspectedBackup = disposableCleanup.document.getElementById("nemotron-cleanup-backup-inspector");
  assert(inspectedBackup.textContent.includes('"turnCount": 75'));
  assert(inspectedBackup.textContent.includes('"algorithm": "SHA-256"'));
  deletedFixtureIds.add("active-thread");
  deletedFixtureIds.add("pending-thread");
  const repeatedCleanup = await runOneClickCleanup(disposableCleanup);
  assert.strictEqual(repeatedCleanup.deleted, 0);
  assert.strictEqual(convergenceEvents[1].clearAllThreads, true, "empty authoritative inventory did not clear stale sidebar rows");
  assert.strictEqual(
    disposableCleanup.document.getElementById("nemotron-cleanup-result").dataset.outcome,
    "success",
    "a repeated empty inventory overwrote the completed deletion receipt with a misleading zero result",
  );

  let corruptDeleteCount = 0;
  const corruptCleanup = createEnvironment({
    pathname: "/thread/corrupt-cleanup",
    indexedDB: corruptIndexedDB,
    httpHandler: cleanupPageHandler(new Map([
      ["corrupt-inactive", [{id: "corrupt-turn", status: "completed", items: []}]],
    ])),
    rpcHandler: async (method, params) => {
      if (method === "thread/list") {
        return params.archived
          ? {data: [], nextCursor: null}
          : {data: [{id: "corrupt-inactive", status: "completed"}], nextCursor: null};
      }
      if (method === "thread/delete") { corruptDeleteCount += 1; return {}; }
      return {};
    },
  });
  await assert.rejects(
    runOneClickCleanup(corruptCleanup),
    /read-back metadata verification failed/,
  );
  assert.strictEqual(corruptDeleteCount, 0, "cleanup deleted before backup integrity verification");
  assert.strictEqual(
    corruptCleanup.document.getElementById("nemotron-cleanup-result").dataset.outcome,
    "verification-failure",
  );

  const partiallyDeletedIds = new Set();
  const failingCleanup = createEnvironment({
    pathname: "/thread/failing-cleanup",
    indexedDB: fakeIndexedDB,
    httpHandler: cleanupPageHandler(new Map([
      ["inactive-first", [{id: "inactive-first-turn", status: "completed", items: []}]],
      ["inactive-fails", [{id: "inactive-fails-turn", status: "completed", items: []}]],
    ])),
    pendingRequests: [{ params: { threadId: "pending-safe" } }],
    rpcHandler: async (method, params) => {
      if (method === "thread/list") {
        if (params.archived) return { data: [], nextCursor: null };
        return {
          data: [
            { id: "inactive-first", status: "completed" },
            { id: "inactive-fails", status: "completed" },
            { id: "active-safe", status: "active" },
            { id: "pending-safe", status: "completed" },
          ],
          nextCursor: null,
        };
      }
      if (method === "thread/read") return { thread: { id: params.threadId, status: "completed", turns: [] } };
      if (method === "thread/delete") {
        if (params.threadId === "inactive-fails") throw new Error("fixture deletion failure");
        partiallyDeletedIds.add(params.threadId);
        return {};
      }
      return {};
    },
  });
  await assert.rejects(
    runOneClickCleanup(failingCleanup),
    /fixture deletion failure/,
  );
  assert.deepStrictEqual([...partiallyDeletedIds], ["inactive-first"]);
  assert(!partiallyDeletedIds.has("active-safe"));
  assert(!partiallyDeletedIds.has("pending-safe"));
  assert.strictEqual(backupRecords.length, 2, "failure path did not retain its pre-delete backup");
  assert.strictEqual(backupRecords[1].recoveryState, "retained-before-delete");
  assert.deepStrictEqual(backupRecords[1].threadIds, ["inactive-first", "inactive-fails"]);
  const partialResult = failingCleanup.document.getElementById("nemotron-cleanup-result");
  assert.strictEqual(partialResult.dataset.outcome, "partial-failure");
  assert(partialResult.textContent === "" || partialResult.childNodes.some((node) => /1 of 2/u.test(node.textContent)));
  assert(failingCleanup.document.getElementById("nemotron-cleanup-inspect-backup"));

  let raceInventoryReads = 0;
  const raceDeletedIds = new Set();
  const cleanupRace = createEnvironment({
    pathname: "/thread/cleanup-race",
    indexedDB: fakeIndexedDB,
    httpHandler: cleanupPageHandler(new Map([
      ["becomes-active", [{id: "becomes-active-turn", status: "completed", items: []}]],
    ])),
    rpcHandler: async (method, params) => {
      if (method === "thread/list") {
        raceInventoryReads += 1;
        if (params.archived) return {data: [], nextCursor: null};
        return {
          data: [{
            id: "becomes-active",
            status: raceInventoryReads >= 3 ? "active" : "completed",
          }],
          nextCursor: null,
        };
      }
      if (method === "thread/delete") {
        raceDeletedIds.add(params.threadId);
        return {};
      }
      return {};
    },
  });
  const cleanupRaceResult = await runOneClickCleanup(cleanupRace);
  assert.strictEqual(cleanupRaceResult.deleted, 0);
  assert.strictEqual(cleanupRaceResult.skippedActive, 1);
  assert.strictEqual(raceDeletedIds.size, 0, "thread that became active after inventory was deleted");
  assert.strictEqual(backupRecords.length, 3, "TOCTOU-protected thread backup was not retained");
  assert.deepStrictEqual(backupRecords[2].threadIds, ["becomes-active"]);

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
  assert.strictEqual(
    transcript.api.humanizeCommand("codex-exec --script workspace/task.sh"),
    "Checking the prepared task script for syntax, then running it",
  );
  assert.strictEqual(
    transcript.api.humanizeCommand("codex-win '{\"action\":\"diagnostics\"}'"),
    "Connecting to the paired PC and verifying the exact Windows result",
  );
  assert.strictEqual(
    transcript.api.humanizeCommand("codex-doctor android --json"),
    "Checking environment, Android, storage, permissions, and tool readiness without changing them",
  );
  assert.strictEqual(
    transcript.api.humanizeCommand("codex-schedule run-now backup"),
    "Checking or updating the durable Android task schedule",
  );
  assert.strictEqual(
    transcript.api.humanizeCommand("codex-pc-route select"),
    "Checking the paired PC identity, route, health, and fresh capability evidence",
  );
  const completedReceiptItem = {
    aggregatedOutput: JSON.stringify({
      action: "Verify a structured example",
      message: "The example completed successfully.",
      ok: true,
      taskVerified: true,
      verification: "The structured output receipt matched every required field.",
    }),
  };
  assert.strictEqual(
    transcript.api.structuredReceipt(completedReceiptItem).taskVerified,
    true,
  );
  assert(
    transcript.api.resultNarration(completedReceiptItem, false).includes(
      "The structured output receipt matched every required field.",
    ),
  );
  const quoteFailureNarration = transcript.api.resultNarration({
    command: "/data/data/com.termux/files/usr/bin/bash -c \"echo '\"",
    aggregatedOutput: "unexpected EOF while looking for matching `''",
  }, true);
  assert(quoteFailureNarration.includes("unmatched quote"), quoteFailureNarration);
  assert(quoteFailureNarration.includes("syntax-checked script"), quoteFailureNarration);
  const windowsFailureNarration = transcript.api.resultNarration({
    aggregatedOutput: JSON.stringify({
      error: "windows_gateway_unverified",
      message: "The Windows action returned an incomplete verification receipt, so no successful result was claimed.",
      nextAction: "Run bounded status and diagnostics.",
      ok: false,
      verified: false,
    }),
  }, true);
  assert(windowsFailureNarration.includes("incomplete verification receipt"), windowsFailureNarration);
  assert(windowsFailureNarration.includes("Next: Run bounded status and diagnostics."), windowsFailureNarration);

  const convergenceStart = FRONTEND_SOURCE.indexOf("function nemotronCleanupConverge");
  const convergenceEnd = FRONTEND_SOURCE.indexOf("function Xd(){", convergenceStart);
  assert(convergenceStart >= 0 && convergenceEnd > convergenceStart, "real frontend cleanup convergence handler is absent");
  const convergenceSource = FRONTEND_SOURCE.slice(convergenceStart, convergenceEnd);
  const cachedThreadIds = ["deleted-thread", "protected-thread"];
  const frontendContext = {
    Array,
    Ht: [],
    Ur() { return cachedThreadIds.map((id) => ({id})); },
    fo(id) {
      const index = cachedThreadIds.indexOf(id);
      if (index >= 0) cachedThreadIds.splice(index, 1);
    },
    async kr() {
      cachedThreadIds.push("deleted-thread");
    },
  };
  vm.createContext(frontendContext);
  vm.runInContext(`"use strict";${convergenceSource};this.runCleanupConvergence=nemotronCleanupConverge`, frontendContext);
  frontendContext.runCleanupConvergence({
    detail: {deletedThreadIds: ["deleted-thread"], protectedThreadIds: ["protected-thread"], clearAllThreads: false},
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepStrictEqual(cachedThreadIds, ["protected-thread"], "deleted sidebar row returned after a stale in-flight refetch");
  cachedThreadIds.push("stale-a", "stale-b");
  frontendContext.runCleanupConvergence({
    detail: {deletedThreadIds: [], protectedThreadIds: [], clearAllThreads: true},
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepStrictEqual(cachedThreadIds, [], "authoritatively empty inventory did not clear every stale Pinned/Chats row");

  console.log("PROGRESS_OVERLAY_HARNESS_OK");
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
