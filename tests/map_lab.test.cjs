/* Dependency-free regression checks for isolated Midnight web map lab. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const palette = require("../public/map-lab-midnight.js");
const read = p => fs.readFileSync(path.join(root, p), "utf8");

test("Midnight palette matches Android's initial experimental vector paint overrides", () => {
  // Explicit expected Android values (nightrider-driver-android PreviewActivity.kt).
  assert.equal(palette.colors.background, "#172635");
  assert.equal(palette.colors.fills.water, "#0D1D33");
  assert.equal(palette.colors.fills.landuse_residential, "#1D2D3C");
  assert.equal(palette.colors.lines.highway_minor, "#536F87");
  assert.equal(palette.colors.lines.highway_major_inner, "#7891A7");
  assert.equal(palette.colors.lines.highway_motorway_inner, "#9BAEC2");
  assert.equal(palette.colors.labels.highway_name_other, "#CEDBE6");
  assert.equal(palette.colors.labels.highway_ref, "#E5EFF7");
  assert.equal(palette.colors.placeOtherOpacity, 0.2);
});

test("palette applies only existing vector layers and leaves unknown layers alone", () => {
  const calls = [];
  const mockedMap = {
    getLayer(id) { return id === "waterway" ? null : { id }; },
    setPaintProperty(id, name, value) { calls.push({ id, name, value }); }
  };
  const missing = palette.apply(mockedMap);
  assert.deepEqual(missing, ["waterway"]);
  assert.ok(calls.some(c => c.id === "background" &&
    c.name === "background-color" && c.value === "#172635"));
  assert.ok(calls.some(c => c.id === "highway_motorway_inner" &&
    c.name === "line-color" && c.value === "#9BAEC2"));
  assert.ok(calls.some(c => c.id === "place_other" &&
    c.name === "text-opacity" && c.value === 0.2));
  assert.ok(!calls.some(c => c.id === "waterway"));
});

test("preview is independent and makes no mutating API calls", () => {
  const js = read("public/map-lab.js");
  const html = read("public/map-lab.html");
  assert.match(js, /\/api\/dispatch\/map/);
  assert.match(js, /credentials:\s*"same-origin"/);
  assert.doesNotMatch(js, /method:\s*["'`](?:POST|PATCH|PUT|DELETE)["'`]/i);
  assert.doesNotMatch(js, /\/api\/dispatch\/rides\/.*\/ack/);
  assert.match(html, /Read-only/i);
  assert.match(html, /maplibre-gl@6\.15\.0/);
  assert.match(html, /map-lab-midnight\.js/);
  assert.match(js, /maxPitch:\s*0/);
  assert.match(js, /touchPitch:\s*false/);
  assert.match(js, /PRESETS\.streets\.center/);
});

test("MapLibre v6 loads its actual ESM entrypoint and has a second CDN", () => {
  const js = read("public/map-lab.js");
  const html = read("public/map-lab.html");
  // v6 removed the old UMD bundle and no longer exports supported().
  assert.ok(!html.includes('src="https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.js"'));
  assert.ok(!js.includes("maplibregl.supported("));
  assert.ok(js.includes("https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.mjs"));
  assert.ok(js.includes("https://cdn.jsdelivr.net/npm/maplibre-gl@6.15.0/dist/maplibre-gl.mjs"));
  assert.ok(js.includes("await import(url)"));
  assert.ok(js.includes("GPUInitializationError"));
  assert.ok(html.includes("/map-lab.js?v=5"));
  assert.ok(html.includes("maplibre-gl@6.15.0/dist/maplibre-gl.css"));
});

test("production Leaflet pages remain separate from the lab", () => {
  assert.match(read("public/dispatch.html"), /leaflet@1\.9\.4/);
  assert.match(read("public/index.html"), /leaflet@1\.9\.4/);
  assert.ok(!read("public/dispatch.html").includes("map-lab.js"));
  assert.ok(!read("public/index.html").includes("map-lab.js"));
});


test("locally parses a NightRider Field Test CSV without any server request", () => {
  const trace = require("../public/map-lab-trace.js");
  const file = "epoch_ms,latitude,longitude,accuracy_m,speed_mps\n" +
    "1793113000000,32.0809,-81.0912,5.0,3.5\n" +
    "1793113001500,32.0811,-81.0909,8.0,7.2\n";
  const points = trace.parseCsv(file);
  assert.equal(points.length, 2);
  assert.deepEqual([points[1].lon, points[1].lat], [-81.0909, 32.0811]);
  assert.throws(() => trace.parseCsv(file.replace("32.0811", "999")), /Invalid coordinates/);
  assert.throws(() => trace.parseCsv(file.replace("1793113001500", "1793113000000")), /Invalid coordinates/);
  assert.throws(() => trace.parseCsv("unexpected.csv"), /not a NightRider/);
  assert.match(read("public/map-lab.html"), /id="labTraceFile"/);
  assert.match(read("public/map-lab.js"), /lab-field-trace/);
  assert.match(read("public/map-lab.html"), /map-lab-trace\.js/);
  assert.doesNotMatch(read("public/map-lab-trace.js"), /fetch\(|XMLHttpRequest|localStorage/);
});

test("field trace metrics flag weak GPS and filter implausible jumps", () => {
  const trace = require("../public/map-lab-trace.js");
  const fixes = [
    {epochMs:1000,lat:32,lon:-81,accuracyM:5,speedMps:0},
    {epochMs:11000,lat:32.0005,lon:-81,accuracyM:5,speedMps:6},
    {epochMs:12000,lat:33,lon:-81,accuracyM:60,speedMps:0}
  ];
  const m = trace.summarize(fixes);
  assert.equal(m.fixes,3);
  assert.equal(m.durationS,11);
  assert.equal(m.inaccurate,1);
  assert.equal(m.largestGapS,10);
  assert.ok(m.distanceM > 50 && m.distanceM < 60);
  assert.equal(trace.summarize([]),null);
  assert.match(read("public/map-lab.js"), /summarize\(fixes\)/);
});
