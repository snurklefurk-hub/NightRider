const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const root = path.resolve(__dirname, "..");
const iconPath = path.join(root, "public/media/branding/nightrider-icon.webp");
const approvedHash = "fe4db1fd862d15338a1edb2a11a83442cb33477285397757f0655afecc0ea8c4";

test("NightRider's approved bridge-moon brand icon is a real optimized WebP asset", () => {
  const icon = fs.readFileSync(iconPath);
  assert.equal(icon.subarray(0, 4).toString("ascii"), "RIFF");
  assert.equal(icon.subarray(8, 12).toString("ascii"), "WEBP");
  assert.equal(crypto.createHash("sha256").update(icon).digest("hex"), approvedHash);
  assert.ok(icon.length > 4000 && icon.length < 40000, "WebP icon size is reasonable");
});

test("all public HTML pages use the approved and cache-versioned NightRider icon", () => {
  const pages = fs.readdirSync(path.join(root, "public")).filter(name => name.endsWith(".html"));
  assert.equal(pages.length, 13);
  for (const name of pages) {
    const contents = fs.readFileSync(path.join(root, "public", name), "utf8");
    assert.match(contents, /<link rel="icon" href="\/media\/branding\/nightrider-icon\.webp\?v=barb-1" type="image\/webp">/, name);
    assert.doesNotMatch(contents, /rel="icon" href="\/nightrider-mark\.svg/, name);
  }
});
