const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const crypto = require("node:crypto");

const html = fs.readFileSync(path.resolve(__dirname, "../public/dispatch.html"), "utf8");
const start = html.indexOf("  async function archiveThenDeleteHistory(");
const end = html.indexOf("  function refreshDriverAccounts()", start);
assert.ok(start > 0 && end > start, "Archive/delete function and button wiring must exist");
const code = html.slice(start, end);

async function clickScenario(settings = {}) {
  const calls = [];
  const buttons = {};
  const messages = {};
  for (const key of ["clearChatHistory", "clearRideHistory"]) {
    buttons[key] = {disabled: false, addEventListener(event, cb) {this[event] = cb;}};
  }
  messages.clearChatMsg = {textContent: ""};
  messages.clearRidesMsg = {textContent: ""};
  const archiveText = '{"demo":"history"}\n';
  const sum = crypto.createHash("sha256").update(archiveText).digest("hex");
  const file = {
    async createWritable() {
      calls.push("createWritable");
      return {
        async write(blob) {calls.push("write"); if (settings.failWrite) throw Error("disk full"); assert.equal(await blob.text(), archiveText);},
        async close() {calls.push("close"); if (settings.failClose) throw Error("disk full");},
        async abort() {calls.push("abort");}
      };
    }
  };
  const window = {
    crypto: {subtle: {async digest(_algorithm, bytes) {
      calls.push("digest");
      const digest = crypto.createHash("sha256").update(Buffer.from(bytes)).digest();
      return digest.buffer.slice(digest.byteOffset, digest.byteOffset + digest.byteLength);
    }}},
    showSaveFilePicker: async () => {
      calls.push("picker");
      if (settings.abortPicker) throw Object.assign(new Error("cancelled"), {name:"AbortError"});
      return file;
    },
    confirm() {calls.push("confirm"); return settings.confirm !== false;},
    location: {reload() {calls.push("reload");}}
  };
  if (settings.noPicker) delete window.showSaveFilePicker;
  async function api(url, options) {
    calls.push(options && options.method === "POST" ? "POST" : "GET");
    if (options && options.method === "POST") {
      assert.equal(url, "/api/dispatch/history-deletion");
      const sent = JSON.parse(options.body);
      assert.equal(sent.kind, "chat");
      assert.equal(sent.sha256, sum);
      return {ok:true, json:async () => ({ok:true})};
    }
    assert.equal(url, "/api/dispatch/history-archive?kind=chat");
    return {ok:true, json:async () => ({content:archiveText,sha256:sum,token:"sample-grant"})};
  }
  const $ = (id) => buttons[id] || messages[id];
  vm.runInNewContext(code, {$, window, TextEncoder, Blob, Date, JSON, Uint8Array,
    canDeleteAccounts:settings.isAdmin !== false, api, encodeURIComponent});
  await buttons.clearChatHistory.click.call(buttons.clearChatHistory);
  // The event listener launches an async task without returning its promise.
  for (let i=0;i<4;i++) await new Promise(resolve => setImmediate(resolve));
  return {calls, message:messages.clearChatMsg.textContent};
}

test("history controls exist inside both Dispatch panels", () => {
  assert.match(html, /id="chatCard"[\s\S]*?id="clearChatHistory" hidden/);
  assert.match(html, /id="rideBoard"[\s\S]*?id="clearRideHistory" hidden/);
  assert.match(html, /clearChatHistory"\)\.hidden = !canDeleteAccounts/);
  assert.match(html, /clearRideHistory"\)\.hidden = !canDeleteAccounts/);
});

test("no admin permission, no save API, or cancel never contacts the server", async () => {
  for (const settings of [{isAdmin:false},{noPicker:true},{abortPicker:true}]) {
    const result = await clickScenario(settings);
    assert.equal(result.calls.includes("POST"), false);
    assert.equal(result.calls.includes("GET"), false);
    assert.match(result.message, /blocked|cancelled|required/i);
  }
});

test("failed local file writes block any deletion", async () => {
  const result = await clickScenario({failWrite:true});
  assert.ok(result.calls.includes("GET"));
  assert.ok(result.calls.includes("abort"));
  assert.equal(result.calls.includes("POST"), false);
  assert.match(result.message, /blocked/i);
});

test("declining deletion after successful export leaves history intact", async () => {
  const result = await clickScenario({confirm:false});
  assert.ok(result.calls.indexOf("close") < result.calls.indexOf("confirm"));
  assert.equal(result.calls.includes("POST"), false);
});

test("only a successfully closed and confirmed export can authorize deletion", async () => {
  const result = await clickScenario();
  assert.deepEqual(result.calls, ["picker", "GET", "digest", "createWritable",
    "write", "close", "confirm", "POST", "reload"]);
});
