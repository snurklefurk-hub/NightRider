const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const read = p => fs.readFileSync(path.join(root, p), "utf8");

function bootstrap(initial) {
  const store = new Map(initial ? [["nightrider.ui-theme.v1", initial]] : []);
  const tags = [], listeners = {};
  const documentElement = { dataset: {}, style: {} };
  const host = { appendChild: item => tags.push(item) };
  const document = {
    readyState: "complete", documentElement,
    querySelector: selector => selector === "header nav" ? host : null,
    querySelectorAll: () => tags,
    createElement() {
      const attributes = {};
      return { className: "", textContent: "", title: "", type: "",
        addEventListener(name, cb) { this[name] = cb; },
        setAttribute(key, value) { attributes[key] = value; },
        getAttribute(key) { return attributes[key]; } };
    }
  };
  const window = { document, localStorage: {
    getItem(key) { return store.get(key) || null; },
    setItem(key, value) { store.set(key, value); }
  }, addEventListener(name, cb) { listeners[name] = cb; } };
  vm.runInNewContext(read("public/aero-theme.js"), { window, console });
  return { window, store, tags, documentElement, listeners };
}

test("Classic is default and Aero persists without changing NightRider map mode", () => {
  const h = bootstrap();
  assert.equal(h.window.NightRiderUiTheme.current(), "classic");
  assert.equal(h.documentElement.dataset.nrUi, "classic");
  assert.equal(h.tags.length, 1);
  assert.equal(h.tags[0].textContent, "Aero");
  assert.equal(h.window.NightRiderUiTheme.set("aero"), true);
  assert.equal(h.store.get("nightrider.ui-theme.v1"), "aero");
  assert.equal(h.documentElement.dataset.nrUi, "aero");
  assert.equal(h.tags[0].textContent, "Classic");
  assert.equal(h.tags[0].getAttribute("aria-pressed"), "true");
  assert.equal(h.window.NightRiderUiTheme.set("invalid"), false);
  assert.ok(!h.store.has("nightrider.map-mode.v1"));
});

test("All five web entrypoints load the same opt-in Aero CSS and JS", () => {
  for (const p of ["index", "dispatch", "driver", "account", "map-lab"]) {
    const page = read("public/" + p + ".html");
    assert.ok(page.includes('href="/aero-theme.css?v=1"'), p);
    assert.ok(page.includes('src="/aero-theme.js?v=1"'), p);
  }
  const css = read("public/aero-theme.css");
  assert.ok(css.includes('html[data-nr-ui="aero"]'));
  assert.ok(css.includes(".nr-ui-theme-toggle"));
  assert.ok(css.includes("prefers-reduced-motion"));
  assert.ok(css.includes("color-scheme:light"));
  assert.ok(!read("public/map-theme.js").includes("nightrider.ui-theme.v1"));
});
