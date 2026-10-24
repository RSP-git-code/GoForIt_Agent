// Wrapper around chrome.storage.local for the profile.
// Needs profile-schema.js to be loaded first (uses normalizeProfile).
//
// chrome.storage.local is a key-value store kept on disk by Chrome, private
// to this extension. It survives browser restarts and is never synced
// anywhere (unlike chrome.storage.sync).

const PROFILE_KEY = "profile";

async function loadProfile() {
  // get() returns an object like { profile: {...} }, or {} if nothing is saved yet.
  const result = await chrome.storage.local.get(PROFILE_KEY);
  return normalizeProfile(result[PROFILE_KEY]);
}

async function saveProfile(profile) {
  // `[PROFILE_KEY]: ...` uses the variable's value ("profile") as the key.
  await chrome.storage.local.set({ [PROFILE_KEY]: normalizeProfile(profile) });
}

// ---------- Resume file ----------
// The PDF is stored separately from the profile (as base64 text), so exporting
// the profile as JSON doesn't include it. chrome.storage.local allows ~10 MB.
const RESUME_KEY = "resume_blob";
const MAX_RESUME_BYTES = 5 * 1024 * 1024;

// Returns { name, type, size, data (base64), saved_at } or null.
async function loadResume() {
  const result = await chrome.storage.local.get(RESUME_KEY);
  return result[RESUME_KEY] || null;
}

async function saveResume(resume) {
  await chrome.storage.local.set({ [RESUME_KEY]: resume });
}

async function removeResume() {
  await chrome.storage.local.remove(RESUME_KEY);
}

// ---------- Settings ----------
const SETTINGS_KEY = "settings";

// attachResume: put the saved resume into resume upload boxes on Fill (default on).
// aiDrafts: after Fill, have the local AI draft written answers one by one (default off).
async function loadSettings() {
  const saved = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY] || {};
  return { attachResume: saved.attachResume !== false, aiDrafts: saved.aiDrafts === true };
}

// Saves only the settings you pass, keeping the others ({ ...a, ...b } merges two objects).
async function saveSettings(changes) {
  const saved = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY] || {};
  await chrome.storage.local.set({ [SETTINGS_KEY]: { ...saved, ...changes } });
}
