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
  // Retain the old map-mode key name for API compatibility only. It is never
  // independently read or written: the site appearance preference owns maps.
  var STORAGE_KEY = "nightrider.ui-theme.v1";
  var FIORD = "https://tiles.openfreemap.org/styles/fiord";
  var DARK = "https://tiles.openfreemap.org/styles/dark";
  var listeners = [];
  function mode() {
    if (root.NightRiderUiTheme) return root.NightRiderUiTheme.current();
    try {
      var stored = root.localStorage.getItem(STORAGE_KEY);
      return stored === "aero" || stored === "light" ? "light" : "dark";
    } catch (_) {
      return root.document.documentElement.dataset.nrUi === "aero" ? "light" : "dark";
    }
  }
  function url(next) { return next === "light" ? FIORD : DARK; }
  function fire() {
    var next = mode();
    listeners.slice().forEach(function (cb) { cb(next); });
    try { root.dispatchEvent(new CustomEvent("nightrider:map-mode", { detail: { mode: next } })); }
    catch (_) {}
  }
  function setMode(next) {
    // Kept for existing callers but always delegates to the one UI setting.
    if (next !== "light" && next !== "dark") return false;
    if (root.NightRiderUiTheme) return root.NightRiderUiTheme.set(next);
    try { root.localStorage.setItem(STORAGE_KEY, next === "light" ? "aero" : "classic"); }
    catch (_) { root.document.documentElement.dataset.nrUi = next === "light" ? "aero" : "classic"; }
    fire();
    return true;
  }
  function subscribe(cb) {
    listeners.push(cb);
    return function () { listeners = listeners.filter(function (x) { return x !== cb; }); };
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
      var ready = false, failed = false, timer = null, off = null;
      function stop() {
        if (timer) { clearTimeout(timer); timer = null; }
        if (off) { off(); off = null; }
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
        if (mode() === "light") root.NightRiderMidnight.apply(gl);
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
  root.addEventListener("nightrider:ui-theme", fire);
  root.addEventListener("storage", function (event) {
    if (event.key === STORAGE_KEY) fire();
  });
  root.NightRiderMapTheme = {
    STORAGE_KEY: STORAGE_KEY, FIORD: FIORD, DARK: DARK,
    getMode: mode, setMode: setMode, url: url, subscribe: subscribe,
    setCredit: setCredit, attach: attach
  };
})(window);
