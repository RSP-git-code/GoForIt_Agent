// Agent Octo chat (Chrome side panel). Each message goes to the backend on this laptop
// (POST /octo) with your profile; Octo's replies are typed out while he "talks".
// The side panel is an extension page like the popup, so it can call 127.0.0.1:8000
// directly (host_permissions in manifest.json) and read the profile from storage.

// (The preview page in extension/tests sets GOFORIT_BACKEND_URL to go through its test server.)
const BACKEND_URL = globalThis.GOFORIT_BACKEND_URL || "http://127.0.0.1:8000";
const $ = (id) => document.getElementById(id);
const octo = $("octo");

let lastResult = null; // the Coach analysis of the job we're talking about
let plan = null;       // the study plan so far; the backend edits it and sends it back each time
let history = [];      // recent turns, so the local AI remembers the conversation
let log = [];          // every bubble on screen ({who, text, links}), so the chat can be restored
let lastChips = [];

// ---------- remembering the chat ----------
// Chrome throws the side panel page away when you close it, and everything in these variables
// with it. So after each turn we save the chat to chrome.storage.local (on this laptop only,
// like the profile) and draw it again when the panel opens. "New chat" clears it.
const CHAT_KEY = "octoChat";
const KEEP = 60; // bubbles kept; older ones are dropped

async function saveChat() {
  log = log.slice(-KEEP);
  history = history.slice(-12);
  try {
    await chrome.storage.local.set({ [CHAT_KEY]: { log, history, lastResult, plan, chips: lastChips } });
  } catch (err) { /* storage unavailable (e.g. the dev preview): the chat just isn't kept */ }
}

async function loadChat() {
  try {
    return (await chrome.storage.local.get(CHAT_KEY))[CHAT_KEY] || null;
  } catch (err) {
    return null;
  }
}

// ---------- Octo's face ----------

// Mood = a class on the SVG ("idle", "thinking", "happy", "concerned"); octo.css draws each.
// classList.toggle adds/removes one class without touching the others.
function setMood(mood) {
  const talking = octo.classList.contains("talking");
  octo.setAttribute("class", mood);
  octo.classList.toggle("talking", talking);
}
function setTalking(on) {
  octo.classList.toggle("talking", on);
}

// The pupils look towards the mouse: move them up to 3 units in its direction.
document.addEventListener("mousemove", (e) => {
  const box = octo.getBoundingClientRect();
  const dx = e.clientX - (box.left + box.width / 2);
  const dy = e.clientY - (box.top + box.height * 0.42);
  const len = Math.hypot(dx, dy) || 1;
  const move = `translate(${(dx / len) * 3}px, ${(dy / len) * 3}px)`;
  octo.querySelectorAll(".pupil, .glint").forEach((p) => (p.style.transform = move));
});

// ---------- chat bubbles ----------

// A few tiny bubbles rise from under a new message as it floats in (skipped for restored ones).
function addTrail(div) {
  for (let i = 0; i < 3; i++) {
    const t = document.createElement("span");
    t.className = "trail";
    t.style.left = `${20 + Math.random() * 60}%`;
    t.style.animationDelay = `${0.1 + i * 0.12}s`;
    t.addEventListener("animationend", () => t.remove());
    div.append(t);
  }
}

function scrollDown() {
  $("chat").scrollTop = $("chat").scrollHeight;
}

// Your message. textContent never interprets HTML, so pasted text can't inject anything.
function addMine(text, restored = false) {
  const div = document.createElement("div");
  div.className = "msg me" + (text.length > 300 ? " long" : "") + (restored ? " restored" : "");
  div.textContent = text.length > 300 ? "📋 Job description pasted (click to expand)\n" + text.slice(0, 280) : text;
  if (text.length > 300) {
    div.title = "Click to show or hide the whole text";
    // Click toggles between the short preview and the full pasted text.
    div.addEventListener("click", () => {
      div.classList.toggle("open");
      div.textContent = div.classList.contains("open") ? text : "📋 Job description pasted (click to expand)\n" + text.slice(0, 280);
    });
  }
  $("chat").append(div);
  if (!restored) addTrail(div);
  // A pasted job description is saved shortened: the analysis is what matters later.
  log.push({ who: "me", text: text.length > 300 ? text.slice(0, 300) + " " : text });
  scrollDown();
}

function addTyping() {
  const div = document.createElement("div");
  div.className = "msg octo";
  div.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>'; // fixed markup, no user text
  $("chat").append(div);
  scrollDown();
  return div;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Octo's message, typed out a few characters at a time while his mouth moves.
// restored = drawn again from the saved chat: shown at once, no typing.
async function addOcto({ text, links }, restored = false) {
  const div = document.createElement("div");
  div.className = "msg octo" + (restored ? " restored" : "");
  $("chat").append(div);
  log.push({ who: "octo", text, links: links || [] });
  if (restored) {
    div.textContent = text;
  } else {
    div.textContent = " ";
    setTalking(true);
    const step = Math.max(2, Math.ceil(text.length / 120)); // long answers type faster
    for (let i = 0; i < text.length; i += step) {
      div.textContent = text.slice(0, i + step);
      scrollDown();
      await sleep(14);
    }
    setTalking(false);
    addTrail(div); // after typing: setting textContent above would have removed it
  }
  if (links && links.length) {
    const row = document.createElement("div");
    row.className = "links";
    for (const link of links) {
      const a = document.createElement("a");
      a.href = link.url;
      a.textContent = link.title;
      a.target = "_blank"; // opens in a new tab, only when you click it
      a.rel = "noopener";
      row.append(a);
    }
    div.append(row);
  }
  scrollDown();
}

// Suggested replies sit at the END of the conversation (inside the chat, so they scroll
// with it and never cover a long answer). Old suggestions are removed when you send.
function showChips(chips) {
  lastChips = chips || [];
  document.querySelectorAll("#chat .chips").forEach((c) => c.remove());
  if (!chips || !chips.length) return;
  const row = document.createElement("div");
  row.className = "chips";
  for (const label of chips) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.addEventListener("click", () => send(label));
    row.append(b);
  }
  $("chat").append(row);
  scrollDown();
}

// ---------- talking to the backend ----------

// label: what your bubble shows instead of the text (e.g. "📄 QC Associate JD.pdf").
async function send(text, jobTitle = "", label = "") {
  text = text.trim();
  if (!text) return;
  addMine(label || text);
  showChips([]);
  $("send").disabled = true;
  setMood("thinking");
  $("status").textContent = "thinking…";
  const typing = addTyping();
  try {
    const profile = await loadProfile(); // from shared/storage.js
    const resp = await fetch(`${BACKEND_URL}/octo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, last_result: lastResult, plan, history, profile, job_title: jobTitle }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const out = await resp.json();
    typing.remove();
    if (out.result) lastResult = out.result; // a new job was checked
    if ("plan" in out) plan = out.plan;     // "in" = the reply has that key (even when it is null)
    setMood(out.mood || "idle");
    for (const m of out.messages) await addOcto(m);
    history.push({ role: "student", text: text.slice(0, 400) },
                 { role: "octo", text: out.messages.map((m) => m.text).join(" ").slice(0, 400) });
    showChips(out.chips);
    saveChat();
  } catch (err) {
    typing.remove();
    setMood("concerned");
    await addOcto({ text: "I can't reach the GoForIt backend. Start it (start-backend.bat) and try again." });
  } finally {
    $("send").disabled = false;
    $("status").textContent = "your job-fit buddy";
  }
}

// ---------- 📎 upload a job description (PDF or .txt) ----------
// The hidden <input type="file"> is Chrome's own file picker; the 📎 button just "clicks" it.
// FileReader.readAsDataURL gives the file as text ("data:application/pdf;base64,JVBER...");
// the part after the comma is the file's bytes in base64, which can travel inside JSON.
// The backend (on this laptop) pulls the text out, and it's then checked like a pasted job.
$("attach").addEventListener("click", () => $("file").click());

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

$("file").addEventListener("change", async () => {
  const file = $("file").files[0];
  $("file").value = ""; // so picking the same file again still fires "change"
  if (!file) return;
  $("attach").disabled = true;
  $("status").textContent = "reading the file…";
  let text = "", problem = "";
  try {
    const resp = await fetch(`${BACKEND_URL}/octo/read-file`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: file.name, data_base64: await readAsBase64(file) }),
    });
    const out = await resp.json();
    if (!resp.ok) problem = out.detail || `Backend error (HTTP ${resp.status}).`;
    else text = out.text;
  } catch (err) {
    problem = "I can't reach the GoForIt backend. Start it (start-backend.bat) and try again.";
  } finally {
    $("attach").disabled = false;
    $("status").textContent = "your job-fit buddy";
  }
  if (!problem && text.trim().length < 80) {
    problem = "I couldn't find text in that file: it's probably a scanned picture. Select the text on the page instead, or paste it.";
  }
  if (problem) {
    setMood("concerned");
    await addOcto({ text: problem });
    return;
  }
  // The file name usually holds the job title ("QC Associate JD v1.0.pdf" -> "QC Associate JD v1.0").
  send(text, file.name.replace(/\.(pdf|txt)$/i, ""), `📄 ${file.name}`);
});

// ---------- day / night sea ----------
// No choice saved = follow Windows. A click picks the opposite of what's showing and remembers
// it in localStorage (this panel's own small store; it only holds "light" or "dark").
const media = matchMedia("(prefers-color-scheme: dark)");
function isDark() {
  const chosen = document.documentElement.dataset.theme;
  return chosen ? chosen === "dark" : media.matches;
}
function showThemeButton() {
  $("theme").textContent = isDark() ? "☀️" : "🌙";
  $("theme").title = isDark() ? "Daytime sea" : "Night sea";
}
try {
  const saved = localStorage.getItem("octoTheme");
  if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
} catch (err) { /* storage blocked: follow Windows */ }
showThemeButton();
media.addEventListener("change", showThemeButton);
$("theme").addEventListener("click", () => {
  const next = isDark() ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("octoTheme", next); } catch (err) { /* not remembered */ }
  showThemeButton();
});

// ---------- fun: click Octo ----------
// He spins and blows a puff of bubbles. The bubbles are little <span>s placed over him that
// float up and fade (CSS "puff" animation); each removes itself when its animation ends.
octo.addEventListener("click", () => {
  octo.classList.remove("spin");
  void octo.getBoundingClientRect(); // forces the browser to notice the removal, so the spin can replay
  octo.classList.add("spin");
  const box = octo.getBoundingClientRect();
  for (let i = 0; i < 7; i++) {
    const b = document.createElement("span");
    b.className = "puff";
    b.style.left = `${box.left + box.width / 2 + (Math.random() - 0.5) * 40}px`;
    b.style.top = `${box.top + box.height * 0.6}px`;
    b.style.setProperty("--dx", `${(Math.random() - 0.5) * 70}px`); // drift sideways a little
    b.style.animationDelay = `${i * 0.08}s`;
    b.addEventListener("animationend", () => b.remove());
    document.body.append(b);
  }
});
octo.addEventListener("animationend", (e) => {
  if (e.animationName === "spin") octo.classList.remove("spin");
});

// ---------- the input box ----------

const input = $("input");
// Grow the box with its content (up to the CSS max-height).
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight}px`;
});
// The Enter key sends (Shift+Enter makes a new line). This is Octo's own chat box,
// not a job site's form. requestSubmit isn't needed: we call send() directly.
input.addEventListener("keydown", (e) => {
  if (e.keyCode === 13 && !e.shiftKey) {
    e.preventDefault();
    sendFromBox();
  }
});
function sendFromBox() {
  const text = input.value;
  input.value = "";
  input.style.height = "auto";
  send(text);
}
$("composer").addEventListener("submit", (e) => {
  e.preventDefault(); // Octo's own little form: never sends anything anywhere but the backend
  sendFromBox();
});

// ---------- hello (or welcome back) ----------

async function greet() {
  setMood("happy");
  await addOcto({ text: "Hi! I'm Agent Octo 🐙\nSelect a job description on the page, right-click → \"Ask Agent Octo about this\" (or press Alt+Shift+O), or paste it here. I'll tell you if it's a fit, what you already have, and what to learn." });
  setMood("idle");
  showChips(["What can you do?", "How do I learn Docker?"]);
  saveChat();
}

$("new-chat").addEventListener("click", async () => {
  $("chat").replaceChildren(); // removes every bubble
  log = []; history = []; lastResult = null; plan = null;
  try { await chrome.storage.local.remove(CHAT_KEY); } catch (err) { /* nothing saved */ }
  greet();
});

// ---------- text you selected on a page (right-click "Ask Agent Octo about this", or Alt+Shift+O) ----------
// background.js leaves it in chrome.storage.session as "octoPending". A whole job description
// is checked straight away; a short bit (one line, a requirement) goes into the box with your
// cursor after it, so you can add your question.
const JD_HINT = /requirements?|responsibilit|qualifications?|what you.ll do|about the role|eligibility|job description|we are looking for/i;

let taking = false; // the panel can hear about the same selection twice while opening

async function takePending() {
  if (taking) return;
  taking = true;
  try { await usePending(); } finally { taking = false; }
}

async function usePending() {
  let pending = null;
  try {
    pending = (await chrome.storage.session.get("octoPending")).octoPending;
    if (pending) await chrome.storage.session.remove("octoPending");
  } catch (err) { return; } // storage.session unavailable (dev preview)
  if (!pending || !pending.text || Date.now() - pending.at > 60000) return; // ignore leftovers
  const text = pending.text.trim();
  // The tab title usually starts with the job title ("AI Engineer Intern - Company | ...").
  const jobTitle = pending.title.split(/\s[|–-]\s/)[0].slice(0, 120);
  if (text.length > 350 || (text.split("\n").length > 3 && JD_HINT.test(text))) {
    send(text, jobTitle);
  } else {
    input.value = `About this: "${text}"\n`;
    input.dispatchEvent(new Event("input")); // grow the box to fit
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length); // cursor at the end
  }
}

// storage.onChanged fires in every extension page when stored data changes: this is how an
// already-open panel hears about a new selection.
try {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "session" && changes.octoPending && changes.octoPending.newValue) takePending();
  });
} catch (err) { /* dev preview */ }

(async () => {
  const saved = await loadChat();
  if (!saved || !saved.log || !saved.log.length) {
    await greet();
    return takePending();
  }
  history = saved.history || [];
  lastResult = saved.lastResult || null;
  plan = saved.plan || null;
  for (const m of saved.log) {
    if (m.who === "me") addMine(m.text, true);
    else await addOcto(m, true);
  }
  showChips(saved.chips);
  takePending();
})();
