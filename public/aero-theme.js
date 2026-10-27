/* One NightRider appearance preference. LIGHT = Aero/Midnight vector map;
 * DARK = Classic/Original Dark vector map. Never changes ride or session data. */
(function (root) {
  "use strict";
  var key = "nightrider.ui-theme.v1";
  var memory = null;
  function current() {
    if (memory) return memory;
    try {
      var stored = root.localStorage.getItem(key);
      return stored === "aero" || stored === "light" ? "light" : "dark";
    } catch (_) {
      return root.document.documentElement.dataset.nrUi === "aero" ? "light" : "dark";
    }
  }
  function paint(next) {
    var light = next === "light";
    root.document.documentElement.dataset.nrUi = light ? "aero" : "classic";
    root.document.documentElement.style.colorScheme = light ? "light" : "dark";
    root.document.querySelectorAll(".nr-ui-theme-toggle").forEach(function (button) {
      var selected = button.dataset.mode === next;
      button.setAttribute("aria-pressed", String(selected));
    });
    try {
      root.dispatchEvent(new CustomEvent("nightrider:ui-theme", { detail: { mode: next } }));
    } catch (_) { /* old or limited clients */ }
  }
  function set(next) {
    if (next !== "light" && next !== "dark") return false;
    memory = next;
    // Keep the previous Aero/Classic storage values so existing users retain
    // their choices; there is no second, independently persisted map preference.
    try { root.localStorage.setItem(key, next === "light" ? "aero" : "classic"); } catch (_) {}
    paint(next);
    return true;
  }
  function mount() {
    paint(current());
    var anchor = root.document.querySelector("header nav") ||
      root.document.querySelector(".lab-header") ||
      root.document.querySelector("main");
    if (!anchor) return;
    var group = root.document.createElement("div");
    group.className = "nr-ui-mode-group";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Appearance");
    ["light", "dark"].forEach(function (mode) {
      var button = root.document.createElement("button");
      button.type = "button";
      button.className = "nr-ui-theme-toggle";
      button.dataset.mode = mode;
      button.textContent = mode.toUpperCase();
      button.setAttribute("aria-label", mode.toUpperCase());
      button.addEventListener("click", function () { set(mode); });
      group.appendChild(button);
    });
    anchor.appendChild(group);
    paint(current());
  }
  root.addEventListener("storage", function (event) {
    if (event.key === key) { memory = null; paint(current()); }
  });
  root.NightRiderUiTheme = { key: key, current: current, set: set };
  // This small script loads in <head> before the page paints; apply saved
  // colors without adding an inline script that disrupts Dispatch's test harness.
  paint(current());
  if (root.document.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else mount();
})(window);
