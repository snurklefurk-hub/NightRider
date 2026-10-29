const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const read = name => fs.readFileSync(path.join(root, name), "utf8");

const questions = [
  "Does it make delivering a professional ride easier or safer?",
  "Does it make the rider's experience more dependable, transparent, or trustworthy?",
  "Does it make the industry better?"
];

test("the published NightRider gate uses the same three owner-approved questions", () => {
  for (const file of [
    "AGENTS.md", "README.md", ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/commit-value-gate.yml", ".gitmessage", ".githooks/commit-msg"
  ]) {
    const source = read(file);
    const positions = questions.map(question => source.indexOf(question));
    assert.ok(positions.every(position => position >= 0), file + ": all three questions");
    assert.deepEqual(positions, [...positions].sort((a, b) => a - b), file + ": question order");
    assert.doesNotMatch(source, /Does it improve the driver's profitability, independence, or ability to retain customers\?/);
  }
  assert.match(read(".github/workflows/commit-value-gate.yml"), /safety\|customer-trust\|industry/);
  assert.doesNotMatch(read(".github/workflows/commit-value-gate.yml"), /safety\|driver-business\|customer-trust/);
});

test("local gate accepts concrete current categories and scoped overrides only", {
  skip: process.platform === "win32"
}, () => {
  const hook = path.join(root, ".githooks", "commit-msg");
  const syntax = spawnSync("sh", ["-n", hook], { encoding: "utf8" });
  assert.equal(syntax.status, 0, syntax.stderr);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nr-gate-"));
  try {
    const messageFile = path.join(dir, "commit.txt");
    const examples = [
      ["NR-Value: safety - Keeps pickup guidance stable under weak GPS fixes.", true],
      ["NR-Value: customer-trust - Explains unexpected pickup delays to riders.", true],
      ["NR-Value: industry - Makes local transportation practices more transparent.", true],
      ["NR-Override: MAKE IT SO - Apply the owner's approved scoped experiment.", true],
      ["NR-Value: driver-business - An obsolete category is not a current test.", false],
      ["NR-Value: industry - vague", false],
      ["NR-Override: MAKE IT SO", false]
    ];
    for (const [message, valid] of examples) {
      fs.writeFileSync(messageFile, "Test commit\n\n" + message + "\n");
      const result = spawnSync("sh", [hook, messageFile], { encoding: "utf8" });
      assert.equal(result.status === 0, valid, message + ": " + result.stderr);
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
