/* Real shared chat UI contract: explicit recipients, no surprise scrolling. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function element() {
  return {
    dataset: {}, style: { setProperty() {} }, textContent: "", value: "",
    disabled: false, scrollTop: 0, scrollHeight: 500, children: [],
    handlers: {},
    setAttribute(k, v) { this[k] = String(v); },
    addEventListener(k, cb) { this.handlers[k] = cb; },
    appendChild(c) { this.children.push(c); return c; },
    replaceChildren() { this.children.length = 0; },
    click() { if (this.handlers.click) this.handlers.click(); },
    focus() { throw Error("Chat must not steal input focus"); }
  };
}

function setup(role, accountOnly) {
  const log = element(), target = element(), field = element(), send = element();
  const status = element(), caption = element();
  const buttons = [];
  const host = {
    markup: "",
    set innerHTML(s) {
      this.markup = s;
      [...s.matchAll(/data-recipient="([^"]+)"/g)].forEach(m => {
        const b = element(); b.dataset.recipient = m[1];
        const badge = element();
        b.querySelector = () => badge;
        buttons.push(b);
      });
    },
    get innerHTML() { return this.markup; },
    querySelector(selector) {
      return ({
        ".nr-chat-log": log, ".nr-chat-select": target,
        ".nr-chat-compose input": field, ".nr-chat-send": send,
        ".nr-chat-status": status, ".nr-chat-target-label": caption
      })[selector];
    },
    querySelectorAll() { return buttons; }
  };
  let incoming = [], posts = [], gets = 0, sequence = 0;
  const sandbox = {
    window: {}, document: { getElementById() { return host; }, createElement: element, createTextNode(text) { return { textContent: text }; } },
    fetch(url, options) {
      if (!options || options.method !== "POST") {
        gets++;
        return Promise.resolve({ ok: true, json: async () => ({ messages: incoming }) });
      }
      const body = JSON.parse(options.body);
      posts.push(body);
      return Promise.resolve({
        ok: true, json: async () => ({
          message: { id: "sent" + (++sequence), at: 120 + sequence, text: body.text,
            role: role, channel: body.private || body.to_driver ? "private" : "group",
            ride_id: body.ride_id, driver: body.to_driver, audience: body.audience,
            rider_account_id: body.rider_account_id || (body.account_chat ? "r1" : undefined) }
        })
      });
    },
    Date, Math, JSON, Map, Set, Object, Array, String, Number, Promise
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  const script = fs.readFileSync(path.join(__dirname, "..", "public", "nr-chat.js"), "utf8");
  vm.runInContext(script, sandbox);
  const app = sandbox.NightRiderChat.mount({ role, host: "test-chat", accountOnly: !!accountOnly });
  return {
    app, log, target, field, send, status, caption, buttons,
    setIncoming(messages) { incoming = messages; }, posts, get gets() { return gets; }
  };
}

const tick = () => new Promise(resolve => setImmediate(() => setImmediate(resolve)));
(async () => {
  const dispatch = setup("dispatch");
  await tick();
  dispatch.app.setDrivers([{display_name: "Dana"}]);
  dispatch.app.setRides([{id: "R1", rider_name: "Riley"}]);
  dispatch.field.value = "Pickup north entrance";
  dispatch.send.click();
  await tick();
  assert.equal(dispatch.posts[0].ride_id, "R1");
  assert.equal(dispatch.posts[0].audience, "rider", "Dispatch Rider tab must reach rider only");
  dispatch.app.show("driver");
  dispatch.field.value = "Are you close?";
  dispatch.send.click();
  await tick();
  assert.equal(dispatch.posts[1].to_driver, "Dana", "Driver tab must be private to selected driver");
  dispatch.app.setRiderAccounts([{id:"r1",display_name:"Riley",enabled:true}]);
  assert.equal(dispatch.app.showRecipient("rider", "account:r1"), true,
    "Text rider tile must select the permanent rider account");
  dispatch.field.value = "You left your sunglasses";
  dispatch.send.click(); await tick();
  assert.equal(dispatch.posts[2].rider_account_id, "r1");
  assert.equal(dispatch.posts[2].ride_id, undefined);
  assert.equal(dispatch.app.showRecipient("driver", "Dana"), true,
    "Text driver tile must select the individual driver");
  dispatch.app.show("team");
  dispatch.field.value = "Stand by";
  dispatch.send.click();
  await tick();
  assert.equal(dispatch.posts[3].to_driver, undefined);
  assert.equal(dispatch.posts[3].ride_id, undefined);

  dispatch.log.scrollTop = 37;
  dispatch.setIncoming([{id:"new1", message_kind:"team", from:"Dana", role:"driver",
    channel:"group", text:"Traffic", at:300, mine:false}]);
  dispatch.app.refresh(); await tick();
  assert.equal(dispatch.log.scrollTop, 37, "Incoming message cannot auto-scroll");
  assert.ok(dispatch.buttons.find(b=>b.dataset.recipient==="team"), "Tab stays in fixed location");

  const driver = setup("driver"); await tick();
  driver.app.setRides([{id:"R1",rider_name:"Riley"}]);
  driver.app.show("dispatch");
  driver.field.value = "Need assistance";
  driver.send.click(); await tick();
  assert.equal(driver.posts[0].private, true, "Driver -> Dispatch must be private");
  driver.app.show("rider");
  driver.field.value = "I'm arriving";
  driver.send.click(); await tick();
  assert.equal(driver.posts[1].ride_id, "R1");
  assert.equal(driver.posts[1].audience, "shared", "Driver -> rider must also reach Dispatch");

  const rider = setup("rider"); await tick();
  rider.app.setRides([{id:"R1",rider_name:"Riley"}]);
  assert.equal(rider.buttons.length, 1, "Riders must not have a Dispatch-only tab");
  rider.field.value = "At the door";
  rider.send.click(); await tick();
  assert.equal(rider.posts[0].ride_id, "R1");
  assert.equal(rider.posts[0].audience, "shared");
  const account = setup("rider", true); await tick();
  assert.equal(account.buttons.length, 1, "Account chat is accessible without an active ride");
  account.field.value = "I need help finding a receipt";
  account.send.click(); await tick();
  assert.equal(account.posts[0].account_chat, true);
  assert.equal(account.posts[0].ride_id, undefined);
  assert.equal(account.app.showRecipient("driver", "Dana"), false);
  console.log("PASS: role recipient routing, fixed tabs, rider sharing, no uncommanded scrolling");
})().catch(e => { console.error(e); process.exitCode = 1; });
