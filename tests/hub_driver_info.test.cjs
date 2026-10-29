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

test("Hub has separate public customer and driver information destinations", () => {
  const hub = read("public/hub.html");
  assert.match(hub, /<h2>Info for customers<\/h2>/);
  assert.match(hub, /href="\/for-customers\.html"/);
  assert.match(hub, /<h2>Info for drivers<\/h2>/);
  assert.doesNotMatch(hub, /<h2>Driver board<\/h2>/);
  // Keep direct rider booking and the other ecosystem modules.
  for (const link of ["/rider", "/dispatch.html", "/map-lab.html", "/account.html"]) {
    assert.ok(hub.includes('href="' + link + '"'), link);
  }
});

test("Customer page explains NightRider standards without promising guaranteed coverage", () => {
  const page = read("public/for-customers.html");
  for (const phrase of [
    "A ride you can feel good about booking.",
    "Clean, comfortable, and calm.",
    "Know what to expect.",
    "Clarity beats gimmicks.",
    "A familiar driver beats another mystery ride.",
    "No separate customer app to download.",
    "A request isn't a guaranteed ride",
    "not a nationwide fleet or an always-available on-demand network"
  ]) {
    assert.ok(page.includes(phrase), phrase);
  }
  assert.match(page, /href="\/rider"/);
  assert.match(page, /href="\/hub"/);
  assert.match(page, /href="\/for-drivers\.html"/);
  assert.match(page, /href="\/aero-theme\.css\?v=3"/);
  assert.match(page, /src="\/aero-theme\.js\?v=2"/);
  assert.ok(page.includes('name="viewport"'));
});
