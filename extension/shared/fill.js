// Runs a Fill on a tab. Used by the popup's "Fill this page" button
// (popup/popup.js) and by the Alt+Shift+F keyboard shortcut (background.js),
// so both behave exactly the same.
//
// Chrome only lets the extension script a tab you acted on yourself (the
// "activeTab" permission): clicking the popup button or pressing the shortcut
// both count. Nothing runs on a page until you do one of them.

// Content files injected into the page. Order matters: later files use
// functions defined by earlier ones.
const GOFORIT_CONTENT_FILES = [
  "content/extractor.js",
  "content/applier.js",
  "content/adapters/generic.js",
  "content/adapters/google-forms.js",
  "content/adapters/greenhouse.js",
  "content/adapters/lever.js",
  "content/content.js",
];

// Time limits. A Fill normally takes seconds; these only stop an endless "Filling…".
const GOFORIT_MAIN_FRAME_MS = 150000; // the main page (the backend itself may take up to 2 minutes)
const GOFORIT_OTHER_FRAMES_MS = 20000; // embedded frames (forms in an iframe; chat widgets, ads, trackers)

// Promise.race settles with whichever finishes first: the work, or a timer that gives up.
function goforitWithTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("timeout")), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

// Injects the content files into the target frames and runs the fill there.
// injectImmediately: run now, instead of waiting until the frame has "finished loading".
// Some frames never finish (a chat widget that keeps a connection open), and without
// this Chrome would wait for them forever.
async function goforitRunIn(target) {
  await chrome.scripting.insertCSS({ target, files: ["content/panel.css"] }).catch(() => {});
  await chrome.scripting.executeScript({ target, files: GOFORIT_CONTENT_FILES, injectImmediately: true });
  // executeScript waits for the async function and passes back its return value.
  return chrome.scripting.executeScript({
    target, injectImmediately: true, func: () => globalThis.GoForIt.runFill({ quietIfEmpty: true }),
  });
}

// Fills the tab and returns a one-line summary for the popup.
async function goforitFillTab(tab) {
  let frames = [];
  // 1. The main page first, on its own (frame 0 is always the page itself).
  try {
    frames = await goforitWithTimeout(goforitRunIn({ tabId: tab.id, frameIds: [0] }), GOFORIT_MAIN_FRAME_MS);
  } catch (err) {
    if (err.message === "timeout") {
      return "The page didn't answer for over 2 minutes: it may have reloaded or still be loading. "
        + "Wait until it has fully loaded, then click Fill again.";
    }
    // e.g. chrome:// pages and the Chrome Web Store can't be scripted.
    return `Can't fill this page: ${err.message}`;
  }
  // 2. Forms are sometimes inside an iframe (a page embedded in the page), so try every
  //    frame too, but don't wait long. The main page answers "already done" this time.
  try {
    const more = await goforitWithTimeout(goforitRunIn({ tabId: tab.id, allFrames: true }), GOFORIT_OTHER_FRAMES_MS);
    frames = frames.concat(more.filter((f) => f.frameId !== 0));
  } catch (err) {
    // A frame that never answers (or one Chrome won't let us into) is skipped.
  }

  if (frames[0] && frames[0].result && frames[0].result.busy) {
    return "A Fill is already running on this page: give it a moment (it shows its results in the panel).";
  }
  const results = frames.map((f) => f.result).filter((r) => r && !r.empty);
  const errors = results.filter((r) => r.error);
  const filled = results.filter((r) => r.counts);
  if (!results.length) {
    return "No form fields found on this page. If you can see a form, tell the developer which site this is.";
  }
  if (!filled.length && errors.length) return errors[0].error;
  const c = { filled: 0, review: 0, missing: 0 };
  for (const r of filled) for (const k of Object.keys(c)) c[k] += r.counts[k];
  return `Filled ${c.filled} · Review ${c.review} · Missing ${c.missing}. Check the page, then submit it yourself.`;
}
