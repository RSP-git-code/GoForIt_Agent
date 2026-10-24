// Content script entry point: GoForIt.runFill() is called by the popup after
// it injects all the content files.
//
// Flow (Phase 3):
//   1. extract the fields on this page (extractor.js + adapters)
//   2. send their descriptors to the background worker, which adds the
//      profile and asks the backend agent pipeline for a FILL PLAN
//   3. apply the plan, highlight each field, show the summary panel
// If the backend is down, nothing on the page is changed; the panel says why.
//
// It NEVER submits the form (CLAUDE.md rule 1). See applier.js for how
// clicks are restricted.

(() => {
  const GF = (globalThis.GoForIt = globalThis.GoForIt || {});

  const STATUS_CLASSES = ["goforit-filled", "goforit-review", "goforit-missing"];

  function clearHighlights() {
    document.querySelectorAll(STATUS_CLASSES.map((c) => `.${c}`).join(",")).forEach((el) => {
      el.classList.remove(...STATUS_CLASSES);
      el.removeAttribute("data-goforit-reason");
    });
  }

  function highlight(el, status, reason) {
    if (!el || status === "skipped") return;
    el.classList.add(`goforit-${status}`);
    // The `title` attribute shows as a tooltip when you hover over the field.
    if (reason) {
      el.setAttribute("data-goforit-reason", reason);
      el.title = `GoForIt: ${reason}`;
    }
  }

  // Asks the backend (through background.js) for a fill plan.
  // chrome.runtime.sendMessage delivers a message to the extension's
  // background worker and resolves with whatever it replies.
  // The test harness replaces this function to call the backend directly.
  GF.requestPlan =
    GF.requestPlan ||
    function (payload) {
      return chrome.runtime.sendMessage({ type: "run-fill", ...payload });
    };

  // The saved resume and the "attach it" setting. The test harness replaces this.
  GF.getResume =
    GF.getResume ||
    async function () {
      const stored = await chrome.storage.local.get(["resume_blob", "settings"]);
      const settings = stored.settings || {};
      return { resume: stored.resume_blob || null, attach: settings.attachResume !== false };
    };

  // How long to let a site read an attached resume before filling the rest
  // (Keka, Workday and others fill fields from it). Tests set this lower.
  GF.SITE_PARSE_WAIT_MS = GF.SITE_PARSE_WAIT_MS ?? 2500;

  // Puts the saved resume into a resume upload box. Returns { status, reason, attached }.
  async function attachResume(field) {
    if (field.hasValue()) return { status: "filled", reason: "Resume already attached" };
    if (!field.input) return { status: "review", reason: "Upload your resume yourself (this upload box can't be filled automatically)" };
    const { resume, attach } = await GF.getResume();
    if (!attach) return { status: "review", reason: "Resume attaching is off (popup setting): upload it yourself" };
    if (!resume) return { status: "review", reason: "No resume saved yet: add it in Edit profile, or upload it yourself" };
    if (!GF.acceptsFile(field.input, resume.name, resume.type)) {
      return { status: "review", reason: `This box doesn't accept ${resume.name.split(".").pop().toUpperCase()} files: upload a suitable file yourself` };
    }
    let ok = false;
    try {
      ok = GF.attachFile(field.input, resume);
    } catch (err) {
      ok = false;
    }
    return ok
      ? { status: "review", reason: `Attached ${resume.name}: check the site shows it`, attached: true }
      : { status: "review", reason: "Couldn't attach your resume here: upload it yourself" };
  }

  // Applies one action from the plan. Returns { status, reason }.
  async function applyAction(field, action) {
    if (!action) return { status: "skipped", reason: "" };
    if (action.key === "resume_file" && field.hasValue()) {
      return { status: "filled", reason: "Resume already attached" };
    }
    if (action.value == null || action.status === "skipped") {
      return { status: action.status, reason: action.reason };
    }
    if (field.hasValue()) {
      // Never overwrite what's already there: you, an earlier Fill, or the
      // site's own resume reader. But if it differs from your profile, say so,
      // so a wrong value (e.g. a mis-parsed address) doesn't hide behind green.
      const current = field.currentValue ? field.currentValue() : null;
      const wanted = Array.isArray(action.value) ? action.value.join(", ") : String(action.value);
      if (current != null && GF.normalize(current) !== GF.normalize(wanted)) {
        const short = (s) => (s.length > 40 ? `${s.slice(0, 39)}…` : s);
        return { status: "review", reason: `Page already has "${short(current)}"; your profile says "${short(wanted)}". Left unchanged.` };
      }
      return { status: "filled", reason: "Already had a value, left unchanged" };
    }
    const host = field.highlightEl;
    const boxes = !host ? [] : host.matches("input, textarea, select") ? [host] : [...host.querySelectorAll("input, textarea, select")];
    if (boxes.some((b) => GF.reloadsPage(b))) {
      return { status: "review", reason: "This box makes the page reload when it changes, so GoForIt left it. Fill it yourself last." };
    }
    let result;
    try {
      if (action.mode === "tags" && Array.isArray(action.value)) {
        // A tag box: one skill at a time, each picked from the site's suggestions (see GF.applyTags).
        const input = host && host.matches("input") ? host : host && host.querySelector("input:not([type='hidden'])");
        if (!input) return { status: "review", reason: `Add these yourself, one at a time: ${action.value.join(", ")}` };
        return await GF.applyTags(input, action.value);
      }
      result = await field.apply(action.value);
    } catch (err) {
      return { status: "review", reason: `Couldn't fill automatically: ${err.message}` };
    }
    // The page may disagree with the plan (option not found, dropdown didn't
    // open). Its answer wins; otherwise keep the plan's status and reason.
    if (result.status !== "filled") return result;
    return { status: action.status, reason: action.reason };
  }

  // ---------- Summary panel ----------
  // Built inside a "shadow root": a private mini-DOM whose styles can't leak
  // into the page and the page's CSS can't break ours.

  function showPanel({ adapterName, results = [], warnings = [], error = "" }) {
    const old = document.getElementById("goforit-panel-host");
    if (old) old.remove();

    const host = document.createElement("div");
    host.id = "goforit-panel-host";
    const shadow = host.attachShadow({ mode: "open" });

    const count = (s) => results.filter((r) => r.status === s).length;
    const attention = results.filter((r) => r.status === "review" || r.status === "missing");

    shadow.innerHTML = `
      <style>
        .panel { position: fixed; right: 16px; bottom: 16px; z-index: 2147483646; width: 320px; max-height: 60vh;
                 display: flex; flex-direction: column; background: #fff; color: #1f2328; border: 1px solid #d0d7de;
                 border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.18); font: 13px/1.4 system-ui, sans-serif; }
        header { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid #d0d7de; }
        header strong { font-size: 14px; }
        header small { color: #57606a; }
        button.close { border: none; background: none; font-size: 18px; cursor: pointer; color: #57606a; }
        .counts { display: flex; gap: 10px; padding: 8px 12px; font-weight: 600; }
        .filled { color: #1a7f37; } .review { color: #9a6700; } .missing { color: #cf222e; } .skipped { color: #57606a; }
        .error { margin: 10px 12px; padding: 8px 10px; background: #ffebe9; color: #82071e; border-radius: 6px; }
        .warning { margin: 0 12px 6px; padding: 6px 10px; background: #fff8c5; color: #4d2d00; border-radius: 6px; font-size: 12px; }
        ul { list-style: none; margin: 0; padding: 0 12px; overflow-y: auto; }
        li { padding: 6px 0; border-top: 1px solid #eaeef2; cursor: pointer; }
        li:hover .label { text-decoration: underline; }
        .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .dot.review { background: #d4a72c; } .dot.missing { background: #cf222e; }
        .reason { color: #57606a; font-size: 12px; margin-left: 14px; }
        footer { padding: 8px 12px; border-top: 1px solid #d0d7de; color: #57606a; font-size: 12px; }
        button.skipped { border: none; background: none; font: inherit; font-weight: 600; padding: 0; cursor: pointer;
                         text-decoration: underline dotted; }
        ul.skipped-list { display: none; border-top: 1px dashed #d0d7de; }
        ul.skipped-list.open { display: block; }
        .dot.skipped { background: #8c959f; }
      </style>
      <div class="panel" role="dialog" aria-label="GoForIt fill summary">
        <header>
          <div><strong>GoForIt</strong> <small></small></div>
          <button class="close" title="Close">×</button>
        </header>
        <div class="body"></div>
        <ul class="attention"></ul>
        <ul class="skipped-list"></ul>
        <footer>Nothing has been submitted. Check every field, then submit the form yourself.</footer>
      </div>`;

    // Page-controlled text (labels) goes in via textContent, never innerHTML,
    // so a malicious label can't inject HTML/JS into our panel.
    shadow.querySelector("small").textContent = adapterName || "";
    const body = shadow.querySelector(".body");

    if (error) {
      const box = document.createElement("div");
      box.className = "error";
      box.textContent = `${error} Nothing on this page was changed.`;
      body.append(box);
    } else {
      const counts = document.createElement("div");
      counts.className = "counts";
      for (const s of ["filled", "review", "missing", "skipped"]) {
        // "Skipped N" is a button: it opens the list of boxes GoForIt saw but didn't fill.
        const span = document.createElement(s === "skipped" && count(s) ? "button" : "span");
        span.className = s;
        span.textContent = `${s[0].toUpperCase()}${s.slice(1)} ${count(s)}`;
        if (span.tagName === "BUTTON") {
          span.title = "Show which boxes were skipped";
          span.addEventListener("click", () => shadow.querySelector(".skipped-list").classList.toggle("open"));
        }
        counts.append(span);
      }
      body.append(counts);
    }
    for (const w of warnings) {
      const box = document.createElement("div");
      box.className = "warning";
      box.textContent = w;
      body.append(box);
    }

    const list = shadow.querySelector("ul.attention");
    for (const r of attention) {
      const li = document.createElement("li");
      const dot = document.createElement("span");
      dot.className = `dot ${r.status}`;
      const label = document.createElement("span");
      label.className = "label";
      label.textContent = r.label || "(unlabelled field)";
      const reason = document.createElement("div");
      reason.className = "reason";
      reason.textContent = r.reason;
      li.append(dot, label, reason);
      li.addEventListener("click", () => r.el && r.el.scrollIntoView({ behavior: "smooth", block: "center" }));
      list.append(li);
    }

    // The skipped boxes: what GoForIt saw on the page but didn't fill, and why. Unlabelled ones
    // show their type and the name the page's code gives them, which tells hidden widget parts
    // (a dropdown's search box, say) apart from real questions GoForIt didn't understand.
    const skippedList = shadow.querySelector("ul.skipped-list");
    for (const r of results.filter((x) => x.status === "skipped")) {
      const li = document.createElement("li");
      const dot = document.createElement("span");
      dot.className = "dot skipped";
      const label = document.createElement("span");
      label.className = "label";
      label.textContent = r.label || "(no label)";
      const reason = document.createElement("div");
      reason.className = "reason";
      const codeName = r.el ? r.el.getAttribute("name") || r.el.id || r.el.getAttribute("class") || "" : "";
      reason.textContent = [r.kind, r.reason || "GoForIt didn't recognise this box", codeName && `code name: ${codeName.slice(0, 40)}`]
        .filter(Boolean).join(" · ");
      li.append(dot, label, reason);
      li.addEventListener("click", () => {
        if (!r.el) return;
        r.el.scrollIntoView({ behavior: "smooth", block: "center" });
        r.el.style.outline = "3px dashed #8c959f"; // show where it is for a few seconds
        setTimeout(() => (r.el.style.outline = ""), 4000);
      });
      skippedList.append(li);
    }

    shadow.querySelector(".close").addEventListener("click", () => host.remove());
    document.body.append(host);
  }

  // ---------- AI drafts (optional) ----------

  // Asks the backend (through background.js) for ONE AI-drafted answer. The harness replaces this.
  GF.requestDraft =
    GF.requestDraft ||
    function (payload) {
      return chrome.runtime.sendMessage({ type: "draft", ...payload });
    };

  // The popup switches (only the ones content scripts need). The harness replaces this.
  GF.getSettings =
    GF.getSettings ||
    async function () {
      const saved = (await chrome.storage.local.get("settings")).settings || {};
      return { aiDrafts: saved.aiDrafts === true };
    };

  // Writes AI drafts into open-question boxes one at a time, updating the panel as each arrives.
  // Never touches a box you typed in: only empty boxes, or ones still holding GoForIt's own text.
  async function writeAiDrafts({ adapterName, fields, results, warnings, draftable, jobDescription, planned }) {
    const byId = new Map(fields.map((f) => [f.descriptor.id, f]));
    const valueOf = (field) => (field.currentValue ? String(field.currentValue() || "") : "");
    for (let i = 0; i < draftable.length; i++) {
      const id = draftable[i];
      const field = byId.get(id);
      const before = valueOf(field);
      if (before && before !== planned.get(id)) continue; // you've written something here: keep it
      const progress = `Writing AI drafts with your local model: ${i + 1} of ${draftable.length} (about 10-30 s each)…`;
      showPanel({ adapterName, results, warnings: [...warnings, progress] });

      let reply;
      try {
        reply = await GF.requestDraft({ field: field.descriptor, job_description: jobDescription });
      } catch (err) {
        reply = { ok: false, error: err.message };
      }
      if (!reply || !reply.ok) {
        warnings.push(`AI drafts stopped: ${(reply && reply.error) || "no reply from the backend"}`);
        break;
      }
      const action = reply.action;
      const result = results.find((r) => r.id === id);
      if (action.value && valueOf(field) === before) { // still untouched while the model was writing
        await field.apply(action.value);
        Object.assign(result, { status: "review", reason: action.reason, key: action.key });
      } else if (!action.value) {
        Object.assign(result, { reason: action.reason });
      }
      highlight(field.highlightEl, result.status, result.reason);
    }
    showPanel({ adapterName, results, warnings });
  }

  // Visible buttons like "ADD EDUCATION" or "+ Add Experience" (only their names).
  // innerText is the text as shown on screen; the Set removes duplicates.
  function addButtonNames() {
    const names = new Set();
    for (const el of document.querySelectorAll("button, [role='button'], a")) {
      const text = GF.cleanText(el.innerText || el.textContent || "");
      if (/^\+?\s*add\b/i.test(text) && text.length <= 40 && GF.isVisible(el)) names.add(`"${text}"`);
    }
    return [...names].slice(0, 3);
  }

  // If the page has an "Add Education" button but no education boxes yet, click it
  // once (GF.clickAddSection refuses anything that could submit) and wait for the
  // boxes to appear. Returns the button's name, or "" if nothing was clicked.
  GF.ADD_WAIT_MS = 1200;
  GF.REVALIDATE_WAIT_MS = 300; // let the site finish its own checks before the fallback
  GF.SECOND_PASS_WAIT_MS = 400; // let the site unlock / show fields that depend on our answers
  // ---------- If the page reloads in the middle of a Fill ----------
  // Before each step GoForIt notes what it's about to do (the box's label only: no values) in
  // chrome.storage.local. A finished Fill clears the note. If the site reloads the page halfway,
  // the note survives, so the next Fill can say where it stopped and skip that step.
  const TRACE_KEY = "goforitFillTrace";
  async function noteStep(step) {
    try {
      await chrome.storage.local.set({ [TRACE_KEY]: { host: location.host, path: location.pathname, step, at: Date.now() } });
    } catch (err) { /* no storage (test harness): no note */ }
  }
  async function lastInterruptedStep() {
    try {
      const t = (await chrome.storage.local.get(TRACE_KEY))[TRACE_KEY];
      await chrome.storage.local.remove(TRACE_KEY);
      // Only a recent Fill on this same site counts (the page's address may change on reload).
      return t && t.host === location.host && Date.now() - t.at < 10 * 60 * 1000 ? t.step : null;
    } catch (err) {
      return null;
    }
  }
  async function doneSteps() {
    try { await chrome.storage.local.remove(TRACE_KEY); } catch (err) { /* nothing noted */ }
  }

  async function openEducationSection(fields, skip) {
    const hasEducationBox = fields.some((f) => /school|universit|college|degree|institut|qualification/i.test(f.descriptor.label || ""));
    if (hasEducationBox) return "";
    for (const el of document.querySelectorAll("button, [role='button'], a")) {
      const text = GF.cleanText(el.innerText || el.textContent || "");
      if (!/^\+?\s*add\b/i.test(text) || !GF.isVisible(el)) continue;
      if (skip === `button: ${text}`) continue; // last time this click reloaded the page
      try {
        await noteStep(`button: ${text}`);
        GF.clickAddSection(el);
      } catch (err) {
        continue; // not an education button, or it could submit: leave it alone
      }
      await GF.sleep(GF.ADD_WAIT_MS);
      return text;
    }
    return "";
  }

  // ---------- Entry point ----------

  // options.quietIfEmpty: when the popup runs this in every frame of the tab
  // (forms often live in an iframe), frames with no fields stay silent.
  // One Fill at a time per page. The popup fills the main page first and then looks in every
  // frame; the main page answers that second call with "already done" instead of filling twice.
  // A double click while a Fill is running gets "busy". (A run older than 3 minutes is treated
  // as dead, e.g. the page was reloaded under it.)
  GF.runFill = async function (options = {}) {
    const state = globalThis.__goforitFillState || {};
    if (state.running && Date.now() - state.startedAt < 180000) return { adapter: "", empty: true, busy: true };
    if (state.finishedAt && Date.now() - state.finishedAt < 5000) return { adapter: "", empty: true };
    globalThis.__goforitFillState = { running: true, startedAt: Date.now() };
    try {
      return await runFillOnce(options);
    } finally {
      globalThis.__goforitFillState = { running: false, finishedAt: Date.now() };
    }
  };

  async function runFillOnce(options = {}) {
    if (GF.isCaptchaFrame()) return { adapter: "captcha", empty: true }; // never touch CAPTCHA frames
    // CLAUDE.md rule 2: no automation on LinkedIn / Indeed / Naukri (e.g. Easy Apply).
    // Only the main page shows the message; frames inside it stay quiet.
    if (/(^|\.)(linkedin\.com|indeed\.(com|co\.in)|naukri\.com)$/.test(location.hostname)) {
      if (window !== window.top) return { adapter: "job board", empty: true };
      const error = "GoForIt doesn't fill forms on LinkedIn, Indeed or Naukri. Click through to the company's own application page and use GoForIt there.";
      showPanel({ adapterName: "Job board", error });
      return { adapter: "job board", error };
    }
    clearHighlights();
    const interrupted = await lastInterruptedStep(); // e.g. "box: Name of Board" if the page reloaded last time
    let { adapter, fields } = GF.extractFields();
    const opened = window === window.top || fields.length ? await openEducationSection(fields, interrupted) : "";
    if (opened) ({ adapter, fields } = GF.extractFields()); // the new education boxes
    if (!fields.length && options.quietIfEmpty) return { adapter: adapter.name, empty: true };

    let reply;
    try {
      reply = await GF.requestPlan({
        fields: fields.map((f) => f.descriptor),
        job_description: adapter.jobDescription() || null,
      });
    } catch (err) {
      reply = { ok: false, error: `Couldn't reach the GoForIt extension background (${err.message}). Reload the extension.` };
    }
    if (!reply || !reply.ok) {
      const error = (reply && reply.error) || "Something went wrong.";
      showPanel({ adapterName: adapter.name, error });
      return { adapter: adapter.name, error };
    }

    const actions = new Map(reply.plan.actions.map((a) => [a.field_id, a]));

    // 1. Resume first: sites like Keka and Workday fill fields from it, so we
    //    let them, then fill only what's still empty (never overwriting).
    const resumeResults = new Map();
    for (const field of fields) {
      const action = actions.get(field.descriptor.id);
      if (action && action.key === "resume_file") resumeResults.set(field.descriptor.id, await attachResume(field));
    }
    if ([...resumeResults.values()].some((r) => r.attached)) await GF.sleep(GF.SITE_PARSE_WAIT_MS);

    // 2. Everything else.
    const results = [];
    for (const field of fields) {
      const d = field.descriptor;
      const action = actions.get(d.id);
      const step = `box: ${d.label || d.id}`;
      let r;
      if (step === interrupted && action && action.value != null) {
        r = { status: "review", reason: "The page reloaded while GoForIt filled this box last time, so it's left for you." };
      } else {
        if (action && action.value != null) await noteStep(step);
        r = resumeResults.get(d.id) || (await applyAction(field, action));
      }
      highlight(field.highlightEl, r.status, r.reason);
      results.push({ ...r, id: d.id, label: d.label, kind: d.kind, key: action ? action.key : null, el: field.highlightEl });
    }

    // 2b. Fields that appeared or unlocked because of our answers (on SAP, "Ethnic group" stays
    //     greyed out until "Diversity consent" is answered): look once more and fill the new ones.
    const signature = (d) => `${d.label}|${d.kind}|${d.section}`;
    const known = new Set(fields.map((f) => signature(f.descriptor)));
    await GF.sleep(GF.SECOND_PASS_WAIT_MS);
    const appeared = GF.extractFields().fields.filter((f) => !known.has(signature(f.descriptor)));
    if (appeared.length) {
      appeared.forEach((f, i) => (f.descriptor.id = `gf2-${i}`)); // ids that don't clash with the first pass
      let second = null;
      try {
        second = await GF.requestPlan({ fields: appeared.map((f) => f.descriptor), job_description: adapter.jobDescription() || null });
      } catch (err) {
        second = null;
      }
      if (second && second.ok) {
        const more = new Map(second.plan.actions.map((a) => [a.field_id, a]));
        for (const field of appeared) {
          const d = field.descriptor;
          const action = more.get(d.id);
          if (action && action.value != null) await noteStep(`box: ${d.label || d.id}`);
          const r = await applyAction(field, action);
          highlight(field.highlightEl, r.status, r.reason);
          results.push({ ...r, id: d.id, label: d.label, kind: d.kind, key: action ? action.key : null, el: field.highlightEl });
        }
      }
    }

    // 3. Fallback: boxes we filled that the site still marks as errors get re-checked.
    const filledBoxes = results
      .filter((r) => r.status !== "skipped" && r.status !== "missing" && r.el)
      .flatMap((r) => (r.el.matches("input, textarea, select") ? [r.el] : [...r.el.querySelectorAll("input, textarea, select")]));
    await GF.sleep(GF.REVALIDATE_WAIT_MS);
    GF.revalidate(filledBoxes);

    await doneSteps(); // finished without the page reloading
    const warnings = [...(reply.plan.warnings || [])];
    if (interrupted) {
      warnings.push(`Last time the page reloaded while GoForIt was on "${interrupted.replace(/^(box|button): /, "")}". `
        + "That's the site's own doing (it reloads when that changes); this time it was skipped, so fill it yourself last.");
    }
    if (GF.pageHasCaptcha()) warnings.push("This page has a CAPTCHA: solve it yourself before submitting. GoForIt never touches it.");
    // Nothing to fill, but "Add Education"-style buttons: the boxes only appear
    // after one is clicked (Oracle, Workday). GoForIt never clicks them itself.
    if (opened) warnings.push(`Clicked "${opened}" to open the education boxes. Check the entry, then save it yourself.`);
    const useful = results.some((r) => r.status !== "skipped" && r.key !== "consent");
    const addButtons = addButtonNames();
    if (!useful && addButtons.length) {
      warnings.push(`Nothing to fill yet. Click ${addButtons.join(" / ")} first, then click Fill again.`);
    }
    showPanel({ adapterName: adapter.name, results, warnings });

    // 4. Optional AI drafts for written answers ("AI drafts" switch in the popup).
    //    Not awaited: Fill returns now, and each draft appears when it's ready.
    const settings = await GF.getSettings();
    const draftable = (reply.plan.draftable || []).filter((id) => fields.some((f) => f.descriptor.id === id));
    if (settings.aiDrafts && draftable.length) {
      GF.lastDrafts = writeAiDrafts({
        adapterName: adapter.name, fields, results, warnings, draftable,
        jobDescription: adapter.jobDescription() || null,
        planned: new Map(reply.plan.actions.map((a) => [a.field_id, typeof a.value === "string" ? a.value : ""])),
      });
    }

    // Summary for the caller (popup / test harness). No profile values in here.
    return {
      adapter: adapter.name,
      trace: reply.plan.trace,
      warnings, // the panel's notes (backend warnings + CAPTCHA / "click Add first")
      counts: ["filled", "review", "missing", "skipped"].reduce((acc, s) => ({ ...acc, [s]: results.filter((r) => r.status === s).length }), {}),
      fields: results.map(({ id, label, kind, key, status, reason }) => ({ id, label, kind, key, status, reason })),
    };
  };
})();
