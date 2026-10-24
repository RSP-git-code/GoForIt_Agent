// Extractor: finds the form fields on the page and describes each one.
//
// Content-script basics:
// - These files are NOT loaded on every page. The popup injects them into the
//   current tab only when you click "Fill this page" (chrome.scripting).
// - They run in an "isolated world": they can read and change the page's DOM,
//   but they can't see the page's own JS variables (and vice versa).
// - Each file is wrapped in (() => { ... })(), a function that runs
//   immediately, so its variables stay private. What other files need is put
//   on one shared object, globalThis.GoForIt. Clicking Fill twice re-runs the
//   files, which just replaces those functions; nothing breaks.
//
// A "field" returned by an adapter looks like:
//   {
//     descriptor: { label, placeholder, name, element_id, aria_label,
//                   helper_text, kind, options, required, max_length },
//     highlightEl: element to colour green/yellow/red,
//     hasValue(): true if the user already filled it,
//     apply(value): async, fills it, returns { status, reason }
//   }
// The descriptor is plain data (no DOM), so in Phase 3 it can be sent to the backend.

(() => {
  const GF = (globalThis.GoForIt = globalThis.GoForIt || {});
  GF.adapters = GF.adapters || {};

  // Collapses whitespace and trims.
  GF.cleanText = function (s) {
    return (s || "").replace(/\s+/g, " ").trim();
  };

  // Label text without the trailing "*" / "✱" required markers.
  GF.cleanLabel = function (s) {
    return GF.cleanText(s)
      .replace(/^(q|question)\s*[.:]\s*/i, "") // "Q. Do you have..." prefixes
      .replace(/\s*\b(required|optional)\s*$/i, "")
      .replace(/[*✱]+\s*$/, "")
      .trim();
  };

  // True if a text node's parent is actually shown: not display:none, and not
  // a 1px "screen-reader only" box. Screen-reader text often repeats the label
  // ("Question Do you have...? required"), so we skip it.
  function rendered(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 1 && rect.height <= 1) return false;
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden";
  }

  // The text a person sees inside `el`, ignoring form controls and hidden text.
  // A TreeWalker visits every text node under an element, one by one.
  GF.visibleText = function (el) {
    const parts = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || parent.closest("input, select, textarea, button, option, script, style")) continue;
      if (node.nodeValue.trim() && rendered(parent)) parts.push(node.nodeValue);
    }
    return GF.cleanText(parts.join(" "));
  };

  // Visible text if there is any, otherwise all text (e.g. pages laid out off-screen).
  GF.labelText = function (el) {
    return GF.visibleText(el) || GF.textWithoutControls(el);
  };

  // True if the element takes up space on screen.
  GF.isVisible = function (el) {
    if (!el || !el.isConnected) return false;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  // Text of an element with any form controls removed (a <label> wrapping a
  // <select> would otherwise include every option's text).
  GF.textWithoutControls = function (el) {
    const copy = el.cloneNode(true);
    copy.querySelectorAll("input, select, textarea, button, script, style").forEach((n) => n.remove());
    return GF.cleanText(copy.textContent);
  };

  // `root` is the document, or the shadow root the element lives in.
  function textOfIds(ids, root = document) {
    return GF.cleanText(
      (ids || "")
        .split(/\s+/)
        .map((id) => root.getElementById(id))
        .filter(Boolean)
        .map((n) => GF.textWithoutControls(n))
        .join(" ")
    );
  }

  // Short text found just before `node`: checks previous siblings, then
  // climbs up to `maxDepth` parents and repeats. Handles layouts like Lever's
  // <div class="label">Phone</div><div class="field"><input></div>.
  // Placeholder-like labels that say nothing about the question ("Your answer",
  // "Type here", "Short answer text"): never used as the question text.
  const FILLER = new RegExp("^(" + [
    "your (answer|response)", "type (your answer|here|something)", "enter (your answer|here|text|a value)",
    "answer( here)?", "short answer( text)?", "long answer( text)?", "write (here|your answer)", "response",
    "select( an option)?", "choose",
    // Generic screen-reader names that say what KIND of box it is, not what it asks
    // (HCLTech names every box "text field" or "select option"). A bare "Email" still counts as a label.
    "(text|input|number|date|email|phone|mobile)( field| box| input)", "text", "input", "textbox", "text area",
    "dropdown( list)?", "select (option|box|field|list)", "combo ?box", "list ?box",
  ].join("|") + ")\\s*\\*?\\s*$", "i");
  GF.isFillerLabel = (text) => FILLER.test(GF.cleanText(text || ""));
  // What custom dropdowns show before you pick ("No Selection", "- Select -"): not a real value.
  GF.isPlaceholderValue = (text) => /^\W*(no selection|select( one| an option)?|choose( one)?|please (select|choose)|none selected)\W*$/i.test(GF.cleanText(text || ""));

  GF.precedingText = function (node, maxDepth = 4) {
    for (let depth = 0; depth < maxDepth && node && node !== document.body; depth++) {
      let sib = node.previousElementSibling;
      while (sib) {
        if (!sib.matches("script, style, input, select, textarea, button")) {
          const text = GF.labelText(sib);
          if (text && !GF.isFillerLabel(text)) return text.length <= 250 ? text : "";
        }
        sib = sib.previousElementSibling;
      }
      node = node.parentElement;
    }
    return "";
  };

  // Best guess at the question text for one control.
  // Boxes laid out in a table (HCLTech's "10TH ACADEMIC DETAILS"): the question is the
  // heading of the box's COLUMN ("School Name"), and the row's first cell says which one
  // ("10th"). Result: "10th · School Name". Works for real <table>s and for ARIA grids
  // (role="row" / "columnheader" / "cell"). Returns "" when the box isn't in such a table.
  GF.tableCellLabel = function (el) {
    const cell = el.closest("td, th, [role='cell'], [role='gridcell']");
    const row = cell && cell.closest("tr, [role='row']");
    const table = row && row.closest("table, [role='table'], [role='grid']");
    if (!table) return "";
    const cellsOf = (r) => [...r.children].filter((c) => c.matches("td, th, [role='cell'], [role='gridcell'], [role='columnheader'], [role='rowheader']"));
    // The column, counting merged cells (colspan) so headings line up with the boxes below them.
    const columnOf = (r, target) => {
      let col = 0;
      for (const c of cellsOf(r)) {
        if (c === target) return col;
        col += Number(c.getAttribute("colspan")) || 1;
      }
      return -1;
    };
    const cellAt = (r, col) => {
      let at = 0;
      for (const c of cellsOf(r)) {
        const span = Number(c.getAttribute("colspan")) || 1;
        if (col >= at && col < at + span) return c;
        at += span;
      }
      return null;
    };
    const col = columnOf(row, cell);
    if (col < 0) return "";
    const hasBox = (c) => !!c.querySelector("input, select, textarea, [role='combobox'], [role='listbox']");
    // The heading row: the nearest row above this one with no boxes in it (usually the first).
    const rows = [...table.querySelectorAll("tr, [role='row']")].filter((r) => r.closest("table, [role='table'], [role='grid']") === table);
    let heading = "";
    for (let i = rows.indexOf(row) - 1; i >= 0 && !heading; i--) {
      if (cellsOf(rows[i]).some(hasBox)) continue;
      const h = cellAt(rows[i], col);
      heading = h ? GF.cleanLabel(h.innerText || h.textContent || "") : "";
    }
    if (!heading) return "";
    // The row's name: its first cell, if that's short text and not a box ("10th", "12th", "Diploma").
    const first = cellsOf(row)[0];
    const rowName = first && first !== cell && !hasBox(first) ? GF.cleanLabel(first.innerText || first.textContent || "") : "";
    return rowName && rowName.length <= 30 ? `${rowName} · ${heading}` : heading;
  };

  GF.labelFor = function (el) {
    const root = el.getRootNode();
    // Each source is skipped if it's only a filler phrase like "Your answer" (some forms
    // label every box that way and put the real question above it as plain text).
    const real = (text) => {
      const clean = GF.cleanLabel(text || "");
      return clean && !GF.isFillerLabel(clean) ? clean : "";
    };
    const byIds = real(textOfIds(el.getAttribute("aria-labelledby"), root.getElementById ? root : document));
    if (byIds) return byIds;
    if (el.labels && el.labels.length) {
      const text = real([...el.labels].map((l) => GF.labelText(l)).join(" "));
      if (text) return text;
    }
    const aria = real(el.getAttribute("aria-label"));
    if (aria) return aria;
    const cell = GF.tableCellLabel(el);
    if (cell) return cell;
    const before = GF.cleanLabel(GF.precedingText(el));
    if (before) return before;
    // Inside a web component (shadow DOM), the label is usually on or next to
    // the component itself ("host"), e.g. <ui5-input accessible-name="City">.
    if (root instanceof ShadowRoot) {
      const host = root.host;
      return GF.cleanLabel(host.getAttribute("accessible-name") || "") || GF.labelFor(host);
    }
    return "";
  };

  // Like querySelectorAll, but also looks inside web components' "shadow DOM".
  // Shadow DOM is a private mini-page inside an element (e.g. SAP's <ui5-input>
  // keeps its real <input> there); normal searches don't see into it.
  // Results stay in page order. Only "open" shadow roots can be read.
  GF.queryAllDeep = function (selector, root = document) {
    const found = [];
    const visit = (parent) => {
      for (const child of parent.children) {
        if (child.matches(selector)) found.push(child);
        if (child.shadowRoot && child.id !== "goforit-panel-host") visit(child.shadowRoot);
        visit(child);
      }
    };
    visit(root);
    return found;
  };

  GF.kindOf = function (el) {
    if (el.tagName === "TEXTAREA") return "textarea";
    if (el.tagName === "SELECT") return "select";
    if (el.getAttribute("role") === "combobox") return "combobox";
    const type = (el.getAttribute("type") || "text").toLowerCase();
    // "month" boxes (<input type="month">) only accept "YYYY-MM", e.g. IBM's education dates.
    const known = ["email", "tel", "number", "date", "month", "url", "radio", "checkbox", "file"];
    return known.includes(type) ? type : "text";
  };

  // Builds the plain-data descriptor for a control. `overrides` lets adapters
  // supply things they know better (e.g. Google Forms question titles).
  // The heading of the section a field sits in ("Websites", "Education"...).
  // Some forms label boxes just "URL" or "From"; the heading says what they mean.
  // compareDocumentPosition tells whether a heading comes BEFORE the field in the page.
  GF.sectionFor = function (el) {
    const headings = document.querySelectorAll("h1, h2, h3, h4, h5, h6, legend, [role='heading']");
    let section = "";
    for (const h of headings) {
      if (h.contains(el)) continue;
      if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
        const text = GF.cleanText(h.textContent);
        if (text && text.length <= 80) section = text;
      } else {
        break; // headings are in page order: the rest come after the field
      }
    }
    return section;
  };

  GF.describe = function (el, overrides = {}) {
    const label = overrides.label !== undefined ? overrides.label : GF.labelFor(el);
    return {
      label,
      section: GF.sectionFor(el),
      placeholder: el.getAttribute("placeholder") || "",
      name: el.getAttribute("name") || "",
      element_id: el.id || "",
      aria_label: el.getAttribute("aria-label") || "",
      helper_text: textOfIds(el.getAttribute("aria-describedby")),
      kind: GF.kindOf(el),
      options: [],
      required: el.required || el.getAttribute("aria-required") === "true",
      max_length: el.maxLength > 0 ? el.maxLength : null,
      readonly: !!el.readOnly && el.tagName !== "SELECT",
      ...overrides,
    };
  };

  // ---------- CAPTCHAs (CLAUDE.md rule 3) ----------
  // GoForIt never solves, fills or clicks a CAPTCHA. These checks keep CAPTCHA
  // boxes out of the field list and let the panel remind you to solve it yourself.
  const CAPTCHA = /captcha|recaptcha|hcaptcha|turnstile/i;

  GF.isCaptcha = function (el) {
    const attrs = [el.name, el.id, el.className, el.getAttribute("aria-label"), el.getAttribute("placeholder")].join(" ");
    return CAPTCHA.test(attrs) || !!el.closest(".g-recaptcha, .h-captcha, .cf-turnstile, [class*='captcha' i], [id*='captcha' i]");
  };

  // One-time codes (OTP) the site texts or emails you: never filled, they aren't profile data.
  // HCLTech's "Enter OTP" box is named like "mobileOtp", which used to look like a phone field.
  // autocomplete="one-time-code" is the standard way pages mark such a box. The OTP test is
  // case-sensitive for "Otp" / "OTP" so words like "footprint" don't count.
  GF.isOneTimeCode = function (el) {
    if ((el.getAttribute("autocomplete") || "").toLowerCase() === "one-time-code") return true;
    const attrs = [el.name, el.id, el.getAttribute("aria-label"), el.getAttribute("placeholder"), GF.labelText(el)].join(" ");
    return /(^|[^A-Za-z])otp([^a-z]|$)|Otp|OTP/.test(attrs) ||
      /one[\s-]?time[\s-]?(pass|code)|verification[\s-]?code|pass ?code/i.test(attrs);
  };

  // True only for a CAPTCHA you can see and must solve (a checkbox or picture
  // puzzle). Many sites (Oracle, Workday) load an INVISIBLE one: a hidden frame,
  // a small badge in the corner and a hidden response box. Those need nothing
  // from you, so they don't count. getBoundingClientRect() gives the element's
  // size on screen in pixels.
  GF.pageHasCaptcha = function () {
    const candidates = document.querySelectorAll(
      ".g-recaptcha, .h-captcha, .cf-turnstile, iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='turnstile'], [id*='captcha' i], [name*='captcha' i]"
    );
    return [...candidates].some((el) => {
      if (el.closest(".grecaptcha-badge")) return false;                 // the corner badge
      if (/size=invisible/.test(el.getAttribute("src") || "")) return false;
      if (el.getAttribute("data-size") === "invisible") return false;   // <div class="g-recaptcha" data-size="invisible">
      if (el.matches("input[type='hidden'], textarea") && !GF.isVisible(el)) return false; // hidden response box
      const box = el.getBoundingClientRect();
      return GF.isVisible(el) && box.width >= 100 && box.height >= 50;    // a real widget is ~300 x 78
    });
  };

  // The CAPTCHA widget's own frame (when GoForIt runs in every frame).
  GF.isCaptchaFrame = function () {
    return /(^|\.)(recaptcha\.net|hcaptcha\.com|challenges\.cloudflare\.com)$/.test(location.hostname) || /\/recaptcha\//.test(location.pathname);
  };

  // Picks the adapter for this page (generic.js is the fallback), extracts
  // the fields and gives each one an id.
  GF.extractFields = function () {
    const order = ["googleForms", "greenhouse", "lever"];
    const adapter = order.map((n) => GF.adapters[n]).find((a) => a && a.matches()) || GF.adapters.generic;
    const fields = adapter.extract();
    fields.forEach((f, i) => (f.descriptor.id = `gf-${i}`));
    return { adapter, fields };
  };
})();
