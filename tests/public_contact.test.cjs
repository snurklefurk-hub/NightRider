const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");
const { compose, audiences, recipient } = require("../public/nr-contact.js");

test("all three public information pages have usable prefilled and accessible email forms", () => {
  const pages = [
    ["rider", "public/for-customers.html"],
    ["driver", "public/for-drivers.html"],
    ["partner", "public/for-affiliates.html"]
  ];
  assert.equal(recipient, "carson.nightrider@gmail.com");
  for (const [audience, file] of pages) {
    const html = read(file);
    assert.match(html, new RegExp('data-nr-contact="' + audience + '"'));
    assert.match(html, /href="mailto:carson\.nightrider@gmail\.com"/);
    assert.match(html, /action="mailto:carson\.nightrider@gmail\.com" method="post"/);
    assert.match(html, /name="name" type="text"[^>]*required/);
    assert.match(html, /name="email" type="email"[^>]*required/);
    assert.match(html, /name="kind" required/);
    assert.match(html, /<option value="interest" selected>Express interest<\/option>/);
    assert.match(html, /<option value="question">Ask a question<\/option>/);
    assert.match(html, /name="message" maxlength="1200"[^>]*required>/);
    assert.match(html, /Open email draft/);
    assert.match(html, /Nothing is sent until you review it and press Send/);
    assert.match(html, /nr-contact\.css\?v=1/);
    assert.match(html, /nr-contact\.js\?v=1/);
    assert.match(html, /role="status" aria-live="polite"/);
    assert.match(html, /id="contact"/);
    assert.ok(html.includes(audiences[audience].interest.split("\n")[0]), audience + " prefill");
  }
});

test("email composer uses a fixed recipient and encodes all visitor fields", () => {
  for (const audience of ["rider", "driver", "partner"]) {
    for (const kind of ["interest", "question"]) {
      const result = compose(audience, kind, "Ada Example", "ada@example.net", "I'd like to learn more & help.");
      const url = new URL(result);
      assert.equal(url.protocol, "mailto:");
      assert.equal(url.pathname, "carson.nightrider@gmail.com");
      assert.equal(url.searchParams.get("subject"), "NightRider " + audiences[audience].label + " " + (kind === "interest" ? "interest" : "question"));
      assert.match(url.searchParams.get("body"), /Name: Ada Example\nReply email: ada@example.net/);
      assert.match(url.searchParams.get("body"), /I'd like to learn more & help\./);
      assert.equal(url.searchParams.get("bcc"), null);
    }
  }
  const untrusted = compose("partner", "question", "A&B", "a@example.net", "Hi?subject=forged&bcc=other@example.net");
  const url = new URL(untrusted);
  assert.equal(url.searchParams.get("bcc"), null);
  assert.equal(url.searchParams.get("subject"), "NightRider Partner question");
  assert.match(url.searchParams.get("body"), /bcc=other@example.net/);
  assert.throws(() => compose("other", "interest", "", "", ""), /Unknown contact audience/);
  assert.throws(() => compose("rider", "other", "", "", ""), /Unknown inquiry type/);
});

test("public inquiry never claims server delivery or collects data on the website", () => {
  const source = read("public/nr-contact.js");
  assert.doesNotMatch(source, /\bfetch\(|XMLHttpRequest|localStorage|sessionStorage|sendBeacon/);
  assert.match(source, /Your email app should open with a draft/);
  assert.match(source, /Nothing was submitted through this website/);
  assert.match(source, /root\.location\.href = compose\(/);
  const hub = read("public/hub.html");
  const insurer = read("public/for-insurers.html");
  const portal = read("public/partner-portal.html");
  for (const html of [hub, insurer, portal]) {
    assert.match(html, /mailto:carson\.nightrider@gmail\.com/);
  }
  assert.match(hub, /Questions or future interest\?/);
  assert.match(portal, /href="\/for-affiliates\.html#contact"/);
  assert.match(portal, /nothing you enter is sent or saved/);
  assert.match(read("public/nr-contact.css"), /\.nr-public-contact-link:link, \.nr-public-contact-link:visited \{ color: var\(--cyan\); \}/);
  assert.match(insurer, /class="nr-public-contact-link" href="mailto:/);
  assert.match(portal, /class="nr-public-contact-link" href="\/for-affiliates\.html#contact"/);
  assert.doesNotMatch(hub, /<h2>Contact<\/h2>/);
  assert.match(read("HUB.md"), /Public contact and prelaunch inquiries/);
});
