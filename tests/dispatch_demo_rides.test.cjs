const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const html = fs.readFileSync(path.join(__dirname, "../public/dispatch.html"), "utf8");

test("Live Dispatch is before map; Previous Rides includes only terminal statuses", () => {
  const live = html.indexOf('id="liveDispatchBoard"');
  const map = html.indexOf('id="dispatchMapCard"');
  const previous = html.indexOf('id="rideBoard"');
  assert.ok(live > 0 && map > live && previous > map);
  assert.match(html, /<h2 id="liveDispatchTitle">Live Dispatch<\/h2>/);
  assert.match(html, /<h2>Previous Rides<\/h2>/);
  assert.match(html, /renderRows\(all\.filter\(function \(ride\) \{ return !isTerminalRide\(ride\); \}\), "liveRideRows"\)/);
  assert.match(html, /renderRows\(all\.filter\(isTerminalRide\)\.slice\(0, 10\), "rows"\)/);
  assert.match(html, /renderDemoRows\(examples\.filter\(isTerminalRide\)/);
  assert.match(html, /renderDemoRows\(examples\.filter\(function \(ride\) \{ return !isTerminalRide\(ride\); \}\)/);
  assert.match(html, /nrDispatchChat\.setRides\(all\)/);
  assert.match(html, /5 completed, 2 cancelled/);
  assert.match(html, /id="mapShowDemo" checked/);
});

test("only completed and cancelled are previous; every other status is live", () => {
  const start = html.indexOf('  function isTerminalRide(ride) {');
  const end = html.indexOf('  function refresh()', start);
  assert.ok(start > 0 && end > start);
  const isTerminalRide = vm.runInNewContext(
    html.slice(start, end) + "\nisTerminalRide;", {});
  for(const status of ["requested", "accepted", "to_pickup", "at_pickup",
                       "to_dropoff", "at_dropoff", "unknown_future_status"]) {
    assert.equal(isTerminalRide({status}), false, status);
  }
  for(const status of ["completed", "cancelled"]) {
    assert.equal(isTerminalRide({status}), true, status);
  }
});

test("live demo cards can select map, but never dispatch, cancel or chat", () => {
  const start = html.indexOf("  function renderDemoRows(rides, sectionId, bodyId) {");
  const end = html.indexOf("  var countWindowSeconds", start);
  assert.ok(start > 0 && end > start);
  const source = html.slice(start, end);
  for (const banned of ["assignmentControls(", "cancel(", "openDispatchChat(",
                         "showRecipient(", "/api/rides/", "api("]) {
    assert.equal(source.includes(banned), false, banned);
  }
  class Element {
    constructor(tag) {this.tag=tag;this.children=[];this.innerHTML="";this.hidden=false;this.className="";this.events={};}
    appendChild(child) {this.children.push(child);}
    replaceChildren() {this.children=[];}
    addEventListener(name, fn) {this.events[name]=fn;}
  }
  const demoLiveSection=new Element("section"), demoLiveRows=new Element("div");
  const demoRideSection=new Element("section"), demoRideRows=new Element("div");
  const elements={demoLiveSection,demoLiveRows,demoRideSection,demoRideRows};
  const focused=[];
  const ctx={
    document:{createElement(tag){return new Element(tag);}},
    $:id=>elements[id],
    esc:x=>String(x).replaceAll("&","&amp;").replaceAll("<","&lt;"),
    money:x=>"$"+Number(x).toFixed(2),
    statusWord:x=>x,
    stageBlock:()=>null,
    window:{NightRiderDispatchMap:{focusRide(id){focused.push(id);}}}
  };
  const state=vm.createContext(ctx);
  vm.runInContext(source, state);
  vm.runInContext('renderDemoRows([{demo_preview:true,id:"NR-DEMO-001",status:"to_pickup",'+
    'rider_name:"Naomi",pickup:"City Hall",dropoff:"Oglethorpe Mall",'+
    'fare:18.4,distance_mi:7.4}], "demoLiveSection", "demoLiveRows")',state);
  assert.equal(demoLiveSection.hidden,false);
  assert.equal(demoLiveRows.children.length,1);
  const card=demoLiveRows.children[0];
  assert.match(card.children[0].innerHTML,/DEMO/);
  assert.match(card.children[0].innerHTML,/to_pickup/);
  assert.equal(card.children[1].children.length,1);
  assert.equal(card.children[1].children[0].textContent,"Show DEMO on map");
  card.children[1].children[0].events.click();
  assert.deepEqual(focused,["NR-DEMO-001"]);

  vm.runInContext('renderDemoRows([{demo_preview:true,id:"NR-DEMO-004",status:"completed",'+
    'rider_name:"Adrian",pickup:"Square",dropoff:"Hotel",'+
    'fare:9.5,distance_mi:0.8}], "demoRideSection", "demoRideRows")',state);
  assert.equal(demoRideRows.children.length,1);
  assert.equal(demoRideRows.children[0].children[1].children.length,0);
  vm.runInContext('renderDemoRows([], "demoLiveSection", "demoLiveRows")',state);
  assert.equal(demoLiveSection.hidden,true);
});
