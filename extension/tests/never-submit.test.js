// CLAUDE.md rule 1: GoForIt must never submit a form.
// Static check: no extension script may contain code that submits forms or
// presses Enter. (The harness run also checks the tripwire on each test form.)

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const EXTENSION_DIR = path.join(__dirname, "..");

function jsFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "tests" ? [] : jsFiles(full);
    return entry.name.endsWith(".js") ? [full] : [];
  });
}

// Strip // and /* */ comments so explanations like "we never call form.submit()" don't trip the test.
function stripComments(code) {
  return code.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

const FORBIDDEN = [
  [/\.submit\s*\(/, "calls .submit()"],
  [/\.requestSubmit\s*\(/, "calls .requestSubmit()"],
  [/new\s+(Submit)?Event\s*\(\s*["'`]submit/, "creates a submit event"],
  [/KeyboardEvent\s*\(/, "simulates key presses (Enter can submit a form)"],
  [/["'`]Enter["'`]/, "references the Enter key"],
  [/querySelector(All)?\([^)]*type=["']?submit/, "looks up submit buttons"],
];

const files = jsFiles(EXTENSION_DIR);

test("found extension scripts to check", () => {
  assert.ok(files.length >= 8, `only found ${files.length} files`);
});

// The ONE place allowed to simulate Enter (approved 2026-10-22): GF.pressEnterToSearch in applier.js,
// between the ENTER-ALLOWED markers, for a picker's search box only. Everything else is checked as before.
const ALLOWED_BLOCK = /\/\/ ENTER-ALLOWED-START[\s\S]*?\/\/ ENTER-ALLOWED-END/g;

test("Enter is simulated in exactly one guarded place", () => {
  const code = fs.readFileSync(path.join(EXTENSION_DIR, "content/applier.js"), "utf8");
  const blocks = code.match(ALLOWED_BLOCK) || [];
  assert.strictEqual(blocks.length, 1, "exactly one ENTER-ALLOWED block");
  assert.match(blocks[0], /GF\.pressEnterToSearch = function/);
  assert.match(blocks[0], /if \(!GF\.isSearchBox\(input\)\) throw/, "it must refuse anything but a search box");
  const blocksElsewhere = files.filter((f) => !f.endsWith("applier.js")).some((f) => ALLOWED_BLOCK.test(fs.readFileSync(f, "utf8")));
  assert.ok(!blocksElsewhere, "no other file may have an ENTER-ALLOWED block");
});

for (const file of files) {
  test(`never submits: ${path.relative(EXTENSION_DIR, file)}`, () => {
    const code = stripComments(fs.readFileSync(file, "utf8").replace(ALLOWED_BLOCK, ""));
    for (const [pattern, why] of FORBIDDEN) {
      assert.ok(!pattern.test(code), `${path.basename(file)} ${why}`);
    }
  });
}

test("safeClick refuses buttons and links", () => {
  const code = fs.readFileSync(path.join(EXTENSION_DIR, "content/applier.js"), "utf8");
  assert.match(code, /closest\('button, a\[href\], \[role="button"\]/);
  // Every click in the content scripts must go through GF.safeClick.
  for (const file of files.filter((f) => f.includes(`${path.sep}content${path.sep}`))) {
    const clicks = stripComments(fs.readFileSync(file, "utf8")).match(/[\w\])]\.click\(\)/g) || [];
    // applier.js: the one inside safeClick and the one inside clickAddSection.
    const allowed = path.basename(file) === "applier.js" ? 2 : 0;
    assert.ok(clicks.length <= allowed, `${path.basename(file)} calls .click() directly`);
  }
});

test("clickAddSection only clicks Add Education-type buttons, never submit buttons", () => {
  const code = fs.readFileSync(path.join(EXTENSION_DIR, "content/applier.js"), "utf8");
  assert.match(code, /const ADD_SECTION = \/\^\\\+\?\\s\*add\\s\+/);
  assert.match(code, /\(el\.getAttribute\("type"\) \|\| "submit"\)\.toLowerCase\(\) === "submit"/);
  assert.match(code, /input\[type="submit"\]/);
});

test("CAPTCHA fields are excluded and CAPTCHA frames are skipped", () => {
  const generic = fs.readFileSync(path.join(EXTENSION_DIR, "content/adapters/generic.js"), "utf8");
  assert.match(generic, /if \(GF\.isCaptcha\(el\)\) return false;/);
  const content = fs.readFileSync(path.join(EXTENSION_DIR, "content/content.js"), "utf8");
  assert.match(content, /if \(GF\.isCaptchaFrame\(\)\) return/);
});

test("never fills on LinkedIn, Indeed or Naukri (rule 2)", () => {
  const content = fs.readFileSync(path.join(EXTENSION_DIR, "content/content.js"), "utf8");
  assert.match(content, /linkedin\\\.com\|indeed\\\.\(com\|co\\\.in\)\|naukri\\\.com/);
});
