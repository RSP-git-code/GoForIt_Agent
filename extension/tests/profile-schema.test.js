// Run with: node --test "extension/tests/*.test.js"
// Uses Node's built-in test runner, so nothing to install.
//
// profile-schema.js is a plain browser script (no exports), so we run it inside
// a sandbox with `vm` and read its globals from there.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const code = fs.readFileSync(path.join(__dirname, "../shared/profile-schema.js"), "utf8");
const sandbox = { structuredClone };
vm.createContext(sandbox);
vm.runInContext(`${code}; this.api = { EMPTY_PROFILE, normalizeProfile, profileCompleteness, emptyProfile };`, sandbox);
const { EMPTY_PROFILE, normalizeProfile, profileCompleteness, emptyProfile } = sandbox.api;

// Objects created inside the sandbox have different prototypes, so compare via JSON.
const plain = (obj) => JSON.parse(JSON.stringify(obj));

test("normalizing nothing gives the empty profile", () => {
  assert.deepStrictEqual(plain(normalizeProfile(undefined)), plain(EMPTY_PROFILE));
  assert.deepStrictEqual(plain(normalizeProfile("garbage")), plain(EMPTY_PROFILE));
});

test("emptyProfile returns an independent copy", () => {
  const p = emptyProfile();
  p.personal.email = "changed";
  assert.strictEqual(EMPTY_PROFILE.personal.email, "");
});

test("keeps known values, trims strings, drops unknown keys", () => {
  const p = normalizeProfile({
    personal: { first_name: "  Asha ", hacker_field: "x" },
    unknown_section: { a: 1 },
  });
  assert.strictEqual(p.personal.first_name, "Asha");
  assert.strictEqual(p.personal.hacker_field, undefined);
  assert.strictEqual(p.unknown_section, undefined);
});

test("converts numbers and keeps defaults for bad numbers", () => {
  const p = normalizeProfile({ education: { degree: { active_backlogs: "2", backlog_history: "abc" }, gap_years: "" } });
  assert.strictEqual(p.education.degree.active_backlogs, 2);
  assert.strictEqual(p.education.degree.backlog_history, 0);
  assert.strictEqual(p.education.gap_years, 0);
  assert.strictEqual(p.education.degree.cgpa_scale, "10");
});

test("string lists drop blanks", () => {
  const p = normalizeProfile({ skills: { languages: ["Python", " ", " JavaScript "] } });
  assert.deepStrictEqual(plain(p.skills.languages), ["Python", "JavaScript"]);
});

test("object lists are normalized item by item", () => {
  const p = normalizeProfile({ projects: [{ title: "GoForIt", tech: ["Python", ""], extra: 1 }] });
  assert.deepStrictEqual(plain(p.projects), [{ title: "GoForIt", summary: "", tech: ["Python"], link: "" }]);
});

test("diploma stays null unless it's an object", () => {
  assert.strictEqual(normalizeProfile({}).education.diploma, null);
  const p = normalizeProfile({ education: { diploma: { branch: "Mechanical" } } });
  assert.strictEqual(p.education.diploma.branch, "Mechanical");
  assert.strictEqual(p.education.diploma.percentage, "");
});

test("completeness counts filled fields", () => {
  const empty = profileCompleteness(normalizeProfile({}));
  // These defaults come pre-filled in the schema: cgpa_scale "10", work auth "Yes", sponsorship "No".
  // active_backlogs, backlog_history and gap_years default to 0, which also counts as filled.
  assert.strictEqual(empty.filled, 6);
  const some = profileCompleteness(normalizeProfile({ personal: { email: "a@b.c" }, skills: { languages: ["Python"] } }));
  assert.strictEqual(some.filled, 8);
  assert.strictEqual(some.total, empty.total);
});
