// Shared by all test forms: if anything submits the form or clicks a submit
// button, show a big red banner and set window.__goforitSubmitted = true.
// GoForIt must NEVER trigger this (CLAUDE.md rule 1).

window.__goforitSubmitted = false;

function tripwire(reason) {
  window.__goforitSubmitted = true;
  const banner = document.createElement("div");
  banner.id = "tripwire-banner";
  banner.textContent = `SUBMITTED (${reason}). This must never happen automatically.`;
  banner.style.cssText =
    "position:fixed;top:0;left:0;right:0;padding:16px;background:#cf222e;color:#fff;" +
    "font:bold 18px system-ui;text-align:center;z-index:2147483647";
  document.body.append(banner);
}

document.addEventListener(
  "submit",
  (event) => {
    event.preventDefault(); // never actually navigate away
    tripwire("submit event");
  },
  true
);

document.addEventListener(
  "click",
  (event) => {
    if (event.target.closest("[data-tripwire]")) {
      event.preventDefault();
      tripwire("submit button clicked");
    }
  },
  true
);
