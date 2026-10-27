/* Optional Frutiger Aero UI theme, independent from vector map Light/Dark mode.
 * Classic remains the default. Never changes ride, account or dispatch state.
 */
(function (root) {
  "use strict";
  var key = "nightrider.ui-theme.v1";
  function current() {
    try { return root.localStorage.getItem(key) === "aero" ? "aero" : "classic"; }
    catch (_) { return root.document.documentElement.dataset.nrUi === "aero" ? "aero" : "classic"; }
  }
  function paint(next) {
    root.document.documentElement.dataset.nrUi = next === "aero" ? "aero" : "classic";
    root.document.documentElement.style.colorScheme = next === "aero" ? "light" : "dark";
    root.document.querySelectorAll(".nr-ui-theme-toggle").forEach(function (button) {
      var aero = next === "aero";
      button.textContent = aero ? "DARK" : "LIGHT";
      button.setAttribute("aria-label", aero ? "Switch to dark mode" : "Switch to light mode");
      button.setAttribute("aria-pressed", String(aero));
      button.title = aero ? "DARK" : "LIGHT";
    });
  }
  function set(next) {
    if (next !== "classic" && next !== "aero") return false;
    try { root.localStorage.setItem(key, next); } catch (_) {}
    paint(next);
    if (root.NightRiderMapTheme) root.NightRiderMapTheme.setMode(next === "aero" ? "light" : "dark");
    return true;
  }
  function mount() {
    paint(current());
    var anchor = root.document.querySelector("header nav") ||
      root.document.querySelector(".lab-header") ||
      root.document.querySelector("main");
    if (!anchor) return;
    var button = root.document.createElement("button");
    button.type = "button";
    button.className = "nr-ui-theme-toggle";
    anchor.appendChild(button);
    button.addEventListener("click", function () { set(current() === "aero" ? "classic" : "aero"); });
    paint(current());
  }
  root.addEventListener("storage", function (event) {
    if (event.key === key) { paint(current()); if (root.NightRiderMapTheme) root.NightRiderMapTheme.setMode(current() === "aero" ? "light" : "dark"); }
  });
  root.NightRiderUiTheme = { key: key, current: current, set: set };
  if (root.document.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else mount();
})(window);
