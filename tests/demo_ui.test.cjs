const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const publicDir = path.join(__dirname, "..", "public");

test("every public HTML page identifies the preview even without JavaScript", () => {
  for (const name of fs.readdirSync(publicDir).filter(name => name.endsWith(".html"))) {
    const html = fs.readFileSync(path.join(publicDir, name), "utf8");
    assert.match(html, /class="nr-demo-notice"/, name);
    assert.match(html, /No transportation services are offered/, name);
    assert.match(html, /All trips and payments are simulated/, name);
  }
});

test("demo role selector submits the chosen role and opens its matching workspace", async () => {
  const html = fs.readFileSync(path.join(publicDir, "account.html"), "utf8");
  assert.doesNotMatch(html, /\/api\/auth\/register|showRegister/);
  const code = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  for (const [role, destination] of Object.entries({rider:"/rider", driver:"/driver.html", dispatch:"/dispatch.html"})) {
    const elements = {};
    const requests = [];
    const redirects = [];
    const document = {getElementById(id) {
      return elements[id] ||= {value:"", hidden:false, addEventListener(name, callback) {this[name] = callback;}};
    }};
    const context = {document, URLSearchParams,
      location: {search:"?demo=" + role + "&next=%2Frider", replace(url) {redirects.push(url);}},
      fetch(url, options) {
        if (!options || !options.body) return Promise.resolve({json: async () => ({user:null})});
        requests.push({url, body:JSON.parse(options.body)});
        return Promise.resolve({ok:true, json:async () => ({user:{role, is_demo:true}})});
      }};
    vm.runInNewContext(code, context);
    elements.form.submit({preventDefault() {}});
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(requests, [{url:"/api/auth/login",body:{username:"DEMO",password:"PASSWORD",demo_role:role}}]);
    assert.deepEqual(redirects, [destination]);
  }
});

test("navigation screenshot gallery appears for demo Drivers without requesting location", async () => {
  const html = fs.readFileSync(path.join(publicDir, "driver.html"), "utf8");
  const scripts = [...html.matchAll(/<script>\s*([\s\S]*?)<\/script>/g)].map(match => match[1]);
  for (const isDemo of [true, false]) {
    const elements = {};
    const document = {getElementById(id) {
      return elements[id] ||= {hidden:id === "driverNavigationPreview", addEventListener() {}, appendChild() {}};
    }};
    const user = {role:"driver",display_name:"Fixture Driver",is_demo:isDemo};
    const context = {document, setInterval() {},
      window:{addEventListener() {}, NightRiderChat:{mount:() => ({setRides() {},refresh() {}})}},
      navigator:{geolocation:{getCurrentPosition() {assert.fail("Screenshot gallery must not request GPS");},
                              watchPosition() {assert.fail("Screenshot gallery must not watch GPS");}}},
      fetch(url) { return Promise.resolve({ok:true,json:async () => url === "/api/auth/me" ? {user} : {rides:[]}}); }};
    for (const script of scripts) vm.runInNewContext(script, context);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(elements.driverNavigationPreview.hidden, !isDemo);
  }
  for (const mode of ["light", "dark"]) {
    const asset = "images/navigation/navigation-" + mode + ".png";
    assert.ok(html.includes('src="/' + asset + '"'));
    const png = fs.readFileSync(path.join(publicDir, asset));
    assert.equal(png.subarray(1, 4).toString(), "PNG");
    assert.equal(png.readUInt32BE(16), 1260);
    assert.equal(png.readUInt32BE(20), 2580);
  }
});
