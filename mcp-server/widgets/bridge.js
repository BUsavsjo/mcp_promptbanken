/* Promptbanken MCP Apps-brygga (MCP Apps 2026-01-26).
 * Standardbryggan över postMessage först; window.openai bara som tillägg när
 * värden är ChatGPT och standardvägen saknas. Sätter aldrig HTML från data. */
(function () {
  "use strict";
  var PROTOCOL_VERSION = "2026-01-26";
  var APP_INFO = { name: "promptbanken-widgets", version: "1.3.0" };
  var FALLBACK_MS = 2000;
  var INIT_TIMEOUT_MS = 60000;
  var REQUEST_TIMEOUT_MS = 10000;
  var pending = {};
  var nextId = 1;
  var handlers = [];
  var hostContext = {};
  var connected = false;
  var received = false;
  var sizeScheduled = false;
  var lastSize = { width: 0, height: 0 };
  var lastIntrinsicHeight = 0;

  function post(message) { window.parent.postMessage(message, "*"); }

  /* onLate: ett svar som kommer efter timeout tas ändå emot (långsamma värdar). */
  function request(method, params, timeoutMs, onLate) {
    var id = nextId++;
    post({ jsonrpc: "2.0", id: id, method: method, params: params || {} });
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      setTimeout(function () {
        var entry = pending[id];
        if (!entry || entry.late) return;
        if (onLate) pending[id] = { late: true, resolve: onLate, reject: function () {} };
        else delete pending[id];
        reject(new Error("timeout: " + method));
      }, timeoutMs || REQUEST_TIMEOUT_MS);
    });
  }

  function notify(method, params) { post({ jsonrpc: "2.0", method: method, params: params || {} }); }

  function openai() { return window.openai || null; }

  function applyContext(context) {
    if (!context) return;
    hostContext = Object.assign({}, hostContext, context);
    var root = document.documentElement;
    if (context.theme === "light" || context.theme === "dark") root.setAttribute("data-theme", context.theme);
    var variables = context.styles && context.styles.variables;
    if (variables) {
      Object.keys(variables).forEach(function (name) {
        if (name.indexOf("--") === 0) root.style.setProperty(name, String(variables[name]));
      });
    }
  }

  /* Samma mätning som SDK:ns autoResize: bredd från innerWidth (beror inte på
   * scrollbar, ingen återkopplingsloop), höjd som max-content, rAF-batchat och
   * bara skickat när de avrundade värdena ändrats. setTimeout är reserv om
   * värden stryper rAF i en dold iframe. */
  function measureAndSend() {
    if (!sizeScheduled) return;
    sizeScheduled = false;
    var html = document.documentElement;
    var originalHeight = html.style.height;
    html.style.height = "max-content";
    var height = Math.ceil(html.getBoundingClientRect().height);
    html.style.height = originalHeight;
    var width = Math.ceil(window.innerWidth);
    if (connected) {
      if (width !== lastSize.width || height !== lastSize.height) {
        lastSize = { width: width, height: height };
        notify("ui/notifications/size-changed", { width: width, height: height });
      }
      return;
    }
    var host = openai();
    if (host && typeof host.notifyIntrinsicHeight === "function" && height !== lastIntrinsicHeight) {
      lastIntrinsicHeight = height;
      host.notifyIntrinsicHeight(height);
    }
  }

  function scheduleSize() {
    if (sizeScheduled) return;
    sizeScheduled = true;
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(measureAndSend);
    setTimeout(measureAndSend, 100);
  }

  function observeSize() {
    if (typeof ResizeObserver !== "function") return;
    var observer = new ResizeObserver(scheduleSize);
    observer.observe(document.documentElement);
    if (document.body) observer.observe(document.body);
  }

  function onInitialized(result) {
    if (connected) return;
    connected = true;
    applyContext(result && result.hostContext);
    notify("ui/notifications/initialized");
    scheduleSize();
  }

  function deliver(data) {
    received = true;
    handlers.forEach(function (handler) { handler(data); });
    scheduleSize();
  }

  function fromOpenAi() {
    var host = openai();
    if (host && host.toolOutput) { deliver(host.toolOutput); return true; }
    return false;
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var message = event.data;
    if (!message || message.jsonrpc !== "2.0") return;
    if (message.id !== undefined && !message.method && pending[message.id]) {
      var entry = pending[message.id];
      delete pending[message.id];
      if (message.error) entry.reject(new Error(message.error.message || "error"));
      else entry.resolve(message.result);
      return;
    }
    if (message.id !== undefined && message.method) {
      if (message.method === "ping" || message.method === "ui/resource-teardown") {
        post({ jsonrpc: "2.0", id: message.id, result: {} });
      } else {
        post({ jsonrpc: "2.0", id: message.id, error: { code: -32601, message: "Method not found" } });
      }
      return;
    }
    var params = message.params || {};
    if (message.method === "ui/notifications/tool-result" && params.structuredContent) deliver(params.structuredContent);
    if (message.method === "ui/notifications/host-context-changed") applyContext(params);
  });

  var NAMED_COLORS = {
    blue: "#2563eb", indigo: "#4f46e5", violet: "#7c3aed", purple: "#9333ea",
    pink: "#db2777", red: "#dc2626", orange: "#ea580c", amber: "#d97706",
    yellow: "#ca8a04", lime: "#65a30d", green: "#16a34a", emerald: "#059669",
    teal: "#0d9488", cyan: "#0891b2", sky: "#0284c7", slate: "#475569", gray: "#6b7280"
  };
  var NAMED_ICONS = {
    message: "💬", image: "🖼️", library: "📚", sparkles: "✨", chart: "📊",
    calendar: "📅", check: "✅", compass: "🧭", document: "📄", lightbulb: "💡",
    people: "👥", shield: "🛡️", target: "🎯", workflow: "➜"
  };

  var PB = {
    onData: function (handler) { handlers.push(handler); },
    start: function (onNothing) {
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        document.documentElement.setAttribute("data-theme", "dark");
      }
      observeSize();
      request("ui/initialize", {
        protocolVersion: PROTOCOL_VERSION,
        appInfo: APP_INFO,
        appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] }
      }, INIT_TIMEOUT_MS, onInitialized).then(onInitialized).catch(function () {});
      window.addEventListener("openai:set_globals", function () { if (!received) fromOpenAi(); });
      setTimeout(function () {
        if (received || connected) return;
        if (!fromOpenAi() && onNothing) { onNothing(); scheduleSize(); }
      }, FALLBACK_MS);
    },
    sendMessage: function (text) {
      if (connected) return request("ui/message", { role: "user", content: [{ type: "text", text: text }] });
      var host = openai();
      if (host && host.sendFollowUpMessage) return host.sendFollowUpMessage({ prompt: text });
      return Promise.reject(new Error("no host"));
    },
    canFullscreen: function () {
      var modes = hostContext.availableDisplayModes;
      if (Array.isArray(modes)) return modes.indexOf("fullscreen") !== -1;
      var host = openai();
      return Boolean(host && host.requestDisplayMode);
    },
    requestFullscreen: function () {
      if (connected && Array.isArray(hostContext.availableDisplayModes)) {
        return request("ui/request-display-mode", { mode: "fullscreen" });
      }
      var host = openai();
      if (host && host.requestDisplayMode) return host.requestDisplayMode({ mode: "fullscreen" });
      return Promise.reject(new Error("no host"));
    },
    getState: function () { var host = openai(); return (host && host.widgetState) || null; },
    setState: function (state) { var host = openai(); if (host && host.setWidgetState) host.setWidgetState(state); },
    el: function (tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined && text !== null) node.textContent = String(text);
      return node;
    },
    notice: function (container, text) { container.replaceChildren(PB.el("p", "pb-notice", text)); },
    areaColor: function (slug) {
      var hash = 0;
      String(slug || "").split("").forEach(function (c) { hash = (hash * 31 + c.charCodeAt(0)) >>> 0; });
      return "hsl(" + (hash % 360) + " 55% 50%)";
    },
    safeColor: function (value, slug) {
      if (typeof value === "string" && /^#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(value)) return value;
      if (typeof value === "string" && Object.prototype.hasOwnProperty.call(NAMED_COLORS, value.toLowerCase())) {
        return NAMED_COLORS[value.toLowerCase()];
      }
      return PB.areaColor(slug);
    },
    typeLabel: function (type) {
      return type === "workflow" ? "Arbetsflöde" : type === "collection" ? "Samling" : "Paket";
    },
    typeIcon: function (iconKey, type) {
      if (typeof iconKey === "string" && Object.prototype.hasOwnProperty.call(NAMED_ICONS, iconKey.toLowerCase())) {
        return NAMED_ICONS[iconKey.toLowerCase()];
      }
      if (typeof iconKey === "string" && iconKey.length > 0 && iconKey.length <= 4) return iconKey;
      return type === "workflow" ? "➜" : "▦";
    }
  };
  window.PB = PB;
})();
