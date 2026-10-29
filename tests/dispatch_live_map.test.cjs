const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname,"../public/dispatch-map.js"),"utf8");
const html = fs.readFileSync(path.join(__dirname,"../public/dispatch.html"),"utf8");
const css = fs.readFileSync(path.join(__dirname,"../public/dispatch-map.css"),"utf8");

test("same exact geographic point is one co-located pair; other points stay distinct", () => {
  const startPoint=source.indexOf("  function point(value) {");
  const endPoint=source.indexOf("  function now() {",startPoint);
  const startPair=source.indexOf("  function coLocated(a, b) {");
  const endPair=source.indexOf("  function mapTileLayer(",startPair);
  assert.ok(startPoint > 0 && endPoint > startPoint);
  assert.ok(startPair > 0 && endPair > startPair);
  const coLocated=vm.runInNewContext(
    source.slice(startPoint,endPoint)+"\n"+
    source.slice(startPair,endPair)+"\ncoLocated;",{});
  assert.equal(coLocated([32.1378,-81.247],[32.1378,-81.247]),true);
  assert.equal(coLocated([32.0631,-81.0856],[32.0631,-81.0856]),true);
  assert.equal(coLocated([32.0814,-81.0912],[32.0766,-81.0871]),false);
  assert.equal(coLocated(null,[32.0814,-81.0912]),false);
  assert.equal(coLocated([200,-81],[200,-81]),false);
  assert.equal(coLocated([32.0814,-81.0912],[32.08141,-81.0912]),false,
    "Never move or merge distinct geographic points through screen-space trickery");
});

test("D+R is one keyboard-accessible topmost pin that names both humans", () => {
  const start=source.indexOf("  function markerIcon(");
  const end=source.indexOf("  function syncMarker(",start);
  assert.ok(start>0&&end>start);
  const markerIcon=vm.runInNewContext(source.slice(start,end)+"\nmarkerIcon;",
    {L:{divIcon(opts){return opts;}}});
  const pair=markerIcon("pair","#f4b860",false,true);
  assert.match(pair.className,/is-demo/);
  assert.match(pair.html,/D\+R/);
  assert.equal(pair.iconSize[0],40);
  assert.match(source,/zIndexOffset:\s*\{ pair: 800/);
  assert.match(source,/Driver:.*?esc\(driver\.name\)/s);
  assert.match(source,/Rider:.*?esc\(ride\.rider_name\)/s);
  assert.match(css,/\.nr-map-pin\.pair\{/);
  assert.match(html,/D\+R at one location/);
});

test("map keeps fixed DEMO geometry outside live location and road routing", () => {
  assert.match(source,/demoLayer = L\.layerGroup\(\)\.addTo\(map\)/);
  assert.match(source,/mapShowDemo: demoLayer/);
  assert.match(source,/if \(ride\.demo_preview\) return; \/\/ DEMO routes/);
  assert.match(source,/visibleRides\(\)\.filter\(function \(r\) \{ return !r\.demo_preview; \}\)/);
  assert.match(source,/Fixed fictional placement, not live GPS/);
  assert.match(source,/DEMO straight-line route · illustrative only, no ETA/);
  assert.match(source,/selectedId \? allMapRides\(\)\.filter/);
  assert.match(source,/snapshot\.demo_drivers \|\| \[\]/);
  assert.match(source,/if \(showDrivers && showRiders && driver/);
});
