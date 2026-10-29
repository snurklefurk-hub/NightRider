const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const publicDir = path.resolve(__dirname, "../public");
const read = name => fs.readFileSync(path.join(publicDir, name), "utf8");

function sampleAdapter() {
  const storage = new Map();
  const window = {localStorage: {
    getItem(key) {return storage.has(key) ? storage.get(key) : null;},
    setItem(key, value) {storage.set(key, value);}
  }};
  vm.runInNewContext(read("partner-demo.js"), {window});
  return window.NightRiderPartnerDemo;
}

function simulateDispatch(user, demo) {
  const calls = [];
  const elements = {};
  const listeners = {};
  const element = tag => ({
    tag, children: [], textContent: "", hidden: true, handlers: {},
    appendChild(child) {this.children.push(child); return child;},
    replaceChildren() {this.children = [];},
    addEventListener(type, callback) {this.handlers[type] = callback;}
  });
  const document = {
    hidden: false,
    getElementById(id) {return elements[id] ||= element(id);},
    createElement: element,
    addEventListener(type, callback) {listeners[type] = callback;}
  };
  const window = {
    NightRiderPartnerDemo: demo,
    confirm() {return true;},
    addEventListener(type, callback) {listeners[type] = callback;}
  };
  const fetch = async (url) => {
    calls.push(url);
    assert.equal(url, "/api/auth/me", "sample UI must never send offer mutations to the server");
    return {ok:true, json:async () => ({user})};
  };
  vm.runInNewContext(read("dispatch-partner-demo.js"), {window,document,fetch,encodeURIComponent,Number});
  return {elements, listeners, calls, document};
}

test("Demo Dispatch manages sample Partner Hub offers without posting real partner data", async () => {
  const demo = sampleAdapter();
  const simulated = simulateDispatch({role:"dispatch",is_demo:true},demo);
  await new Promise(resolve=>setImmediate(resolve));
  const {elements, calls} = simulated;
  assert.equal(elements.dispatchSampleOffers.hidden,false);
  assert.equal(elements.deskAccessNotice.hidden,true);
  assert.equal(elements.deskMessage.hidden,true);
  assert.deepEqual(calls, ["/api/auth/me"]);
  const offerId = demo.api("/api/partner-desk").offers[0].id;
  const list = elements.dispatchDemoOfferList;
  assert.equal(list.children.length,1);
  assert.match(list.children[0].children[0].textContent,/SAMPLE-101/);
  const controls = list.children[0].children.at(-1);
  const accept = controls.children[0];
  assert.equal(accept.textContent,"Accept sample terms");
  accept.handlers.click();
  assert.equal(demo.api("/api/partner-desk").offers[0].status,"awaiting_partner");
  assert.deepEqual(calls, ["/api/auth/me"]);
  const offer = demo.api("/api/partner-desk").offers[0];
  demo.api("/api/affiliate-hub/offers/"+offerId+"/confirm",{revision:offer.revision},offer.partner_id);
  elements.dispatchDemoOfferRefresh.handlers.click();
  assert.equal(demo.api("/api/partner-desk").offers[0].status,"agreed_preview");
  assert.match(list.children[0].children[2].textContent,/agreed preview/);
  assert.equal(list.children[0].children.some(child=>child.children.some(x=>x.textContent==="Accept sample terms")),false);
});

test("Non-demo Dispatch does not see browser-only sample offer controls", async () => {
  const simulated = simulateDispatch({role:"dispatch",is_demo:false,dispatch_admin:true},sampleAdapter());
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(simulated.elements.dispatchSampleOffers.hidden,true);
  assert.deepEqual(simulated.calls,["/api/auth/me"]);
});
