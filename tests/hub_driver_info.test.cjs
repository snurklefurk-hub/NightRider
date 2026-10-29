const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");

test("Hub keeps driver info and offers authenticated Driver demo", () => {
  const hub = read("public/hub.html");
  assert.match(hub, /<h2>Info for drivers<\/h2>/);
  assert.match(hub, /href="\/for-drivers\.html"/);
  assert.doesNotMatch(hub, /<h2>Driver board<\/h2>/);
  assert.match(hub, /data-demo-role="driver" data-demo-target="\/driver\.html"/);
  assert.doesNotMatch(hub, /href="\/driver\.html"/);
  // Rider and Dispatch open their shared demo account automatically.
  for (const destination of ["/rider", "/dispatch.html"]) {
    assert.ok(hub.includes('data-demo-target="' + destination + '"'), destination);
  }
  for (const destination of ["/map-lab.html", "/account.html"]) {
    assert.ok(hub.includes('href="' + destination + '"'), destination);
  }
});

test("Driver info page expresses future standards and a software-only preview", () => {
  const page = read("public/for-drivers.html");
  for (const phrase of [
    "A professional ride should feel professional.",
    "The standard comes first.",
    "No race to the bottom.",
    "Your business. Your reputation. Your customers.",
    "What you can explore today",
    "appropriate licensing and insurance",
    "No transportation services are offered",
    "all trips are simulated"
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
  // Keep rider and dispatch demo paths plus separate information pages.
  for (const link of ["/rider", "/dispatch.html"]) {
    assert.ok(hub.includes('data-demo-target="' + link + '"'), link);
  }
  for (const link of ["/map-lab.html", "/account.html"]) {
    assert.ok(hub.includes('href="' + link + '"'), link);
  }
});

test("Customer page explains design aspirations and simulated use without offering service", () => {
  const page = read("public/for-customers.html");
  for (const phrase of [
    "The idea: a ride you could feel good about booking.",
    "Clean, comfortable, and calm.",
    "Know what to expect.",
    "Clarity beats gimmicks.",
    "A familiar driver beats another mystery ride.",
    "No separate customer app to download.",
    "No transportation services are offered",
    "all trips are simulated",
    "Nothing is live except the code"
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

test("Public demo entry points publish all three roles without active-service or signup claims", () => {
  const hub = read("public/hub.html");
  const customers = read("public/for-customers.html");
  const drivers = read("public/for-drivers.html");
  const welcome = read("public/welcome.js");
  assert.ok(hub.includes('/account.html?demo=driver'));
  assert.ok(customers.includes('/account.html?demo=rider'));
  assert.ok(drivers.includes('/account.html?demo=driver'));
  for (const source of [hub, customers, drivers, welcome]) {
    assert.match(source, /DEMO/);
    assert.match(source, /PASSWORD/);
    assert.match(source, /[Pp]ublic rider account creation is paused|[Pp]ublic rider registration is paused/);
    assert.doesNotMatch(source, /We're growing carefully|evolving pilot|always on duty|register as a rider|no Indians/i);
  }
});
