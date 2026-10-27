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
      button.textContent = aero ? "Classic" : "Aero";
      button.setAttribute("aria-label", aero ? "Switch to Classic NightRider appearance" :
        "Switch to Frutiger Aero appearance");
      button.setAttribute("aria-pressed", String(aero));
      button.title = aero ? "Classic theme" : "Frutiger Aero theme";
    });
  }
  function set(next) {
    if (next !== "classic" && next !== "aero") return false;
    try { root.localStorage.setItem(key, next); } catch (_) {}
    paint(next);
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
    if (event.key === key) paint(current());
  });
  root.NightRiderUiTheme = { key: key, current: current, set: set };
  if (root.document.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else mount();
})(window);
