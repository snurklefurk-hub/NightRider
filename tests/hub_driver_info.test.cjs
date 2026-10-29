const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");

test("Hub replaces Driver board with public Info for drivers", () => {
  const hub = read("public/hub.html");
  assert.match(hub, /<h2>Info for drivers<\/h2>/);
  assert.match(hub, /href="\/for-drivers\.html"/);
  assert.doesNotMatch(hub, /<h2>Driver board<\/h2>/);
  assert.doesNotMatch(hub, /\/driver\.html/);
  // Rider, Dispatch, Map Lab, and Account destinations remain intact.
  for (const destination of ["/rider", "/dispatch.html", "/map-lab.html", "/account.html"]) {
    assert.ok(hub.includes('href="' + destination + '"'), destination);
  }
});

test("Driver info page expresses standards, economics and realistic project maturity", () => {
  const page = read("public/for-drivers.html");
  for (const phrase of [
    "A professional ride should feel professional.",
    "The standard comes first.",
    "No race to the bottom.",
    "Your business. Your reputation. Your customers.",
    "How we intend to grow",
    "appropriate licensing and insurance",
    "Broader driver deployment and regional partnerships are goals"
  ]) {
    assert.ok(page.includes(phrase), phrase);
  }
  assert.match(page, /href="\/hub"/);
  assert.match(page, /href="\/aero-theme\.css\?v=3"/);
  assert.match(page, /src="\/aero-theme\.js\?v=2"/);
  assert.ok(page.includes('name="viewport"'));
  assert.ok(page.includes("prefers-reduced-motion") || page.includes("nightrider-motion.js"));
});
