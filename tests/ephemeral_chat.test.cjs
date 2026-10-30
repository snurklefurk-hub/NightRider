const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");

test("all three chat workspaces keep usable chat controls and disclose volatile history", () => {
  for (const [file, host] of [
    ["public/index.html", "nrRiderChat"],
    ["public/driver.html", "nrDriverChat"],
    ["public/dispatch.html", "nrDispatchChat"]
  ]) {
    const html = read(file);
    assert.match(html, new RegExp('<script src="/nr-chat.js"></script>'));
    assert.ok(html.includes('id="' + host + '"'));
    assert.match(html, /Practice messages are temporary/);
    assert.match(html, /disappear when the server restarts/);
  }
  assert.match(read("public/index.html"), /never saved/);
  assert.match(read("public/nr-chat.js"), /fetch\("\/api\/chat\/messages"/);
  assert.match(read("CHAT-POLICY.md"), /All NightRider chat is ephemeral/);
  assert.match(read("README.md"), /No chats are persisted/);
});
