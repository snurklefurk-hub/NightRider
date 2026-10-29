const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");

test("Hub has the eight requested destinations and an empty non-interactive partner placeholder", () => {
  const hub = read("public/hub.html");
  const tiles = [...hub.matchAll(/<(a|div) class="card hub-tile"([^>]*)>\s*<h2>(.*?)<\/h2>([\s\S]*?)<\/\1>/g)];
  assert.deepEqual(tiles.map(tile => tile[3]), [
    "Info for Riders", "Info for Drivers", "Affiliates and Partners", "Our Ethos",
    "Rider Demo", "Driver Demo", "Dispatch Demo", "Partner Portal"
  ]);
  assert.equal(tiles[2][1], "div");
  assert.equal(tiles[2][2], "");
  assert.equal(tiles[2][4].trim(), "");
  assert.match(hub, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(hub, /max-width: 900px/);
  assert.match(hub, /max-width: 520px/);
});

test("public pages have no retired preview mentions or links, and all local page links resolve", () => {
  const shortRoutes = {"/hub":"hub.html", "/rider":"index.html", "/partner-portal":"partner-portal.html",
    "/partner-desk":"partner-desk.html", "/partner-desk-demo":"partner-desk.html", "/affiliate-hub":"affiliate-hub.html"};
  for (const name of fs.readdirSync(path.join(root, "public")).filter(name => name.endsWith(".html"))) {
    const html = read("public/" + name);
    assert.doesNotMatch(html, /map[ -]?lab/i, name);
    for (const match of html.matchAll(/href="(\/[^"#]*)"/g)) {
      const pathname = new URL(match[1], "http://local.test").pathname;
      const target = shortRoutes[pathname] || pathname.slice(1);
      assert.ok(fs.existsSync(path.join(root, "public", target)), name + ": " + pathname);
    }
  }
});

test("Hub keeps driver info and offers authenticated Driver demo", () => {
  const hub = read("public/hub.html");
  assert.match(hub, /<h2>Info for Drivers<\/h2>/);
  assert.match(hub, /href="\/for-drivers\.html"/);
  assert.doesNotMatch(hub, /<h2>Driver board<\/h2>/);
  assert.match(hub, /data-demo-role="driver" data-demo-target="\/driver\.html"/);
  assert.doesNotMatch(hub, /href="\/driver\.html"/);
  // Rider and Dispatch open their shared demo account automatically.
  for (const destination of ["/rider", "/dispatch.html"]) {
    assert.ok(hub.includes('data-demo-target="' + destination + '"'), destination);
  }
  for (const destination of ["/partner-portal", "/account.html"]) {
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

test("Hub has separate public rider and driver information destinations", () => {
  const hub = read("public/hub.html");
  assert.match(hub, /<h2>Info for Riders<\/h2>/);
  assert.match(hub, /href="\/for-customers\.html"/);
  assert.match(hub, /<h2>Info for Drivers<\/h2>/);
  assert.doesNotMatch(hub, /<h2>Driver board<\/h2>/);
  // Keep rider and dispatch demo paths plus separate information pages.
  for (const link of ["/rider", "/dispatch.html"]) {
    assert.ok(hub.includes('data-demo-target="' + link + '"'), link);
  }
  for (const link of ["/partner-portal", "/account.html"]) {
    assert.ok(hub.includes('href="' + link + '"'), link);
  }
});

test("Customer page explains design aspirations and simulated use without offering service", () => {
  const page = read("public/for-customers.html");
  for (const phrase of [
    "For the people in the passenger seat",
    "The idea: Courtesy, consistency, quality, and safety.",
    "Be what Rideshare was supposed to be: The Modern Taxi.",
    "PROFESSIONAL",
    "Ease of use, availability on any device, convenience, and data security via non-collection.",
    "01 / COMFORT",
    "Clean, comfortable, and calm.",
    "Our bare minimum is what the other guys call Premium.",
    "02 / DEPENDABILITY",
    "Know what to expect.",
    "03 / RESPECT &amp; SAFETY",
    "Professional on both sides of the door.",
    "Our drivers <strong>NEVER</strong> use voice calling",
    "04 / HONEST VALUE",
    "Clarity beats gimmicks.",
    "25¢ per mile to come to you, $1 per mile to take you there, and $5 on top per ride (flag drop or cancellation).",
    "No surging, no surprises.",
    "A familiar driver beats another mystery ride.",
    "All drivers are vetted, tested, and checked <strong>FAR</strong> above industry standards.",
    "No separate customer app to download.",
    "book a ride from any device.",
    "Use practice trip details.",
    "Try the other sides.",
    "No transportation services are offered",
    "all trips are simulated",
    "Nothing is live except the code"
  ]) {
    assert.ok(page.includes(phrase), phrase);
  }
  assert.match(page, /href="\/rider"/);
  assert.match(page, /href="\/hub"/);
  assert.match(page, /href="\/for-drivers\.html"/);
  assert.match(page, /href="\/account\.html\?demo=rider"[^>]*>Try the Rider demo<\/a>/);
  assert.match(page, /href="\/hub"[^>]*>Back to the Hub<\/a>/);
  assert.match(page, /href="\/for-drivers\.html"[^>]*>Read the ideas behind the Driver tools\.<\/a>/);
  assert.doesNotMatch(page, /book a ride from and device/);
  const order = ["01 / COMFORT", "02 / DEPENDABILITY", "03 / RESPECT &amp; SAFETY", "04 / HONEST VALUE"];
  assert.deepEqual(order.map(text => page.indexOf(text)), [...order.map(text => page.indexOf(text))].sort((a,b)=>a-b));
  assert.ok(order.every(text => page.indexOf(text) >= 0));
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
