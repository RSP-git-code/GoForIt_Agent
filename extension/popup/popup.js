// Popup script: runs every time the popup opens (the popup is a tiny web page
// that is created on open and destroyed on close).

const BACKEND_URL = "http://127.0.0.1:8000";

// `async` functions let us use `await`, which pauses until a Promise
// (JS's version of a future/result-later) resolves. Similar to Python's async/await.
async function checkBackend() {
  const statusEl = document.getElementById("backend-status");
  statusEl.textContent = "checking…";
  statusEl.className = "";

  try {
    // fetch() makes an HTTP request. The extension is allowed to call
    // 127.0.0.1:8000 because of "host_permissions" in manifest.json.
    const resp = await fetch(`${BACKEND_URL}/health`);
    const data = await resp.json();
    statusEl.textContent = `online (v${data.version})`;
    statusEl.className = "ok";
  } catch (err) {
    // fetch throws if the server isn't running at all.
    statusEl.textContent = "offline — start it with: python -m app.main";
    statusEl.className = "down";
  }
}

async function showProfileStatus() {
  const profile = await loadProfile(); // from shared/storage.js
  const { filled, total } = profileCompleteness(profile);
  document.getElementById("profile-status").textContent = `${filled}/${total} fields filled`;
}

async function showResumeStatus() {
  const resume = await loadResume(); // from shared/storage.js
  document.getElementById("resume-status").textContent = resume ? resume.name : "none saved (add it in Edit profile)";
  const toggle = document.getElementById("attach-resume");
  toggle.checked = (await loadSettings()).attachResume;
  // Many sites upload the file to their server as soon as it's attached,
  // so this switch lets you keep GoForIt from attaching it.
  toggle.addEventListener("change", () => saveSettings({ attachResume: toggle.checked }));
  // Local-AI drafts for open questions ("Why do you want to join us?"), written after Fill.
  const ai = document.getElementById("ai-drafts");
  ai.checked = (await loadSettings()).aiDrafts;
  ai.addEventListener("change", () => saveSettings({ aiDrafts: ai.checked }));
}

// Run the check when the button is clicked, and once right away.
document.getElementById("recheck").addEventListener("click", checkBackend);
checkBackend();
showProfileStatus();
showResumeStatus();

// "Fill this page": the actual work is in shared/fill.js (also used by the
// Alt+Shift+F shortcut in background.js).
async function fillPage() {
  const statusEl = document.getElementById("fill-status");
  statusEl.textContent = "Filling…";
  // The tab you're looking at. Thanks to the "activeTab" permission, the
  // extension may script this one tab only, and only because you clicked.
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  statusEl.textContent = await goforitFillTab(tab);
}

document.getElementById("fill-page").addEventListener("click", fillPage);

// Opens the full-tab profile editor ("options_page" in manifest.json).
document.getElementById("edit-profile").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

// Opens Agent Octo in Chrome's side panel (a panel beside the page that stays open
// while you read the job). Chrome only allows sidePanel.open() *immediately* inside a
// click: waiting for anything first (even asking which window we're in) makes Chrome
// refuse. So the window id is looked up as soon as the popup opens, before the click.
let currentWindowId = null;
chrome.windows.getCurrent().then((win) => (currentWindowId = win.id));
document.getElementById("ask-octo").addEventListener("click", () => {
  chrome.sidePanel
    .open({ windowId: currentWindowId ?? chrome.windows.WINDOW_ID_CURRENT })
    .then(() => window.close()) // close the popup; Octo stays open on the side
    .catch((err) => {
      document.getElementById("fill-status").textContent = `Couldn't open Octo: ${err.message}`;
    });
});
