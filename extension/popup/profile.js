// Profile editor page. Builds the form from EMPTY_PROFILE (profile-schema.js),
// loads/saves through storage.js, and handles JSON import/export.
//
// How it works: every input gets a `data-path` attribute such as
// "education.class_12.percentage" or "projects.0.title". To save, we read all
// inputs and rebuild the profile object from those paths.

// ---------- Display hints ----------

// Nicer labels than the raw key names (the default is "date_of_birth" -> "Date of birth").
const LABELS = {
  personal: "Personal details",
  links: "Links",
  education: "Education",
  skills: "Skills",
  projects: "Projects",
  experience: "Experience",
  certifications: "Certifications",
  achievements: "Achievements",
  publications: "Publications (one per line, with status: \"Title (under review at …)\")",
  memberships: "Professional bodies / club memberships (IEEE, ACM, CSI, student clubs; certifications go under Certifications)",
  languages_spoken: "Languages spoken",
  preferences: "Job preferences",
  standard_answers: "Standard answers",
  degree: "Degree (current / highest)",
  class_12: "Class 12",
  class_10: "Class 10",
  diploma: "Diploma (only if you have one)",
  cgpa: "CGPA",
  cgpa_scale: "CGPA scale (e.g. 10 or 4)",
  percentage_equivalent: "Percentage equivalent",
  linkedin: "LinkedIn URL",
  github: "GitHub URL",
  portfolio: "Portfolio URL",
  leetcode: "LeetCode URL",
  other: "Other links",
  ml_ai: "ML / AI",
  expected_ctc: "Expected CTC",
  work_authorization_india: "Authorized to work in India?",
  has_job_offer: "Already placed / holding a job offer?",
  available_from: "Available to join from (leave empty if immediately)",
  branch_full: "Branch as you write it on forms (e.g. Computer Science with Specialization in AI and ML)",
  relatives: "Relatives working at companies (for \"Do you have relatives working at X?\" questions; leave empty if none)",
  relation: "Relation (e.g. Father, Cousin)",
  diversity: "Diversity answers (optional; only used if filled, never sent to the AI)",
  consent: "Diversity & inclusion consent (Yes / No)",
  ethnicity: "Ethnicity as you'd pick it (e.g. Asian - Indian Subcontinent, or Prefer not to say)",
  disability: "Disability (No / Yes / Prefer not to say)",
  veteran: "Veteran status, for US forms (e.g. I am not a protected veteran)",
  job_title: "Their job title",
  languages_spoken: "Languages known (add your level to fill proficiency boxes: English (Fluent), Hindi (Native), German (Basic))",
  college_email: "College / institute email",
  permanent_city: "Permanent / home town city",
  permanent_state: "Permanent / home state",
  resume_link: "Resume link (Google Drive / OneDrive, anyone with the link can view)",
  math_percentage: "Maths percentage / GPA",
  roll_number: "Roll number (board exam roll / seat number on your marksheet)",
  registration_number: "College registration / university roll number",
  entrance_exams: "Entrance exams (type NA if not taken)",
  jee_main_percentile: "JEE Main percentile",
  jee_main_rank: "JEE Main rank",
  jee_advanced_percentile: "JEE Advanced percentile",
  jee_advanced_rank: "JEE Advanced rank",
  requires_sponsorship: "Requires visa sponsorship?",
  willing_to_relocate: "Willing to relocate?",
  gap_years: "Gap years",
  year: "Year of passing",
  month: "Month of passing",
  start_year: "Start year",
  college_aliases: "Other names for your college (e.g. VIT-AP, Vellore Institute of Technology, Amaravati)",
  start_month: "Start month",
  graduation_month: "Graduation month (actual or expected)",
  about_me: "About me",
  why_hire_me: "Why should we hire you?",
  tech: "Tech used",
};

// Per-field control types. Keys are paths with list indexes removed,
// so "projects.summary" covers projects.0.summary, projects.1.summary, ...
const INPUT_TYPES = {
  "personal.email": "email",
  "personal.college_email": "email",
  "links.resume_link": "url",
  "personal.phone": "tel",
  "personal.alternate_phone": "tel",
  "personal.date_of_birth": "date",
  "preferences.available_from": "date",
  "experience.start": "month", // <input type="month"> stores "YYYY-MM"
  "experience.end": "month",
};
const MONTH_FIELDS = new Set([
  "education.degree.start_month",
  "education.degree.graduation_month",
  "education.class_12.month",
  "education.class_10.month",
  "education.diploma.month",
  "education.class_12.start_month",
  "education.class_10.start_month",
  "education.diploma.start_month",
]);
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const TEXTAREA_FIELDS = new Set([
  "personal.permanent_address",
  "education.gap_reason",
  "projects.summary",
  "experience.summary",
  "standard_answers.about_me",
  "standard_answers.why_hire_me",
  "standard_answers.strengths",
  "standard_answers.weaknesses",
]);
const YES_NO_FIELDS = new Set([
  "preferences.willing_to_relocate",
  "preferences.work_authorization_india",
  "preferences.requires_sponsorship",
  "preferences.has_job_offer",
]);
// Lists entered one item per line; every other list is comma-separated.
const LINE_LISTS = new Set(["achievements", "publications", "memberships", "links.other", "education.degree.college_aliases"]);

// Singular names for the "Add ..." buttons.
const ITEM_NAMES = { projects: "project", experience: "experience", certifications: "certification", relatives: "relative" };

// ---------- State ----------

let currentProfile = emptyProfile(); // last loaded/saved version
let dirty = false; // true when there are unsaved edits

const form = document.getElementById("profile-form");
const statusEl = document.getElementById("status");

// ---------- Small helpers ----------

function labelFor(key) {
  if (LABELS[key]) return LABELS[key];
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// "projects.2.summary" -> "projects.summary"
function genericPath(path) {
  return path.replace(/\.\d+(?=\.|$)/g, "");
}

// Shorthand for document.createElement plus setting properties.
// JS note: `...` gathers the remaining arguments into an array (like *args).
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of children) node.append(child);
  return node;
}

// Sets obj["a"]["0"]["b"] = value for path "a.0.b", creating containers as
// needed (an array when the next key is a number, otherwise an object).
function setByPath(obj, path, value) {
  const keys = path.split(".");
  let cur = obj;
  keys.forEach((key, i) => {
    if (i === keys.length - 1) {
      cur[key] = value;
      return;
    }
    if (cur[key] == null) cur[key] = /^\d+$/.test(keys[i + 1]) ? [] : {};
    cur = cur[key];
  });
}

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = `status ${kind}`;
}

function setDirty(value) {
  dirty = value;
  if (dirty) setStatus("Unsaved changes", "warn");
}

// ---------- Rendering ----------

// One labelled input/select/textarea.
function renderField(path, key, value, defaultValue) {
  const gpath = genericPath(path);
  let control;
  let hint = "";
  let wide = false;

  if (Array.isArray(defaultValue)) {
    if (LINE_LISTS.has(gpath)) {
      control = el("textarea", { value: value.join("\n") });
      control.dataset.kind = "lines";
      hint = "One per line";
      wide = true;
    } else {
      control = el("input", { type: "text", value: value.join(", ") });
      control.dataset.kind = "csv";
      hint = "Comma-separated";
    }
  } else if (MONTH_FIELDS.has(gpath)) {
    // Stored as "01".."12", shown as month names.
    control = el("select");
    control.append(el("option", { value: "", textContent: "—", selected: !value }));
    MONTH_NAMES.forEach((name, i) => {
      const mm = String(i + 1).padStart(2, "0");
      control.append(el("option", { value: mm, textContent: name, selected: mm === value }));
    });
  } else if (YES_NO_FIELDS.has(gpath)) {
    control = el("select");
    for (const opt of ["", "Yes", "No"]) {
      control.append(el("option", { value: opt, textContent: opt || "—", selected: opt === value }));
    }
  } else if (TEXTAREA_FIELDS.has(gpath)) {
    control = el("textarea", { value });
    wide = true;
  } else if (typeof defaultValue === "number") {
    control = el("input", { type: "number", min: 0, value });
  } else {
    let type = INPUT_TYPES[gpath] || "text";
    // Date/month inputs silently drop values in other formats (e.g. an
    // imported "15/08/2003" or "Jul 2024"), so show a plain text box instead.
    if (type === "date" && value && !/^\d{4}-\d{2}-\d{2}$/.test(value)) type = "text";
    if (type === "month" && value && !/^\d{4}-\d{2}$/.test(value)) type = "text";
    control = el("input", { type, value });
  }

  control.dataset.path = path;
  // Stop Chrome's own address/contact autofill from suggesting values here.
  control.setAttribute("autocomplete", "off");
  const field = el("label", { className: wide ? "field wide" : "field" }, el("span", { textContent: labelFor(key) }), control);
  if (hint) field.append(el("span", { className: "hint", textContent: hint }));
  return field;
}

// Renders the keys of a nested object: simple fields go into a grid,
// sub-objects become their own <fieldset>.
function renderObject(container, template, value, path) {
  const grid = el("div", { className: "grid" });
  container.append(grid);

  for (const key of Object.keys(template)) {
    const childPath = `${path}.${key}`;
    const def = template[key];

    if (childPath === "education.diploma") {
      const box = el("fieldset", {}, el("legend", { textContent: labelFor(key) }));
      renderObject(box, DIPLOMA_TEMPLATE, value[key] || DIPLOMA_TEMPLATE, childPath);
      container.append(box);
    } else if (isPlainObject(def)) {
      const box = el("fieldset", {}, el("legend", { textContent: labelFor(key) }));
      renderObject(box, def, value[key], childPath);
      container.append(box);
    } else {
      grid.append(renderField(childPath, key, value[key], def));
    }
  }
}

// Renders a list of objects (projects, experience, certifications) as cards
// with Remove buttons, plus an "Add" button.
function renderItemList(container, listKey, items) {
  const template = LIST_ITEM_TEMPLATES[listKey];
  const name = ITEM_NAMES[listKey];

  items.forEach((item, i) => {
    const removeBtn = el("button", { type: "button", className: "small", textContent: "Remove" });
    removeBtn.addEventListener("click", () => editList(listKey, (list) => list.splice(i, 1)));

    const legend = el("legend", {}, el("span", { className: "item-header" }, `${labelFor(name)} ${i + 1} `, removeBtn));
    const box = el("fieldset", {}, legend);
    renderObject(box, template, item, `${listKey}.${i}`);
    container.append(box);
  });

  const addBtn = el("button", { type: "button", textContent: `+ Add ${name}` });
  addBtn.addEventListener("click", () => editList(listKey, (list) => list.push(structuredClone(template))));
  container.append(addBtn);
}

// Adds/removes a list item: read the current form, change the list, redraw.
function editList(listKey, change) {
  const profile = collectProfile();
  change(profile[listKey]);
  renderForm(profile);
  setDirty(true);
}

// Builds the whole form. Remembers which sections were open and the scroll
// position so redrawing (e.g. after "Add project") doesn't jump around.
function renderForm(profile) {
  const openSections = new Set([...form.querySelectorAll("details[open]")].map((d) => d.dataset.key));
  const scrollY = window.scrollY;
  const firstRender = form.childElementCount === 0;
  form.replaceChildren();

  for (const key of Object.keys(EMPTY_PROFILE)) {
    if (key === "resume_file") continue; // handled in Phase 7
    const def = EMPTY_PROFILE[key];
    const section = el("details", { className: "section" }, el("summary", { textContent: labelFor(key) }));
    section.dataset.key = key;
    section.open = firstRender ? key === "personal" : openSections.has(key);

    if (LIST_ITEM_TEMPLATES[key]) {
      renderItemList(section, key, profile[key]);
    } else if (isPlainObject(def)) {
      renderObject(section, def, profile[key], key);
    } else {
      // Top-level list of strings (achievements, languages_spoken).
      section.append(el("div", { className: "grid" }, renderField(key, key, profile[key], def)));
    }
    form.append(section);
  }
  window.scrollTo(0, scrollY);
}

// ---------- Reading the form back ----------

function collectProfile() {
  const raw = {};
  for (const input of form.querySelectorAll("[data-path]")) {
    let value = input.value;
    if (input.dataset.kind === "csv") value = value.split(",");
    if (input.dataset.kind === "lines") value = value.split("\n");
    setByPath(raw, input.dataset.path, value);
  }

  // A diploma with every field blank means "no diploma".
  const diploma = raw.education && raw.education.diploma;
  if (diploma && Object.values(diploma).every((v) => String(v).trim() === "")) {
    raw.education.diploma = null;
  }

  raw.resume_file = currentProfile.resume_file; // not editable here
  return normalizeProfile(raw); // trims, converts numbers, fills missing keys
}

// ---------- Buttons ----------

async function onSave() {
  const profile = collectProfile();
  try {
    await saveProfile(profile);
  } catch (err) {
    setStatus(`Save failed: ${err.message}`, "err");
    return;
  }
  currentProfile = profile;
  renderForm(profile); // shows the cleaned-up values (trimmed, blanks removed)
  dirty = false;
  const { filled, total } = profileCompleteness(profile);
  setStatus(`Saved at ${new Date().toLocaleTimeString()} (${filled}/${total} fields filled)`, "ok");
}

function onExport() {
  const profile = collectProfile();
  // A Blob is an in-memory file. createObjectURL gives it a temporary URL, and
  // clicking a link with a `download` attribute saves it instead of opening it.
  const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: "goforit-profile.json" });
  link.click();
  URL.revokeObjectURL(url);
  setStatus("Exported. The file has your personal data, so keep it out of git.", "warn");
}

async function onImportFile(event) {
  const file = event.target.files[0];
  event.target.value = ""; // so picking the same file again still fires "change"
  if (!file) return;

  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch (err) {
    setStatus("Import failed: that file is not valid JSON.", "err");
    return;
  }
  // Import only fills the form. Nothing is stored until you review it and click Save.
  renderForm(normalizeProfile(parsed));
  setDirty(true);
  setStatus("Imported. Review the fields, then click Save.", "warn");
}

// ---------- Start-up ----------

document.getElementById("save-btn").addEventListener("click", onSave);
document.getElementById("export-btn").addEventListener("click", onExport);
document.getElementById("import-btn").addEventListener("click", () => document.getElementById("import-file").click());
document.getElementById("import-file").addEventListener("change", onImportFile);

// Any typing in the form marks it as having unsaved changes.
form.addEventListener("input", () => setDirty(true));

// Ctrl+S saves instead of opening the browser's "Save page" dialog.
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "s") {
    event.preventDefault();
    onSave();
  }
});

// ---------- Resume file ----------

const resumeStatusEl = document.getElementById("resume-status");
const resumeRemoveBtn = document.getElementById("resume-remove");

function showResume(resume) {
  if (resume) {
    const kb = Math.round(resume.size / 1024);
    resumeStatusEl.textContent = `${resume.name} (${kb} KB), saved ${new Date(resume.saved_at).toLocaleDateString()}. Attached to resume upload boxes when you click Fill.`;
  } else {
    resumeStatusEl.textContent = "No resume saved. Add one so GoForIt can attach it to resume upload boxes.";
  }
  resumeRemoveBtn.hidden = !resume;
}

// The saved profile records only the file name; the file itself lives in storage.js.
async function recordResumeInProfile(resume) {
  currentProfile = { ...currentProfile, resume_file: { name: resume ? resume.name : "", stored: !!resume } };
  await saveProfile(currentProfile);
}

// FileReader turns the picked file into a "data URL": "data:application/pdf;base64,JVBERi0..."
// We keep only the base64 part after the comma.
function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function onResumePicked(event) {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  if (file.size > MAX_RESUME_BYTES) {
    setStatus(`Resume too large (${Math.round(file.size / 1024 / 1024)} MB). Keep it under 5 MB.`, "err");
    return;
  }
  const resume = { name: file.name, type: file.type || "application/pdf", size: file.size, data: await readAsBase64(file), saved_at: Date.now() };
  await saveResume(resume);
  await recordResumeInProfile(resume);
  showResume(resume);
  setStatus(`Resume saved: ${file.name}`, "ok");
}

document.getElementById("resume-pick").addEventListener("click", () => document.getElementById("resume-file").click());
document.getElementById("resume-file").addEventListener("change", onResumePicked);
resumeRemoveBtn.addEventListener("click", async () => {
  await removeResume();
  await recordResumeInProfile(null);
  showResume(null);
  setStatus("Resume removed", "ok");
});

// Ask for confirmation before closing the tab with unsaved changes.
window.addEventListener("beforeunload", (event) => {
  if (dirty) event.preventDefault();
});

(async function init() {
  currentProfile = await loadProfile();
  renderForm(currentProfile);
  showResume(await loadResume());
  const { filled, total } = profileCompleteness(currentProfile);
  setStatus(`${filled}/${total} fields filled`);
})();
