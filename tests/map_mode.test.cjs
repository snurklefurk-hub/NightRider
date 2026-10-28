const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");

function themeHarness(savedAppearance) {
  const saved = new Map(), events = [], listeners = {};
  if (savedAppearance) saved.set("nightrider.ui-theme.v1", savedAppearance);
  const window = {
    document: { documentElement: { dataset: { nrUi: "classic" } } },
    localStorage: {
      getItem: key => saved.has(key) ? saved.get(key) : null,
      setItem: (key, value) => saved.set(key, value)
    },
    addEventListener(name, callback) { listeners[name] = callback; },
    dispatchEvent(event) { events.push(event); }
  };
  class CustomEvent {
    constructor(name, options) { this.type = name; this.detail = options.detail; }
  }
  vm.runInNewContext(read("public/map-theme.js"), { window, CustomEvent, console });
  return { theme: window.NightRiderMapTheme, window, saved, events, listeners };
}

test("LIGHT always uses Midnight vector Fiord; DARK uses Original Dark vector", () => {
  const { theme } = themeHarness();
  assert.equal(theme.getMode(), "dark");
  assert.equal(theme.url("light"), "https://tiles.openfreemap.org/styles/fiord");
  assert.equal(theme.url("dark"), "https://tiles.openfreemap.org/styles/dark");
  assert.equal(theme.setMode("light"), true);
  assert.equal(theme.getMode(), "light");
  assert.equal(theme.setMode("dark"), true);
  assert.equal(theme.getMode(), "dark");
  assert.equal(theme.setMode("mystery"), false);
});

test("map mode derives from one shared appearance preference, including prior Aero settings", () => {
  const h = themeHarness("aero");
  assert.equal(h.theme.getMode(), "light");
  let notified;
  h.theme.subscribe(next => { notified = next; });
  h.theme.setMode("dark");
  assert.equal(h.saved.get("nightrider.ui-theme.v1"), "classic");
  assert.equal(notified, "dark");
  assert.equal(h.events.at(-1).detail.mode, "dark");
  h.theme.setMode("light");
  assert.equal(notified, "light");
  assert.ok(!h.saved.has("nightrider.map-mode.v1"));
});

test("Rider and Dispatch keep original Leaflet controls and acquire vector base with raster fallback", () => {
  const rider = read("public/index.html");
  const dispatch = read("public/dispatch.html");
  const code = read("public/dispatch-map.js");
  for (const html of [rider, dispatch]) {
    assert.match(html, /leaflet@1\.9\.4/);
    assert.ok(html.includes("maplibre-gl@5.17.0/dist/maplibre-gl.js"));
    assert.ok(html.includes("@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js"));
    assert.ok(html.includes("/map-theme.js?v=2"));
    assert.ok(html.includes("/map-theme.css?v=2"));
  }
  assert.ok(rider.includes("NightRiderMapTheme.attach(map"));
  assert.ok(rider.includes("addLegacyBaseMap(cartoKey)"));
  assert.ok(rider.includes("L.marker(latlng, { icon: pickIcon, draggable: true })"));
  assert.ok(code.includes("NightRiderMapTheme.attach(map"));
  assert.ok(code.includes("mapTileLayer(true"));
  assert.ok(code.includes("L.layerGroup()"));
  assert.ok(code.includes("L.polyline("));
  assert.ok(!read("public/map-theme.js").includes("api.maptiler.com"));
});
test("standalone Web Map Lab shares Light and Dark browser preference", () => {
  const html = read("public/map-lab.html");
  const js = read("public/map-lab.js");
  assert.ok(!html.includes('id="labStyle"'));
  assert.ok(html.includes('src="/aero-theme.js?v=2"'));
  assert.ok(html.includes("/map-theme.js?v=2"));
  assert.ok(html.includes("/map-lab.js?v=8"));
  assert.ok(js.includes('theme.getMode()'));
  assert.ok(js.includes('window.addEventListener("nightrider:map-mode"'));
  assert.ok(js.includes('if (selectedStyle === "light")'));
});

test("Map controls are gone; a single site-wide LIGHT/DARK selector owns maps", () => {
  const mapTheme = read("public/map-theme.js");
  const aero = read("public/aero-theme.js");
  assert.ok(!mapTheme.includes("function control(map)"));
  assert.ok(!mapTheme.includes("control(map);"));
  assert.ok(!read("public/map-theme.css").includes(".nr-map-modes"));
  assert.ok(!read("public/map-lab.html").includes('id="labStyle"'));
  assert.ok(aero.includes('["light", "dark"]'));
  assert.ok(aero.includes("mode.toUpperCase()"));
  assert.ok(mapTheme.includes('root.addEventListener("nightrider:ui-theme", fire)'));
});

test("Dispatch individual layer checkboxes replace Leaflet's overlapping Layers menu", () => {
  const html = read("public/dispatch.html");
  const js = read("public/dispatch-map.js");
  const css = read("public/dispatch-map.css");
  for (const id of ["mapShowDrivers", "mapShowRidePins", "mapShowRiders", "mapShowDispatch", "mapShowRoutes"]) {
    assert.ok(html.includes('id="' + id + '" checked'), id + " is enabled initially");
    assert.ok(js.includes(id + ":"), id + " maps to a dedicated Leaflet layer");
  }
  const first = html.indexOf('id="mapShowOffline"');
  const last = html.indexOf('id="mapShowRoutes"');
  const canvas = html.indexOf('id="dispatchMap"');
  assert.ok(first >= 0 && last > first && canvas > last, "filters remain adjacent, above map");
  assert.ok(js.includes('input.addEventListener("change", function ()'));
  assert.ok(js.includes("map.removeLayer(layer)"));
  assert.ok(js.includes("map.addLayer(layer)"));
  assert.ok(js.includes('map.hasLayer(layer)'));
  assert.ok(!js.includes("L.control.layers("));
  assert.ok(!css.includes(".leaflet-control-layers-toggle"));
});

test("Rider, Dispatch and Map Lab put required attribution adjacent to, never on, the map", () => {
  const rider = read("public/index.html");
  const dispatchHtml = read("public/dispatch.html");
  const dispatchJs = read("public/dispatch-map.js");
  const theme = read("public/map-theme.js");
  const labHtml = read("public/map-lab.html");
  const labJs = read("public/map-lab.js");
  for (const html of [rider, dispatchHtml, labHtml]) {
    assert.ok(html.includes("openstreetmap.org/copyright"));
    assert.ok(html.includes("openmaptiles.org"));
    assert.ok(html.includes("© OpenStreetMap contributors"));
    assert.ok(html.includes("© OpenMapTiles"));
  }
  assert.ok(rider.includes("id=\"riderMapCredit\""));
  assert.ok(dispatchHtml.includes("id=\"dispatchMapCredit\""));
  assert.ok(labHtml.includes("class=\"nr-lab-map-credit\""));
  assert.ok(rider.includes("attributionControl: false"));
  assert.ok(dispatchJs.includes("attributionControl: false"));
  assert.ok(labJs.includes("attributionControl: false"));
  assert.ok(!labHtml.includes("map-ribbon"));
  assert.ok(theme.includes('attributionControl: false'));
  assert.ok(theme.includes('setCredit: setCredit'));
  assert.ok(theme.includes('creditId'));
  assert.ok(theme.includes('provider === "carto"'));
  assert.ok(theme.includes('provider === "vector"'));
  assert.ok(!theme.includes("map.attributionControl.addAttribution("));
  assert.ok(!dispatchJs.includes("FOSSGIS routing"));
  assert.ok(!dispatchJs.includes("Fix the map"));
  assert.ok(rider.includes("carto.com/attributions"));
});

test("Rider address entry works without a redundant Search button", () => {
  const html = read("public/index.html");
  assert.ok(!html.includes('id="searchBtn"'));
  assert.ok(!html.includes('$("searchBtn")'));
  assert.ok(html.includes('id="pickup"'));
  assert.ok(html.includes('id="dropoff"'));
  assert.ok(html.includes('id="results"'));
  assert.ok(html.includes('e.key === "Enter"'));
  assert.ok(html.includes("scheduleSearch(input.value)"));
  assert.ok(html.includes("Press Enter to find this address."));
  assert.ok(html.includes('id="useLocation"'));
  assert.ok(html.includes('id="pinPickup"'));
  assert.ok(html.includes('id="pinDropoff"'));
});
