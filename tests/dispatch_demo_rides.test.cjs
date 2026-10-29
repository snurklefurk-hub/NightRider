const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "../public/dispatch.html"), "utf8");

test("Chatham demo section is inside Recent rides, behind existing live tiles", () => {
  const begin = html.indexOf('id="rideBoard"');
  const real = html.indexOf('id="rows"', begin);
  const demo = html.indexOf('id="demoRideRows"', begin);
  const deleteButton = html.indexOf('id="clearRideHistory"', begin);
  assert.ok(begin > 0 && real > begin && demo > real && deleteButton > demo);
  assert.match(html, /3 incoming, 5 completed, 2 cancelled/);
  assert.match(html, /Read-only examples/);
  assert.match(html, /renderDemoRows\(d\.demo_rides \|\| \[\]\)/);
  assert.match(html, /nrDispatchChat\.setRides\(all\)/);
});

test("demo renderer creates inert details but no assign, message or cancel controls", () => {
  const start = html.indexOf("  function renderDemoRows(rides) {");
  const end = html.indexOf("  var countWindowSeconds", start);
  assert.ok(start > 0 && end > start);
  const source = html.slice(start, end);
  for (const dangerous of ["assignmentControls(", "cancel(", "openDispatchChat(", "showRecipient(", "focusRide(", "api("]) {
    assert.equal(source.includes(dangerous), false, dangerous);
  }
  class Element {
    constructor(tag) {this.tag = tag;this.children = [];this.innerHTML = "";this.hidden = false;this.className = "";}
    appendChild(element) {this.children.push(element);}
    replaceChildren() {this.children = [];}
  }
  const section = new Element("section"), rows = new Element("div");
  const elements = {demoRideSection:section, demoRideRows:rows};
  const ctx = {
    document:{createElement(tag){return new Element(tag);}},
    $:id=>elements[id],
    esc:x=>String(x).replaceAll("&","&amp;").replaceAll("<","&lt;"),
    money:x=>"$"+Number(x).toFixed(2),
    statusWord:x=>({requested:"Requested",completed:"Completed",cancelled:"Cancelled"})[x]||x,
    stageBlock:()=>null,
  };
  vm.runInNewContext(source+"\nrenderDemoRows([\n"+
    '{demo_preview:true,id:"NR-DEMO-1",status:"requested",rider_name:"Fictional A",'+
    'pickup:"2 E Bay St",dropoff:"100 US Highway 80 SW",fare:17.7,distance_mi:5},'+
    '{demo_preview:true,id:"NR-DEMO-2",status:"cancelled",rider_name:"Fictional B",'+
    'pickup:"301 Martin Luther King Jr Blvd",dropoff:"330 Bonaventure Rd",fare:0,distance_mi:4},'+
    '{demo_preview:false,id:"real",status:"requested"}]);',ctx);
  assert.equal(section.hidden,false);
  assert.equal(rows.children.length,2);
  for (const card of rows.children) {
    assert.equal(card.tag,"details");
    assert.deepEqual(card.children.map(child=>child.tag),["summary","div"]);
    assert.match(card.children[0].innerHTML,/DEMO/);
    assert.match(card.children[1].innerHTML,/no actual passenger/);
  }
  vm.runInNewContext(source+"\nrenderDemoRows([]);",ctx);
  assert.equal(section.hidden,true);
  assert.equal(rows.children.length,0);
});
