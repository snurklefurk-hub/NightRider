const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const dash = String.fromCodePoint(0x2014);
const textExtensions = new Set([".html", ".js", ".cjs", ".css", ".md", ".py", ".yml", ".yaml", ".json", ".svg", ".sh", ".txt"]);

function walk(folder) {
  const files = [];
  for (const entry of fs.readdirSync(folder, {withFileTypes:true})) {
    if (entry.name === ".git" || entry.name === "node_modules" || entry.name === "__pycache__") continue;
    const file = path.join(folder, entry.name);
    if (entry.isDirectory()) files.push(...walk(file));
    else if (entry.isFile() && (textExtensions.has(path.extname(file)) || entry.name === ".gitmessage" || entry.name === "commit-msg")) files.push(file);
  }
  return files;
}

test("NightRider source and public copy do not use em dash punctuation", () => {
  const violations = [];
  for (const file of walk(root)) {
    const contents = fs.readFileSync(file, "utf8");
    const index = contents.indexOf(dash);
    if (index !== -1) {
      const line = contents.slice(0, index).split("\n").length;
      violations.push(path.relative(root, file) + ":" + line);
    }
  }
  assert.deepEqual(violations, []);
});
