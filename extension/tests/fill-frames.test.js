// shared/fill.js with a fake Chrome: a frame that never answers (like a chat widget that never
// finishes loading) must not leave the popup on "Filling…" forever.
//   node --test extension/tests/
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Loads fill.js with short time limits, and a fake chrome.scripting that answers per target.
function loadFill(answer) {
  const src = fs.readFileSync(path.join(__dirname, "..", "shared", "fill.js"), "utf8")
    .replace(/GOFORIT_MAIN_FRAME_MS = \d+/, "GOFORIT_MAIN_FRAME_MS = 200")
    .replace(/GOFORIT_OTHER_FRAMES_MS = \d+/, "GOFORIT_OTHER_FRAMES_MS = 100");
  const calls = [];
  const chrome = {
    scripting: {
      insertCSS: async () => {},
      executeScript: (opts) => {
        calls.push(opts);
        return opts.files ? Promise.resolve([]) : answer(opts.target);
      },
    },
  };
  const ctx = vm.createContext({ chrome, setTimeout, clearTimeout, Promise });
  vm.runInContext(src, ctx);
  return { fill: ctx.goforitFillTab, calls };
}

const filledMain = [{ frameId: 0, result: { counts: { filled: 5, review: 1, missing: 0 } } }];
const never = () => new Promise(() => {});

test("a frame that never answers is skipped; the main page's result still comes back", async () => {
  const { fill, calls } = loadFill((t) => (t.frameIds ? Promise.resolve(filledMain) : never()));
  const msg = await fill({ id: 1 });
  assert.match(msg, /^Filled 5 · Review 1 · Missing 0/);
  assert.ok(calls.every((c) => c.injectImmediately), "scripts run without waiting for frames to finish loading");
});

test("a main page that never answers gives a clear message instead of Filling… forever", async () => {
  const { fill } = loadFill(() => never());
  assert.match(await fill({ id: 1 }), /didn't answer for over 2 minutes/);
});

test("a second click while a Fill is running says so", async () => {
  const { fill } = loadFill((t) => Promise.resolve(t.frameIds ? [{ frameId: 0, result: { empty: true, busy: true } }] : []));
  assert.match(await fill({ id: 1 }), /already running/);
});

test("forms inside an iframe still count, and the main page isn't counted twice", async () => {
  const { fill } = loadFill((t) => Promise.resolve(t.frameIds ? filledMain : [
    { frameId: 0, result: { empty: true } },
    { frameId: 7, result: { counts: { filled: 2, review: 0, missing: 1 } } },
  ]));
  assert.match(await fill({ id: 1 }), /^Filled 7 · Review 1 · Missing 1/);
});
