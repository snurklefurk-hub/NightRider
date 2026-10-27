/* NightRider shared map appearance. This changes MAP BASEMAP ONLY.
 * Light = native Android Midnight palette over OpenFreeMap Fiord vectors.
 * Dark = unmodified OpenFreeMap Original Dark vectors.
 *
 * Leaflet pages use official MapLibre/Leaflet adapter, retaining all their
 * existing markers, draggable pins, polylines, popups, routing and controls.
 * If WebGL or a CDN fails, legacy Leaflet raster tiles remain available.
 */
(function (root) {
  "use strict";
  var STORAGE_KEY = "nightrider.map-mode.v1";
  var FIORD = "https://tiles.openfreemap.org/styles/fiord";
  var DARK = "https://tiles.openfreemap.org/styles/dark";
  var listeners = [];
  function safeGet() {
    try { return root.localStorage.getItem(STORAGE_KEY); } catch (_) { return null; }
  }
  function systemDark() {
    try { return !!(root.matchMedia && root.matchMedia("(prefers-color-scheme: dark)").matches); }
    catch (_) { return true; }
  }
  function getMode() {
    try { return root.localStorage.getItem("nightrider.ui-theme.v1") === "aero" ? "light" : "dark"; }
    catch (_) { return "dark"; }
  }
  function url(mode) { return FIORD; }
  function fire() {
    listeners.slice().forEach(function (cb) { cb(mode()); });
    try {
      root.dispatchEvent(new CustomEvent("nightrider:map-mode", { detail: { mode: mode() } }));
    } catch (_) { /* no CustomEvent in test or old browser */ }
  }
  function setMode(mode) {
    if (mode !== "light" && mode !== "dark") return false;
    try { root.localStorage.setItem(STORAGE_KEY, mode); } catch (_) { /* memory-only fallback */ }
    memoryMode = mode;
    fire();
    return true;
  }
  var memoryMode = null;
  function mode() { return memoryMode || getMode(); }
  function subscribe(cb) {
    listeners.push(cb);
    return function () { listeners = listeners.filter(function (x) { return x !== cb; }); };
  }
  function control(map) {
    var parent = map.getContainer();
    var group = document.createElement("div");
    group.className = "nr-map-modes";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Map appearance");
    var buttons = {};
    [["light", "Light"], ["dark", "Dark"]].forEach(function (entry) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = entry[1];
      button.setAttribute("aria-label", entry[1] + " vector map");
      button.addEventListener("click", function () { setMode(entry[0]); });
      group.appendChild(button);
      buttons[entry[0]] = button;
    });
    if (root.L && L.DomEvent) {
      L.DomEvent.disableClickPropagation(group);
      L.DomEvent.disableScrollPropagation(group);
    }
    parent.appendChild(group);
    function update(next) {
      Object.keys(buttons).forEach(function (key) {
        buttons[key].setAttribute("aria-pressed", String(key === next));
      });
    }
    update(mode());
    var off = subscribe(update);
    map.on("unload", function () { off(); group.remove(); });
    return function () { off(); group.remove(); };
  }
  // Attribution stays visible immediately below the map, never covering
  // markers, the route or the light/dark switch. Only static trusted HTML.
  function setCredit(id, provider) {
    var el = document.getElementById(id);
    if (!el) return;
    var osm = '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>';
    var secondary = provider === "vector"
      ? ' · <a href="https://openmaptiles.org/" target="_blank" rel="noopener noreferrer">© OpenMapTiles</a>'
      : provider === "carto"
        ? ' · <a href="https://carto.com/attributions" target="_blank" rel="noopener noreferrer">© CARTO</a>'
        : "";
    el.innerHTML = osm + secondary;
  }
  function attach(map, options) {
    options = options || {};
    if (!root.L || typeof L.maplibreGL !== "function" ||
        !root.maplibregl || typeof root.maplibregl.Map !== "function" ||
        !root.NightRiderMidnight || map._nrVectorFailed) return null;
    try {
      if (typeof root.maplibregl.supported === "function" && !root.maplibregl.supported()) {
        return null;
      }
      var layer = L.maplibreGL({ style: url(mode()), attributionControl: false });
      layer._nrVector = true;
      layer.addTo(map);
      var gl = layer.getMaplibreMap();
      if (!gl || typeof gl.setStyle !== "function") throw new Error("MapLibre was not initialized");
      var ready = false, failed = false, timer = null, off = null, removeControl = null;
      function stop() {
        if (timer) { clearTimeout(timer); timer = null; }
        if (off) { off(); off = null; }
        if (removeControl) { removeControl(); removeControl = null; }
      }
      function fallback() {
        if (failed || ready) return;
        failed = true;
        stop();
        map._nrVectorFailed = true;
        try { map.removeLayer(layer); } catch (_) {}
        if (typeof options.onFallback === "function") options.onFallback();
      }
      function loaded() {
        ready = true;
        if (timer) { clearTimeout(timer); timer = null; }
        if (mode() === "dark") root.NightRiderMidnight.apply(gl);
      }
      gl.on("style.load", loaded);
      gl.on("error", function () {
        // A failing individual tile is not fatal once the style loaded.
        // If the initial style cannot start, the timeout triggers raster fallback.
      });
      timer = setTimeout(fallback, 14000);
      off = subscribe(function (next) {
        if (!failed) {
          try { gl.setStyle(url(next)); } catch (_) { /* preserve current map */ }
        }
      });
      // Appearance is controlled by the shared site-wide Light/Dark switch.
      // The bridge's MapLibre renderer has no built-in attribution overlay.
      // Required provider credits are in a visible external footer.
      if (options.creditId) setCredit(options.creditId, "vector");
      return layer;
    } catch (error) {
      map._nrVectorFailed = true;
      // The plugin may have partly mounted a layer before a GPU error.
      try {
        map.eachLayer(function (x) { if (x._nrVector) map.removeLayer(x); });
      } catch (_) {}
      return null;
    }
  }
  root.addEventListener("storage", function (event) {
    if (event.key === STORAGE_KEY) { memoryMode = null; fire(); }
  });
  root.NightRiderMapTheme = {
    STORAGE_KEY: STORAGE_KEY, FIORD: FIORD, DARK: DARK,
    getMode: mode, setMode: setMode, url: url, subscribe: subscribe,
    setCredit: setCredit, attach: attach
  };
})(window);
