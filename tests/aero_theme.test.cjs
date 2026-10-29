const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const read = p => fs.readFileSync(path.join(root, p), "utf8");

function bootstrap(initial) {
  const store = new Map(initial ? [["nightrider.ui-theme.v1", initial]] : []);
  const listeners = {}, events = [];
  const documentElement = { dataset: {}, style: {} };
  const host = { children: [], appendChild(item) { this.children.push(item); } };
  const document = {
    readyState: "complete", documentElement,
    querySelector: selector => selector === "header nav" ? host : null,
    querySelectorAll: () => host.children.flatMap(group => group.children || []),
    createElement() {
      const attrs = {};
      return { className: "", type: "", dataset: {}, children: [],
        appendChild(child) { this.children.push(child); },
        addEventListener(name, cb) { this[name] = cb; },
        setAttribute(name, value) { attrs[name] = value; },
        getAttribute(name) { return attrs[name]; } };
    }
  };
  class CustomEvent {
    constructor(type, opts) { this.type = type; this.detail = opts.detail; }
  }
  const window = {
    document, localStorage: {
      getItem(key) { return store.get(key) || null; },
      setItem(key, value) { store.set(key, value); }
    },
    addEventListener(name, cb) { listeners[name] = cb; },
    dispatchEvent(ev) { events.push(ev); }
  };
  vm.runInNewContext(read("public/aero-theme.js"), { window, CustomEvent, console });
  return { window, store, host, documentElement, listeners, events };
}

test("DARK is the default; the LIGHT choice applies Aero and persists", () => {
  const h = bootstrap();
  assert.equal(h.window.NightRiderUiTheme.current(), "dark");
  assert.equal(h.documentElement.dataset.nrUi, "classic");
  assert.equal(h.host.children.length, 1);
  const buttons = h.host.children[0].children;
  assert.deepEqual(buttons.map(x => x.textContent), ["LIGHT", "DARK"]);
  assert.equal(buttons[1].getAttribute("aria-pressed"), "true");
  buttons[0].click();
  assert.equal(h.window.NightRiderUiTheme.current(), "light");
  assert.equal(h.documentElement.dataset.nrUi, "aero");
  assert.equal(h.store.get("nightrider.ui-theme.v1"), "aero");
  assert.equal(buttons[0].getAttribute("aria-pressed"), "true");
  assert.equal(buttons[1].getAttribute("aria-pressed"), "false");
  assert.equal(h.events.at(-1).detail.mode, "light");
  assert.equal(h.window.NightRiderUiTheme.set("wrong"), false);
  assert.ok(!h.store.has("nightrider.map-mode.v1"));
});

test("previous Aero preference survives upgrade and DARK restores Classic", () => {
  const h = bootstrap("aero");
  assert.equal(h.window.NightRiderUiTheme.current(), "light");
  assert.equal(h.documentElement.dataset.nrUi, "aero");
  h.host.children[0].children[1].click();
  assert.equal(h.store.get("nightrider.ui-theme.v1"), "classic");
  assert.equal(h.documentElement.dataset.nrUi, "classic");
});

test("Web entrypoints load the shared appearance and matching LIGHT font", () => {
  for (const p of ["index", "dispatch", "driver", "account", "hub", "ethos", "partner-portal"]) {
    const page = read("public/" + p + ".html");
    assert.ok(page.includes('href="/aero-theme.css?v=3"'), p);
    assert.ok(page.includes('src="/aero-theme.js?v=2"'), p);
  }
  const css = read("public/aero-theme.css");
  assert.ok(css.includes('html[data-nr-ui="aero"]'));
  assert.ok(css.includes("Nunito Sans"));
  assert.ok(css.includes("font-family"));
  assert.ok(css.includes("prefers-reduced-motion"));
  assert.ok(css.includes('color-scheme:light'));
  assert.ok(css.includes(".nr-ui-mode-group"));
  assert.ok(read("public/map-theme.js").includes("nightrider.ui-theme.v1"));
});
