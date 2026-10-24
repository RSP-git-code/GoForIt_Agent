// Background service worker: the only part of the extension that talks to the backend.
//
// What's a service worker? A script Chrome runs in the background for the
// extension, with no page of its own. Chrome starts it when a message arrives
// and stops it when idle. Unlike content scripts, it isn't bound by the web
// page's CORS rules, and "host_permissions" lets it call 127.0.0.1:8000.
//
// Flow: content.js sends { type: "run-fill", fields, job_description } ->
// we add the saved profile -> POST /run-fill -> reply with the fill plan.

const BACKEND_URL = "http://127.0.0.1:8000";

async function runFill(message) {
  const { profile } = await chrome.storage.local.get("profile");
  if (!profile) {
    return { ok: false, error: "No profile saved yet. Open the GoForIt popup and click Edit profile first." };
  }

  // AbortController lets us give up if the backend hangs.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const resp = await fetch(`${BACKEND_URL}/run-fill`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: message.fields, job_description: message.job_description || null, profile }),
      signal: controller.signal,
    });
    if (!resp.ok) return { ok: false, error: `Backend error (HTTP ${resp.status}).` };
    return { ok: true, plan: await resp.json() };
  } catch (err) {
    return {
      ok: false,
      error: "The GoForIt backend isn't running. Start it (cd backend, then python -m app.main) and click Fill again.",
    };
  } finally {
    clearTimeout(timer);
  }
}

// Keyboard shortcut (Alt+Shift+F, set in manifest.json "commands"): same as the
// popup's "Fill this page". importScripts loads another script into this
// service worker, so goforitFillTab from shared/fill.js is available here.
// Pressing the shortcut counts as you acting on the tab, like clicking the button.
importScripts("shared/fill.js");

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command === "ask-octo" && tab) return askOctoFromShortcut(tab);
  if (command !== "fill-page" || !tab) return;
  // The results show in the panel on the page; the toolbar badge flashes a tick.
  await goforitFillTab(tab);
  chrome.action.setBadgeText({ tabId: tab.id, text: "✓" });
  setTimeout(() => chrome.action.setBadgeText({ tabId: tab.id, text: "" }), 3000);
});

// One AI-drafted answer (only when the "AI drafts" switch is on). The local model
// can take a minute or more per answer on a laptop CPU, hence the long timeout.
async function runDraft(message) {
  const { profile } = await chrome.storage.local.get("profile");
  if (!profile) return { ok: false, error: "No profile saved yet." };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300000);
  try {
    const resp = await fetch(`${BACKEND_URL}/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field: message.field, job_description: message.job_description || null, profile }),
      signal: controller.signal,
    });
    if (!resp.ok) return { ok: false, error: `Backend error (HTTP ${resp.status}).` };
    return { ok: true, ...(await resp.json()) };
  } catch (err) {
    return { ok: false, error: "The backend didn't answer (is it running?)" };
  } finally {
    clearTimeout(timer);
  }
}

// onMessage listeners must `return true` to keep the reply channel open
// while the async work finishes, then call sendResponse.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "run-fill") {
    runFill(message).then(sendResponse);
    return true;
  }
  if (message && message.type === "draft") {
    runDraft(message).then(sendResponse);
    return true;
  }
  return false;
});

// ---------- "Ask Agent Octo about this": text you selected on a page -> Octo's side panel ----------
//
// Two ways, both started by you (nothing is read until you ask):
//   1. Right-click selected text -> "Ask Agent Octo about this" (a context-menu item).
//      Chrome hands us the selected text itself; no script runs on the page.
//   2. Alt+Shift+O: the shortcut lets us (activeTab) read the page's current selection once.
// The text is put in chrome.storage.session (memory only, cleared when Chrome closes) under
// "octoPending"; the side panel picks it up when it opens, or right away if it's already open.
//
// sidePanel.open() only works directly inside your click/keypress, so it's called first,
// before any "await" (after an await, Chrome no longer counts it as your action).

// Context-menu items are created once, when the extension is installed or updated.
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "ask-octo", title: "Ask Agent Octo about this", contexts: ["selection"] });
});

function handToOcto(text, tab) {
  return chrome.storage.session.set({
    octoPending: { text: (text || "").slice(0, 20000), title: (tab && tab.title) || "", at: Date.now() },
  });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "ask-octo") return;
  chrome.sidePanel.open({ windowId: tab.windowId });
  handToOcto(info.selectionText, tab);
});

async function askOctoFromShortcut(tab) {
  chrome.sidePanel.open({ windowId: tab.windowId });
  let text = "";
  try {
    // Runs once in the page and returns the selected text (keeps line breaks, unlike the menu).
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => String(getSelection()) });
    text = (res && res.result) || "";
  } catch (err) {
    // Chrome's own pages (chrome://, the Web Store) can't be read: the panel just opens.
  }
  if (text.trim()) await handToOcto(text, tab);
}
