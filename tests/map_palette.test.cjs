const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const palette = require("../public/map-midnight.js");

test("Midnight palette keeps the approved Android paint overrides", () => {
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
  assert.deepEqual(palette.apply(mockedMap), ["waterway"]);
  assert.ok(calls.some(c => c.id === "background" && c.name === "background-color" && c.value === "#172635"));
  assert.ok(calls.some(c => c.id === "highway_motorway_inner" && c.name === "line-color" && c.value === "#9BAEC2"));
  assert.ok(calls.some(c => c.id === "place_other" && c.name === "text-opacity" && c.value === 0.2));
  assert.ok(!calls.some(c => c.id === "waterway"));
});

test("operational maps load their preserved shared palette before the map theme", () => {
  for (const name of ["index", "dispatch"]) {
    const html = fs.readFileSync(path.join(__dirname, "..", "public", name + ".html"), "utf8");
    assert.ok(html.indexOf('/map-midnight.js?v=1') < html.indexOf('/map-theme.js?v=2'));
    assert.match(html, /src="\/map-midnight\.js\?v=1"/);
  }
});
