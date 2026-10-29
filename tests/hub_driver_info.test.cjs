const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");

test("Hub keeps the eight requested destinations with a public affiliate-info link", () => {
  const hub = read("public/hub.html");
  const tiles = [...hub.matchAll(/<(a|div) class="card hub-tile"([^>]*)>\s*<h2>(.*?)<\/h2>([\s\S]*?)<\/\1>/g)];
  assert.deepEqual(tiles.map(tile => tile[3]), [
    "Info for Riders", "Info for Drivers", "Affiliates and Partners", "Our Ethos",
    "Rider Demo", "Driver Demo", "Dispatch Demo", "Partner Portal"
  ]);
  assert.equal(tiles[2][1], "a");
  assert.match(tiles[2][2], /href="\/for-affiliates\.html"/);
  assert.match(tiles[2][4], /Plans for hotels and venues: concierge bookings/);
  assert.match(hub, /<a class="card hub-tile" href="\/partner-portal">\s*<h2>Partner Portal<\/h2>/);
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

test("Affiliates and Partners page describes future workflows honestly and retains portal links", () => {
  const hub = read("public/hub.html");
  const page = read("public/for-affiliates.html");
  assert.match(hub, /href="\/for-affiliates\.html"[^>]*>\s*<h2>Affiliates and Partners<\/h2>/);
  for (const phrase of [
    "We're looking forward to working with other companies in the future.",
    "Hotels, resorts, bars, clubs, restaurants",
    "A third-party portal built for your clientele",
    "upfront pricing and availability",
    "SMS message",
    "one-click account setup or sign-in",
    "appropriate customer consent",
    "Concierge fees and flexible pricing",
    "concierge/front desk fee",
    "transparent or opaque pricing",
    "required fare disclosures to riders",
    "integrate seamlessly into the NightRider ecosystem",
    "A real local company. A real dispatcher.",
    "You're not just sending a ride request out into the aether",
    "real local transportation company",
    "live dispatcher always on duty while we're accepting bookings",
    "Your request won't just disappear into an algorithm.",
    "non-emergency medical transportation (NEMT)",
    "ADA accessibility and nondiscrimination requirements for regular rides.",
    "The booking portal, concierge fees, and client handoff features below are planned—not live tools."
  ]) {
    assert.ok(page.includes(phrase), phrase);
  }
  assert.match(page, /href="\/partner-portal"[^>]*>Explore the Partner Portal demos<\/a>/);
  assert.match(page, /href="\/hub"[^>]*>Back to the Hub<\/a>/);
  assert.match(page, /aria-current="page"/);
  assert.match(page, /href="\/aero-theme\.css\?v=3"/);
  assert.match(page, /src="\/aero-theme\.js\?v=2"/);
  assert.doesNotMatch(page, /ADA complaint|we are ADA compliant|NEMT is an ADA exemption/i);
  const localSection = page.indexOf('id="affiliate-local-dispatch"');
  assert.ok(localSection > page.indexOf('id="affiliate-pricing"'));
  assert.ok(localSection < page.indexOf('id="affiliate-accessibility"'));
  assert.match(page, /<strong>live dispatcher always on duty while we're accepting bookings<\/strong>/);
  assert.ok(page.includes("When NightRider begins offering transportation"));
  assert.doesNotMatch(page, /our dispatcher is on duty now|book a real ride today|24\/7 dispatch available now/i);
  const portal = read("public/partner-portal.html");
  assert.match(portal, /href="\/partner-desk-demo"/);
  assert.match(portal, /href="\/affiliate-hub\?demo=1"/);
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

test("Driver info page publishes owner standards and a usable test account entry", () => {
  const page = read("public/for-drivers.html");
  for (const phrase of [
    "For the people behind the wheel",
    "A professional ride should feel professional.",
    "The future design goal is to help good drivers join a dependable, respectable business.",
    "A real job with the flex and lifestyle of a gig app, and less of the uncertainty and headache.",
    "The design starts with professionalism, independence, and transparent expectations.",
    "The standard comes first.",
    "01 / PRIDE",
    "Take pride in your work.",
    "02 / RELIABILITY",
    "We do what we say and say what we mean.",
    "03 / RESPECT",
    "Standards go both ways.",
    "04 / TRANSPARENCY",
    "No race to the bottom.",
    "You'll never bid or fight other drivers",
    "no tricks, no carrot, no stick.",
    "Uber and Lyft can still fill empty hours.",
    "We don't want to be the next Uber.",
    "modern evolution of the classic taxi",
    "What you can explore today",
    "Take the Driver tools for a spin.",
    "view LIGHT and DARK navigation screenshots",
    "leaving out what doesn't.",
    "See the Rider and Dispatch experiences.",
    "Share feedback on the software.",
    "Before launch:",
    "Real-world testing, audits, and driver feedback are part of the plan.",
    "No transportation services are offered",
    "All trips and payments are simulated"
  ]) {
    assert.ok(page.includes(phrase), phrase);
  }
  const standards = ["01 / PRIDE", "02 / RELIABILITY", "03 / RESPECT", "04 / TRANSPARENCY"];
  const positions = standards.map(phrase => page.indexOf(phrase));
  assert.ok(positions.every(position => position >= 0));
  assert.deepEqual(positions, [...positions].sort((a,b) => a-b));
  assert.equal((page.match(/class="card drivers-principle"/g) || []).length, 4);
  assert.match(page, /href="\/account\.html\?demo=driver"[^>]*>Try the Driver demo<\/a>/);
  assert.match(page, /href="\/hub"[^>]*>Back to NightRider Hub<\/a>/);
  assert.doesNotMatch(page, /uncertaintity|overburderning|room the the next guy|\bdoesnt\b/i);
  assert.match(page, /href="\/aero-theme\.css\?v=3"/);
  assert.match(page, /src="\/aero-theme\.js\?v=2"/);
  assert.ok(page.includes('name="viewport"'));
  assert.ok(page.includes("prefers-reduced-motion") || page.includes("nightrider-motion.js"));
});

test("Hub previews destinations without repeating the sitewide demo notice", () => {
  const hub = read("public/hub.html");
  for (const phrase of [
    "browser-based booking, clear fares",
    "direct customer relationships",
    "concierge bookings, flexible referral pricing, and a real local dispatcher",
    "safer professional rides, rider trust, and a better local transportation industry",
    "follow trip updates and messages",
    "preview the LIGHT and DARK navigation designs",
    "the Dispatch map, and test conversations",
    "Partner Desk and Affiliate Hub sandboxes"
  ]) {
    assert.ok(hub.includes(phrase), phrase);
  }
  assert.doesNotMatch(hub, /No driver will come|completely absent or nonfunctional/i);
  for (const file of [
    "public/hub.html", "public/for-customers.html", "public/for-drivers.html",
    "public/for-affiliates.html", "public/ethos.html", "public/partner-portal.html",
    "public/account.html"
  ]) {
    const body = read(file).split("<body>")[1];
    assert.equal((body.match(/class="nr-demo-notice"/g) || []).length, 1, file);
    assert.equal((body.match(/No transportation services are offered\./g) || []).length, 1, file);
    assert.equal((body.match(/All trips and payments are simulated\./g) || []).length, 1, file);
    assert.doesNotMatch(body, /Only the code is live|Nothing is live except the code|may be completely absent or nonfunctional/i, file);
  }
});

test("Our Ethos sets out the modern local transportation company direction", () => {
  const page = read("public/ethos.html");
  const hub = read("public/hub.html");
  for (const phrase of [
    "The modern taxi, done properly",
    "We want to build what rideshare should have become.",
    "build a real local transportation business",
    "Professional is the standard, not an upgrade.",
    "A driver is a professional, not a disposable number.",
    "A real local company. A real human dispatcher.",
    "live dispatcher on duty whenever we're taking them",
    "Clear fares. No games.",
    "Technology should help, then get out of the way.",
    "Be part of the community, not above it.",
    "Does it make delivering a professional ride easier or safer?",
    "Does it make the rider's experience more dependable, transparent, or trustworthy?",
    "Does it make the industry better?"
  ]) {
    assert.ok(page.includes(phrase), phrase);
  }
  assert.match(hub, /<h2>Our Ethos<\/h2>\s*<p>Our principles for safer professional rides/);
  for (const link of ["/for-customers.html", "/for-drivers.html", "/for-affiliates.html", "/hub"]) {
    assert.ok(page.includes('href="' + link + '"'), link);
  }
  assert.match(page, /<ol class="ethos-questions">[\s\S]*?<\/ol>/);
  assert.equal((page.match(/class="nr-demo-notice"/g) || []).length, 1);
  assert.equal((page.match(/No transportation services are offered\./g) || []).length, 1);
  assert.equal((page.match(/All trips and payments are simulated\./g) || []).length, 1);
  assert.match(page, /When NightRider begins accepting real bookings/);
  assert.doesNotMatch(page, /book a real ride today|dispatcher is on duty now|we are ADA compliant/i);
  assert.match(page, /href="\/aero-theme\.css\?v=3"/);
  assert.match(page, /src="\/aero-theme\.js\?v=2"/);
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
    "The goal is browser-based booking on any device.",
    "Use practice trip details.",
    "Try the other sides.",
    "No transportation services are offered",
    "All trips and payments are simulated",
    "Public rider account creation is paused"
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
    assert.doesNotMatch(source, /We're growing carefully|evolving pilot|always on duty|register as a rider|no Indians/i);
  }
  for (const source of [hub, customers, welcome]) {
    assert.match(source, /[Pp]ublic rider account creation is paused|[Pp]ublic rider registration is paused/);
  }
});
