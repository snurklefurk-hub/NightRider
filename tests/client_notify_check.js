/* Functional check for the dispatch page's unread cue.
 *
 * Runs the REAL current dispatch.html inline script inside a stubbed DOM and asserts
 * that an incoming GROUP text from a driver does NOT raise the unread cue,
 * while an incoming PRIVATE text from a driver does. Run: node tests/client_notify_check.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "..", "public", "dispatch.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function el() {
  const e = {
    textContent: "", value: "", hidden: false, className: "", disabled: false,
    innerHTML: "", scrollTop: 0, scrollHeight: 0, style: { setProperty() {} }, children: [],
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
      toggle(c, on) { const v = on === undefined ? !this._s.has(c) : !!on; v ? this._s.add(c) : this._s.delete(c); return v; }
    },
    _attrs: {},
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return this._attrs[k] === undefined ? null : this._attrs[k]; },
    addEventListener() {}, removeEventListener() {},
    appendChild(c) { this.children.push(c); return c; },
    insertBefore(c) { this.children.push(c); return c; },
    remove() {}, click() {}, focus() {},
    querySelector() { return el(); }, querySelectorAll() { return []; }
  };
  return e;
}

const nodes = new Map();
const document = {
  getElementById(id) { if (!nodes.has(id)) nodes.set(id, el()); return nodes.get(id); },
  createElement() { return el(); },
  // Dispatch settings now bind to data-export-hours controls as well.
  // This test has no such controls; return a normal empty NodeList.
  querySelectorAll() { return []; },
  addEventListener() {}, removeEventListener() {}, execCommand() { return true; },
  createTextNode(text) { return { textContent: String(text) }; },
  body: el(), documentElement: el()
};

/* ---- fetch stub ------------------------------------------------------- */
let queuedMessages = [];
let messagesCalls = 0;
function fetch(url) {
  /* The page's live-push loop calls listen() again the instant its long
     request resolves. Park that endpoint with a promise that never settles
     so the loop stays idle instead of spinning in the test process. */
  if (url.indexOf("/api/dispatch/events") === 0) { return new Promise(function () {}); }
  let data = {};
  if (url.indexOf("/api/config") === 0) { data = { statusLabels: {}, stageAction: {} }; }
  else if (url.indexOf("/api/chat/messages") === 0) { messagesCalls++; data = { messages: queuedMessages }; }
  else if (url.indexOf("/api/dispatch/drivers") === 0) { data = { drivers: [] }; }
  else if (url.indexOf("/api/dispatch/rides") === 0) { data = { rides: [] }; }
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data), blob: () => Promise.resolve({}) });
}

/* ---- interval capture ------------------------------------------------- */
const intervals = [];
const sandbox = {
  document, fetch, console,
  window: {}, URL: { createObjectURL: () => "blob:x", revokeObjectURL() {} },
  setInterval: (fn) => { intervals.push(fn); return intervals.length; },
  clearInterval: () => {}, setTimeout: (fn) => { return 0; },
  Date, Math, JSON, String, Number, Object, Array, RegExp, Error, Promise, encodeURIComponent
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(script, sandbox);

const tick = () => new Promise((r) => setImmediate(() => setImmediate(r)));
const pollChat = () => intervals[1]();           /* actual dispatch script wiring order: refreshDrivers, pollChat */
const unread = () => document.getElementById("chatCard").classList.contains("hasunread");
const cue = () => document.getElementById("chatCue").textContent;

(async function main() {
  await tick();                                   /* initial config -> refresh/drivers/pollChat */
  await pollChat(); await tick();                 /* baseline poll */
  const base = unread();
  const callsAfterBaseline = messagesCalls;

  /* 1. A driver's GROUP text must stay silent. */
  queuedMessages = [{ at: 100, role: "driver", from: "Dana", channel: "group", text: "Anyone near 5th?" }];
  await pollChat(); await tick();
  const afterGroup = unread();

  /* 2. A driver's PRIVATE text must raise the cue. */
  queuedMessages = [{ at: 200, role: "driver", from: "Dana", channel: "private", text: "Pickup is behind the diner." }];
  await pollChat(); await tick();
  const afterPrivate = unread();
  const preview = cue();

  const pass = base === false && afterGroup === false && afterPrivate === true &&
    /Pickup is behind/.test(preview) && messagesCalls > callsAfterBaseline;
  console.log(JSON.stringify({ baselineUnread: base, afterGroupUnread: afterGroup, afterPrivateUnread: afterPrivate, preview: preview }, null, 2));
  console.log(pass ? "PASS: group text silent, private text cues" : "FAIL");
  process.exit(pass ? 0 : 1);
})().catch((e) => { console.error("harness error:", e); process.exit(2); });
