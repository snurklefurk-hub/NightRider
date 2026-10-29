const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const publicDir = path.resolve(__dirname, "../public");

function loadDemo() {
  const data = new Map();
  const window = {localStorage:{
    getItem(k) {return data.has(k) ? data.get(k) : null;},
    setItem(k,v) {data.set(k,v);}
  }};
  vm.runInNewContext(fs.readFileSync(path.join(publicDir, "partner-demo.js"), "utf8"), {window});
  return window.NightRiderPartnerDemo;
}

test("sample affiliate offers stay browser-local and never create actual rides", () => {
  const demo = loadDemo();
  const initial = demo.api("/api/partner-desk");
  assert.equal(initial.partners.length, 1);
  assert.equal(initial.offers.length, 1);
  assert.equal(initial.offers[0].status, "submitted");
  const partnerId = initial.partners[0].id;
  const offerId = initial.offers[0].id;
  const accepted = demo.api("/api/partner-desk/offers/" + offerId + "/accept", {revision:1});
  assert.equal(accepted.offer.status, "awaiting_partner");
  assert.throws(() => demo.api("/api/partner-desk/offers/" + offerId + "/accept", {revision:1}), /changed/);
  const confirmed = demo.api("/api/affiliate-hub/offers/" + offerId + "/confirm", {revision:2}, partnerId);
  assert.equal(confirmed.offer.status, "agreed_preview");
  assert.equal(Object.prototype.hasOwnProperty.call(demo.api("/api/partner-desk"), "rides"), false);
  assert.equal(demo.api("/api/affiliate-hub", undefined, partnerId).offers[0].status, "agreed_preview");
});

test("different sample partners see only their own offers and demo can reset", () => {
  const demo = loadDemo();
  const partner1 = demo.partners()[0];
  const partner2 = demo.api("/api/partner-desk/partners", {name:"Sample Another Company"}).partner;
  const offer = demo.api("/api/affiliate-hub/offers", {
    reference:"MOCK-999",pickup:"Sample Resort Entrance",dropoff:"Sample Beach Destination",
    pickup_at: new Date(Date.now()+3600000).toISOString(),passengers:2,bags:1,payout:33,authorized:true
  },partner2.id).offer;
  assert.equal(demo.api("/api/affiliate-hub", undefined, partner1.id).offers.length, 1);
  assert.equal(demo.api("/api/affiliate-hub", undefined, partner2.id).offers.length, 1);
  assert.throws(() => demo.api("/api/affiliate-hub/offers/"+offer.id+"/withdraw", {revision:1}, partner1.id),/unavailable/);
  demo.reset();
  assert.equal(demo.api("/api/partner-desk").offers.length, 1);
  assert.equal(demo.api("/api/partner-desk").partners.length, 1);
});

test("Hub removes Accounts tile and uses one-click shared demo logins", async () => {
  const html = fs.readFileSync(path.join(publicDir, "hub.html"), "utf8");
  assert.doesNotMatch(html, /<h2>Accounts<\/h2>/);
  assert.match(html, /href="\/partner-desk-demo"/);
  assert.match(html, /href="\/affiliate-hub\?demo=1"/);
  const code = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  const sent = [], next = [];
  const roles = ["rider", "driver", "dispatch"];
  const tiles = roles.map(role => ({
    dataset:{demoRole:role,demoTarget:role==="rider"?"/rider":role==="driver"?"/driver.html":"/dispatch.html"},
    addEventListener(type,callback){this[type]=callback;}
  }));
  const session = {textContent:""};
  const link = {textContent:"",href:""};
  const document = {
    querySelectorAll(selector){assert.equal(selector,"[data-demo-role]");return tiles;},
    getElementById(id){return id==="hubSession"?session:link;}
  };
  const window = {location:{assign(url){next.push(url);}}};
  const fetch = async (url,options) => {
    if (url==="/api/auth/me") return {ok:true,json:async()=>({user:null})};
    const payload = JSON.parse(options.body);
    sent.push({url,payload});
    return {ok:true,json:async()=>({user:{role:payload.demo_role,is_demo:true}})};
  };
  vm.runInNewContext(code,{window,document,fetch,JSON});
  for(const tile of tiles) {
    await tile.click({button:0,preventDefault(){},metaKey:false,ctrlKey:false,shiftKey:false,altKey:false});
  }
  assert.deepEqual(sent.map(x=>x.payload.demo_role),roles);
  assert.deepEqual(next,["/rider","/driver.html","/dispatch.html"]);
  assert.ok(sent.every(x=>x.url==="/api/auth/login" && x.payload.username==="DEMO" && x.payload.password==="PASSWORD"));
});

test("Hub preserves an authenticated real Dispatch administrator session", async () => {
  const html = fs.readFileSync(path.join(publicDir, "hub.html"), "utf8");
  const code = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  const redirects = [], calls = [];
  const tile = {
    dataset:{demoRole:"dispatch",demoTarget:"/dispatch.html"},
    addEventListener(type, callback){this[type]=callback;}
  };
  const session = {textContent:""};
  const link = {textContent:"",href:""};
  const document = {
    querySelectorAll(){return [tile];},
    getElementById(id){return id === "hubSession" ? session : link;}
  };
  const window = {location:{assign(url){redirects.push(url);}}};
  const fetch = async (url) => {
    calls.push(url);
    if(url==="/api/auth/me") {
      return {ok:true,json:async()=>({user:{role:"dispatch",is_demo:false,
        dispatch_admin:true,display_name:"Real Dispatch administrator"}})};
    }
    throw Error("Real session must never be replaced by a DEMO login");
  };
  vm.runInNewContext(code,{window,document,fetch,JSON});
  await tile.click({button:0,preventDefault(){},metaKey:false,ctrlKey:false,
    shiftKey:false,altKey:false});
  assert.deepEqual(redirects, ["/dispatch.html"]);
  assert.equal(calls.includes("/api/auth/login"), false);
});

test("Hub refuses DEMO login when current session cannot be verified", async () => {
  const html = fs.readFileSync(path.join(publicDir, "hub.html"), "utf8");
  const code = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  const redirects = [], calls = [];
  const tile = {
    dataset:{demoRole:"dispatch",demoTarget:"/dispatch.html"},
    addEventListener(type,callback){this[type]=callback;}
  };
  const session = {textContent:""};
  const document = {
    querySelectorAll(){return [tile];},
    getElementById(id){return id==="hubSession"?session:{textContent:"",href:""};}
  };
  const window = {location:{assign(url){redirects.push(url);}}};
  const fetch = async (url) => {
    calls.push(url);
    if(url==="/api/auth/me") throw Error("Session endpoint unavailable");
    throw Error("Must not post login after failed session lookup");
  };
  vm.runInNewContext(code,{window,document,fetch,JSON});
  await tile.click({button:0,preventDefault(){},metaKey:false,ctrlKey:false,
    shiftKey:false,altKey:false});
  assert.equal(calls.includes("/api/auth/login"), false);
  assert.deepEqual(redirects,[]);
  assert.match(session.textContent,/unavailable/i);
});

test("Dispatch explicitly describes archive access when user is DEMO or non-admin", () => {
  const html = fs.readFileSync(path.join(publicDir, "dispatch.html"), "utf8");
  assert.match(html,/id="clearChatHistory" hidden/);
  assert.match(html,/id="clearRideHistory" hidden/);
  assert.match(html,/Shared DEMO Dispatch login: history deletion is disabled/);
  assert.match(html,/This Dispatch account is not the designated administrator/);
  assert.match(html,/Administrator verified\. Save a local archive before deleting/);
  assert.match(html,/Unable to check administrator status/);
});
