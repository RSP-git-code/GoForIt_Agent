// Runs the content scripts against every test form in headless Chrome and
// prints what was filled. Fails if any form gets submitted.
//
// Usage (from the repo root):  node extension/tests/run-harness.js
// Needs Google Chrome installed (set CHROME_PATH if it's somewhere unusual)
// and the backend running on 127.0.0.1:8000 (cd backend, python -m app.main).

const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { execFile } = require("node:child_process");

const ROOT = path.join(__dirname, "..", "..");
// Pass file names to test other pages, e.g. a saved real page:
//   node extension/tests/run-harness.js "raw/Apply to a Job _ Amazon.jobs.html"
// Phase 5 dataset: dump the field descriptions of every saved form (no backend needed):
//   node extension/tests/run-harness.js --dump ml/classifier/data/descriptors.jsonl
const DUMP = process.argv[2] === "--dump" ? process.argv[3] : null;
const CUSTOM = DUMP ? [] : process.argv.slice(2);
const FORMS = CUSTOM.length ? CUSTOM : ["google-form.html", "greenhouse.html", "lever.html", "shadow-dom.html", "sections.html"];
const BACKEND = process.env.GOFORIT_BACKEND || "http://127.0.0.1:8000";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".css": "text/css" };

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    path.join(process.env.LOCALAPPDATA || "", "Google/Chrome/Application/chrome.exe"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
  ];
  return candidates.find((p) => p && fs.existsSync(p));
}

// Tiny static file server for the repo root, bound to localhost only.
function serve() {
  const server = http.createServer((req, res) => {
    // /api/* is forwarded to the backend, so the harness page can call it
    // from the same origin (like background.js does in the real extension).
    if (req.url.startsWith("/api/")) {
      const target = new URL(req.url.slice(4), BACKEND);
      const proxy = http.request(target, { method: req.method, headers: { "Content-Type": "application/json" } }, (up) => {
        res.writeHead(up.statusCode, { "Content-Type": "application/json" });
        up.pipe(res);
      });
      proxy.on("error", () => res.writeHead(502).end());
      req.pipe(proxy);
      return;
    }
    const urlPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = path.normalize(path.join(ROOT, urlPath));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    // Saved real pages (test-forms/raw/) are snapshots: their own scripts would
    // re-render or wipe the form offline, so serve the HTML without them.
    if (urlPath.startsWith("/test-forms/raw/") && file.endsWith(".html")) {
      const html = fs.readFileSync(file, "utf8").replace(/<script\b[\s\S]*?<\/script>/gi, "");
      res.writeHead(200, { "Content-Type": "text/html" }).end(html);
      return;
    }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

function dumpDom(chrome, url, profileDir) {
  const args = ["--headless=new", "--disable-gpu", "--no-first-run", `--user-data-dir=${profileDir}`, "--virtual-time-budget=60000", "--dump-dom", url];
  return new Promise((resolve, reject) => {
    execFile(chrome, args, { maxBuffer: 20 * 1024 * 1024, timeout: 60000 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

function decodeHtml(s) {
  return s.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&#39;/g, "'").replace(/&amp;/g, "&");
}

// Every saved form: test-forms/*.html and test-forms/raw/*.html.
function allForms() {
  const dir = path.join(ROOT, "test-forms");
  const html = (d, prefix) => fs.readdirSync(d).filter((f) => f.endsWith(".html")).map((f) => prefix + f);
  const raw = path.join(dir, "raw");
  return html(dir, "").concat(fs.existsSync(raw) ? html(raw, "raw/") : []);
}

// Writes one JSON line per field: { source, form, ...descriptor }. Only labels,
// attributes and option texts; what's typed in a box is never read.
async function dumpFields(chrome) {
  const server = await serve();
  const port = server.address().port;
  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "goforit-dump-"));
  const lines = [];
  for (const form of allForms()) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=${encodeURIComponent(form)}&dump=1`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "no output" };
    if (out.error || !out.fields) {
      console.log(`${form}: ${out.error || "no fields"}`);
      continue;
    }
    const source = path.basename(form, ".html").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    for (const f of out.fields) lines.push(JSON.stringify({ source, form, ...f }));
    console.log(`${form}: ${out.fields.length} fields`);
  }
  fs.mkdirSync(path.dirname(path.resolve(DUMP)), { recursive: true });
  fs.writeFileSync(DUMP, lines.join("\n") + "\n");
  console.log(`Wrote ${lines.length} field descriptions to ${DUMP}`);
  server.close();
  fs.rmSync(profileDir, { recursive: true, force: true });
}

(async () => {
  const chrome = findChrome();
  if (!chrome) {
    console.error("Chrome not found. Set CHROME_PATH.");
    process.exit(2);
  }
  if (DUMP) {
    await dumpFields(chrome);
    return;
  }
  const healthy = await new Promise((resolve) => {
    http.get(`${BACKEND}/health`, (r) => resolve(r.statusCode === 200)).on("error", () => resolve(false));
  });
  if (!healthy) {
    console.error(`Backend not reachable at ${BACKEND}. Start it: cd backend, python -m app.main`);
    process.exit(2);
  }
  const server = await serve();
  const port = server.address().port;
  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "goforit-harness-"));
  let failed = false;

  for (const form of FORMS) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=${encodeURIComponent(form)}`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    if (out.error) {
      console.log(`\n${form}: ERROR\n${out.error}`);
      failed = true;
      continue;
    }
    if (out.result.error) {
      console.log(`
${form}: ${out.result.error}`);
      failed = true;
      continue;
    }
    if (process.env.HARNESS_DEBUG) console.log(JSON.stringify(out).slice(0, 1500));
    const c = out.result.counts;
    console.log(`\n${form}  [${out.result.adapter}]  agents: ${(out.result.trace || []).join(" > ")}`);
    console.log(`  Filled ${c.filled} · Review ${c.review} · Missing ${c.missing} · Skipped ${c.skipped}`);
    console.log(`  submitted: ${out.submitted ? "YES (FAIL)" : "no"}   panel shown: ${out.panelShown ? "yes" : "NO (FAIL)"}`);
    for (const f of out.result.fields) {
      console.log(`  ${f.status.padEnd(8)} ${String(f.key).padEnd(40)} ${f.label.slice(0, 50)}`);
    }
    if (out.submitted || !out.panelShown) failed = true;
    // The saved resume must be attached to resume upload boxes.
    const RESUME_INPUTS = { "greenhouse.html": "job_application[resume]", "lever.html": "resume" };
    if (RESUME_INPUTS[form]) {
      const attached = out.values[RESUME_INPUTS[form]] === "file:test-resume.pdf";
      console.log(`  resume attached: ${attached ? "yes" : "NO (FAIL)"}`);
      if (!attached) failed = true;
    }
  }

  // Boxes that appear only after "Add Education" (Oracle Cloud). A safe Add button
  // is clicked once and the new boxes are filled; Add Experience, Save and Next never.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=add-section.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const note = out.result && (out.result.warnings || []).find((w) => /Clicked "ADD EDUCATION"/.test(w));
    const ok = note && out.addClicked === 1 && !out.experienceClicked && !out.saved && !out.submitted && out.values.school;
    console.log(`\nadd-section.html: ${ok ? `clicked ADD EDUCATION once, filled School "${out.values.school}", nothing else clicked`
                                          : "FAIL " + JSON.stringify(out).slice(0, 400)}`);
    if (!ok) failed = true;
  }
  // The same button, but it would submit the form: refused, hint shown instead.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=add-section-submit.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const hint = out.result && (out.result.warnings || []).find((w) => /Click "Add Education"/.test(w));
    const ok = hint && !out.addClicked && !out.submitted;
    console.log(`add-section-submit.html: ${ok ? "refused the submit-type Add button, showed the hint" : "FAIL " + JSON.stringify(out).slice(0, 300)}`);
    if (!ok) failed = true;
  }

  // Workday-style validation: boxes are re-checked only when you leave them. After
  // Fill, no filled box may still be marked invalid (the red "required" error).
  if (!CUSTOM.length) {
    const run = async (extra) => {
      const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=validation.html${extra}`, profileDir);
      const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
      return m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    };
    const out = await run("&nofocus=1");
    const before = await run("&nofocus=1&nosignal=1"); // the old code under the same conditions
    const ok = out.stillInvalid === 0 && before.stillInvalid > 0 && !out.submitted;
    console.log(`
validation.html (page without focus, like Fill from the popup): ${ok
      ? `old code left ${before.stillInvalid} red boxes, now 0` : `FAIL: now ${out.stillInvalid} red, old code ${before.stillInvalid}`}`);
    if (!ok) failed = true;
  }

  // CAPTCHA warning only for a CAPTCHA you must solve, not an invisible background check.
  if (!CUSTOM.length) {
    for (const [form, expected] of [["captcha-invisible.html", false], ["captcha-visible.html", true]]) {
      const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=${form}`, profileDir);
      const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
      const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
      const warned = !!(out.result && (out.result.warnings || []).some((w) => /CAPTCHA/.test(w)));
      const ok = warned === expected && !out.submitted;
      console.log(`${form}: ${ok ? (expected ? "CAPTCHA warning shown" : "no CAPTCHA warning") : `FAIL (warned: ${warned})`}`);
      if (!ok) failed = true;
    }
  }

  // "AI drafts" switch: the open question gets an AI draft after Fill; your own answer is kept.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=ai-drafts.html&aidrafts=1`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const v = out.values || {};
    const ok = /^AI DRAFT for: Why do you want to join Acme/.test(v.why || "") && v.proud === "My own words about my project." && !out.submitted;
    console.log(`ai-drafts.html: ${ok ? "AI draft written into the empty question, your own answer kept" : "FAIL " + JSON.stringify(v).slice(0, 300)}`);
    if (!ok) failed = true;
  }

  // Boxes all labelled "Your answer", with the real question above: the question is used.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=filler-labels.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const keys = Object.fromEntries(((out.result && out.result.fields) || []).map((f) => [f.label, f.key]));
    const ok = keys["What is your Notice Period?"] === "preferences.notice_period"
      && keys["What is your expected compensation?"] === "preferences.expected_ctc"
      && keys["Your LinkedIn profile URL"] === "links.linkedin" && !Object.keys(keys).some((l) => /your answer/i.test(l));
    console.log(`filler-labels.html: ${ok ? "used the questions above the boxes, not \"Your answer\"" : "FAIL " + JSON.stringify(keys)}`);
    if (!ok) failed = true;
  }

  // Site-drawn dropdowns (SAP / Oracle / IBM style): pressed open, matching option picked.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=custom-dropdowns.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const v = out.values || {};
    const ok = v.gender === "Female" && (out.comboText || {}).auth === "Yes" && v.city === "Hyderabad" && v.country === "India"
      && v.consent === "Yes" && v.ethnic === "Asian or Asian British - Indian" && v.disability === "No"
      && !v.access && !out.saveClicked && !out.submitted;
    console.log(`custom-dropdowns.html: ${ok ? "Gender, eligibility, city, country; consent, then the unlocked ethnicity + disability (second look); accessibility box empty; Save never clicked"
      : "FAIL " + JSON.stringify({ v, combo: out.comboText, save: out.saveClicked, fields: out.result && out.result.fields }).slice(0, 900)}`);
    if (!ok) failed = true;
  }

  // Reload traps: a dropdown that posts the page back on change, and an "Add Education" <a href="">.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=reload-traps.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const v = out.values || {};
    const gender = out.result && out.result.fields.find((f) => f.key === "personal.gender");
    const ok = v.first && !v.gender && gender && gender.status === "review" && !out.addClicked && !out.submitted;
    console.log(`reload-traps.html: ${ok ? "name filled; the reloading dropdown and the empty-link Add button left alone" : "FAIL " + JSON.stringify({ v, gender, add: out.addClicked, sub: out.submitted })}`);
    if (!ok) failed = true;
  }

  // Marks table: questions are column headings, the row says which exam (HCLTech).
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=marks-table.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const v = out.values || {};
    const ok = v.s10 === "Example Public School" && v.b10 === "CBSE" && v.y10 === "2021" && v.m10 === "Percentage"
      && v.p10 === "92.0" && !v.r10 && v.s12 === "Example Junior College" && v.y12 === "2023" && v.p12 === "94.0" && !out.submitted;
    console.log(`marks-table.html: ${ok ? "10th and 12th rows filled from the column headings; school roll number left for you" : "FAIL " + JSON.stringify(v)}`);
    if (!ok) failed = true;
  }

  // Tag boxes: suggest-as-you-type box, and a Workday box that searches only on Enter (Enter allowed
  // ONLY in its search box). Never Enter in an ordinary box; never submitted.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=tag-box.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const tags = out.tags || [], tags2 = out.tags2 || [];
    const core = ["Python", "Java", "SQL", "Django", "Git", "PostgreSQL", "TensorFlow", "Keras"]; // "TensorFlow/Keras" split
    const ok = core.every((t) => tags.includes(t)) && core.every((t) => tags2.includes(t))
      && !tags.includes("C++") && !tags.includes("Python (Programming Language)")
      && !out.enterInPlainBox && !out.submitted;
    console.log(`tag-box.html: ${ok ? `suggest-as-you-type box: ${tags.length} tags; Workday Enter-to-search box: ${tags2.length} tags; Enter never in an ordinary box; nothing submitted`
      : "FAIL " + JSON.stringify({ tags, tags2, plainEnter: out.enterInPlainBox, sub: out.submitted, fields: out.result && out.result.fields }).slice(0, 1500)}`);
    if (!ok) failed = true;
  }

  // Workday education entry: years from the box ids, Field of Study picked from the site's wording.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=workday-education.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const v = out.values || {};
    const from = v["education-832--firstYearAttended-dateSectionYear-input"], to = v["education-832--lastYearAttended-dateSectionYear-input"];
    const ok = from === "2023" && to === "2027" && out.study === "Computer Science" && !out.submitted;
    console.log(`workday-education.html: ${ok ? "From/To years from the box ids; Field of Study = \"Computer Science\" from the site's list" : "FAIL " + JSON.stringify({ from, to, study: out.study, fields: (out.result && out.result.fields || []).filter((f) => /Study/.test(f.label)) })}`);
    if (!ok) failed = true;
  }

  // OTP boxes are never filled (HCLTech's "mobileOtp" used to get the phone number).
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=otp.html`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const v = out.values || {};
    const ok = v.name && v.email && v.mobile && !v.mobileOtp && !v.smsCode && !v.captchaText && !out.submitted;
    console.log(`otp.html: ${ok ? "name, email, mobile filled; OTP, one-time code and captcha left empty" : "FAIL " + JSON.stringify(v)}`);
    if (!ok) failed = true;
  }

  // A field the site already filled with something different: kept, but flagged yellow.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=greenhouse.html&prefill=1`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const last = out.result && out.result.fields.find((f) => f.key === "personal.last_name");
    const ok = last && last.status === "review" && /already has "Kadapa"/.test(last.reason) && out.values["job_application[last_name]"] === "Kadapa";
    console.log(`
prefilled different value (greenhouse.html): ${ok ? "kept and flagged yellow" : "FAIL " + JSON.stringify(last)}`);
    if (!ok) failed = true;
  }

  // Backend down: the page must be left exactly as it was, with an error in the panel.
  if (!CUSTOM.length) {
    const html = await dumpDom(chrome, `http://127.0.0.1:${port}/extension/tests/harness.html?form=greenhouse.html&offline=1`, profileDir);
    const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(html);
    const out = m ? JSON.parse(decodeHtml(m[1])) : { error: "harness produced no output" };
    const ok = !out.error && out.result && out.result.error && out.unchangedWhenOffline && out.panelShown && !out.submitted;
    console.log(`
backend offline (greenhouse.html): ${ok ? "page untouched, error shown in panel" : "FAIL " + JSON.stringify(out).slice(0, 300)}`);
    if (!ok) failed = true;
  }

  server.close();
  fs.rmSync(profileDir, { recursive: true, force: true });
  console.log(failed ? "\nFAILED" : "\nOK: all forms filled, nothing submitted");
  process.exit(failed ? 1 : 0);
})();
