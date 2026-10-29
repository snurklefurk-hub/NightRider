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
