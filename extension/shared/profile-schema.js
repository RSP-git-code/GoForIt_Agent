// Profile schema (see CLAUDE.md §6) plus helpers to clean up profile objects.
//
// JS note: this file is loaded with a plain <script> tag, so the `const`s and
// functions below become globals that later scripts on the same page can use.
// (Like importing everything from a module, but without an import statement.)

const EMPTY_PROFILE = {
  personal: {
    full_name: "", first_name: "", middle_name: "", last_name: "",
    email: "", college_email: "", phone: "", alternate_phone: "",
    date_of_birth: "", gender: "", category: "",
    nationality: "", current_city: "", current_state: "", permanent_city: "", permanent_state: "",
    permanent_address: "", pincode: "",
  },
  links: { linkedin: "", github: "", portfolio: "", leetcode: "", resume_link: "", other: [] },
  education: {
    degree: {
      name: "", branch: "", specialization: "", branch_full: "", college: "", college_aliases: [],
      university: "", registration_number: "", start_year: "",
      start_month: "", graduation_year: "", graduation_month: "",
      cgpa: "", cgpa_scale: "10",
      percentage_equivalent: "", active_backlogs: 0, backlog_history: 0,
    },
    class_12: { school: "", board: "", stream: "", start_year: "", start_month: "", year: "", month: "", percentage: "", math_percentage: "", roll_number: "" },
    class_10: { school: "", board: "", start_year: "", start_month: "", year: "", month: "", percentage: "", roll_number: "" },
    diploma: null, // becomes an object shaped like DIPLOMA_TEMPLATE when filled
    gap_years: 0, gap_reason: "",
    // JEE etc. Type "NA" if you didn't take one; forms often ask "mention NA if not applicable".
    entrance_exams: { jee_main_percentile: "", jee_main_rank: "", jee_advanced_percentile: "", jee_advanced_rank: "" },
  },
  skills: { languages: [], ml_ai: [], web: [], databases: [], tools: [] },
  projects: [],
  experience: [],
  certifications: [],
  achievements: [],
  // Papers, one per line, with their status: "Title (under review at IEEE Access)".
  publications: [],
  // Professional bodies and clubs you're actually a member of: "IEEE Student Member", "Data Science Club, VIT-AP".
  memberships: [],
  languages_spoken: [],
  // Relatives working at companies, for "Do you have relatives working at X?" questions.
  // Stays on this laptop and is never given to the AI agents (it's about other people).
  relatives: [],
  // Optional answers for diversity / equal-opportunity questions. Empty = always left for you.
  // Stays on this laptop and is never given to the AI agents.
  diversity: { consent: "", ethnicity: "", disability: "", veteran: "" },
  preferences: {
    // available_from: "YYYY-MM-DD" you can join (e.g. after exams/capstone). Empty = immediately.
    notice_period: "", available_from: "", willing_to_relocate: "", preferred_locations: [],
    expected_ctc: "", has_job_offer: "", work_authorization_india: "Yes",
    requires_sponsorship: "No",
  },
  standard_answers: {
    about_me: "", why_hire_me: "", strengths: "", weaknesses: "",
  },
  resume_file: { name: "", stored: false },
};

// Months (degree start_month / graduation_month, and `month` of passing for
// class 10, class 12 and diploma) are "01".."12" (added because Workday and
// Oracle ask for month + year). The *_year fields stay the main year values.

// The spec leaves diploma as null; this is the shape we use when it's filled.
const DIPLOMA_TEMPLATE = { institute: "", board: "", branch: "", start_year: "", start_month: "", year: "", month: "", percentage: "" };

// Shape of one item in each "list of objects" section.
const LIST_ITEM_TEMPLATES = {
  projects: { title: "", summary: "", tech: [], link: "" },
  experience: { company: "", role: "", start: "", end: "", summary: "" },
  certifications: { name: "", issuer: "", date: "" },
  relatives: { company: "", relation: "", name: "", job_title: "", department: "", location: "" },
};

// JS note: there are no dicts vs objects in JS; `{}` is used for both.
// This checks for a "plain" {} object (not an array, not null).
function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// Returns a fresh deep copy so callers can't accidentally edit the template.
function emptyProfile() {
  return structuredClone(EMPTY_PROFILE);
}

// Walks `template` and pulls matching values out of `raw`, converting types.
// Unknown keys in `raw` are dropped, and missing keys get the template default.
// Used for anything that comes from storage or an imported JSON file.
function mergeWithTemplate(template, raw, path = "") {
  const out = {};
  const source = isPlainObject(raw) ? raw : {};

  for (const key of Object.keys(template)) {
    const def = template[key];
    const val = source[key];
    const fullPath = path ? `${path}.${key}` : key;

    if (fullPath === "education.diploma") {
      out[key] = isPlainObject(val) ? mergeWithTemplate(DIPLOMA_TEMPLATE, val, fullPath) : null;
    } else if (LIST_ITEM_TEMPLATES[fullPath]) {
      const itemTemplate = LIST_ITEM_TEMPLATES[fullPath];
      out[key] = Array.isArray(val) ? val.map((item) => mergeWithTemplate(itemTemplate, item, fullPath)) : [];
    } else if (Array.isArray(def)) {
      // List of strings, e.g. skills.languages. Drop blanks.
      out[key] = Array.isArray(val) ? val.map((s) => String(s).trim()).filter(Boolean) : [];
    } else if (isPlainObject(def)) {
      out[key] = mergeWithTemplate(def, val, fullPath);
    } else if (typeof def === "number") {
      const n = Number(val);
      out[key] = Number.isFinite(n) && val !== "" && val != null ? n : def;
    } else if (typeof def === "boolean") {
      out[key] = typeof val === "boolean" ? val : def;
    } else {
      out[key] = val == null ? def : String(val).trim();
    }
  }
  return out;
}

function normalizeProfile(raw) {
  return mergeWithTemplate(EMPTY_PROFILE, raw);
}

// Counts how many fields have a value, for the "profile 23/58 filled" display.
// Each list counts as one field, filled if it has at least one item.
function profileCompleteness(profile) {
  let filled = 0;
  let total = 0;

  function walk(template, value) {
    for (const key of Object.keys(template)) {
      const def = template[key];
      const val = value ? value[key] : undefined;
      if (key === "resume_file" || key === "diploma") continue; // optional / not typed in
      if (isPlainObject(def)) {
        walk(def, val);
      } else {
        total += 1;
        const hasValue = Array.isArray(def) ? Array.isArray(val) && val.length > 0 : val !== "" && val != null;
        if (hasValue) filled += 1;
      }
    }
  }

  walk(EMPTY_PROFILE, profile);
  return { filled, total };
}
