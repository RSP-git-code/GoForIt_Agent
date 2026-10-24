// Applier: low-level helpers that put values into form controls safely.
//
// SAFETY (CLAUDE.md rule 1): GoForIt never submits. The only clicks we make
// go through GF.safeClick(), which refuses buttons, links and anything that
// isn't a radio / checkbox / dropdown option. We never call form.submit(),
// form.requestSubmit(), or fire "submit" events. Enter is pressed only by
// GF.pressEnterToSearch, inside a picker's search box (see there), never in
// an ordinary text box.

(() => {
  const GF = (globalThis.GoForIt = globalThis.GoForIt || {});

  // "combobox": a site's own dropdown box (pressed to open its list, see GF.applyCombobox).
  const CLICKABLE_ROLES = ["radio", "checkbox", "option", "listbox", "combobox"];

  GF.safeClick = function (el) {
    const tag = el.tagName;
    const type = (el.getAttribute("type") || "").toLowerCase();
    const role = el.getAttribute("role");
    const isNativeChoice = tag === "INPUT" && (type === "radio" || type === "checkbox");
    // Workday's search results ("promptOption") are choices too, though they often lack role="option".
    const isWorkdayChoice = el.getAttribute("data-automation-id") === "promptOption";

    const insideButtonOrLink = el.closest('button, a[href], [role="button"], [role="link"], input[type="submit"], input[type="image"]');
    if (insideButtonOrLink || (!isNativeChoice && !isWorkdayChoice && !CLICKABLE_ROLES.includes(role))) {
      throw new Error("GoForIt refused to click something that is not a choice option");
    }
    el.click();
  };

  // ---------- Custom dropdowns (SuccessFactors, Oracle, Workday, IBM) ----------
  //
  // Many sites draw their own dropdown: a box with role="combobox" that shows a list of
  // role="option" items only after you press it. GoForIt presses the box, waits for the list,
  // and clicks the matching option, like a person would. It only ever presses the dropdown
  // box and its options (never buttons or links: GF.press refuses them).

  // Press like a mouse does: some widgets open on "mousedown", others on "click".
  // (MouseEvent is the event a mouse press sends; it can't submit anything by itself,
  // and GF.safeClick below refuses buttons and links before anything is pressed.)
  GF.press = function (el) {
    if (el.closest('button, a[href], input[type="submit"], input[type="image"]')) {
      throw new Error("GoForIt refused to press a button or link");
    }
    const opts = { bubbles: true, cancelable: true, view: window };
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    GF.safeClick(el);
  };

  // The option elements this dropdown controls (or, failing that, any visible ones on the page).
  function visibleOptions(box) {
    const ids = `${box.getAttribute("aria-controls") || ""} ${box.getAttribute("aria-owns") || ""}`.trim().split(/\s+/);
    const lists = ids.filter(Boolean).map((id) => document.getElementById(id)).filter(Boolean);
    // Workday marks its suggestions data-automation-id="promptOption" (sometimes without role="option").
    const OPTION = '[role="option"], [data-automation-id="promptOption"]';
    const pool = lists.length ? lists.flatMap((l) => [...l.querySelectorAll(OPTION)]) : GF.queryAllDeep(OPTION);
    return pool.filter((o) => GF.isVisible(o) && GF.cleanText(o.textContent));
  }

  // ---------- Enter, ONLY in a picker's search box (approved 2026-10-22) ----------
  //
  // Workday's skills and field-of-study pickers search only when you press Enter. GoForIt may press
  // Enter in exactly one situation: inside a picker's SEARCH box, right after typing a value, so the
  // site shows its results (which GoForIt then clicks like any option). Never in an ordinary text box.
  // Why this can't submit: a key press made by a script is "untrusted", and browsers never run their
  // built-in actions for untrusted events (a form is never submitted by it); only the site's own
  // search code reacts. The never-submit test allows this one function and nothing else.
  GF.isSearchBox = function (el) {
    if (!el || el.tagName !== "INPUT" || !/^(text|search|)$/i.test(el.getAttribute("type") || "")) return false;
    const role = (el.getAttribute("role") || "").toLowerCase();
    const auto = (el.getAttribute("data-automation-id") || "").toLowerCase();
    return role === "combobox" || role === "searchbox" || !!el.getAttribute("aria-autocomplete") || auto === "searchbox"
      || !!el.closest('[data-automation-id="multiSelectContainer"], [data-automation-id*="multiselect" i], [role="combobox"]');
  };

  // ENTER-ALLOWED-START
  GF.pressEnterToSearch = function (input) {
    if (!GF.isSearchBox(input)) throw new Error("GoForIt only presses Enter in a picker's search box");
    const opts = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true };
    for (const type of ["keydown", "keypress", "keyup"]) input.dispatchEvent(new KeyboardEvent(type, opts));
  };
  // ENTER-ALLOWED-END

  // Type a value into a picker and wait for its suggestions; if none come, press Enter in the search
  // box (Workday) and wait for the results.
  // state.enter: set once this box has needed Enter, so later values press it straight away instead of
  // first waiting for suggestions that never come (12 skills x 1.2 s would add up).
  async function searchFor(input, text, state = {}) {
    let before = optionsKey(input); // what the list shows now (Workday keeps old results open)
    GF.setNativeValue(input, text); // fires "input": many sites suggest as you type
    let options = state.enter ? [] : await waitForFreshOptions(input, before, 1200);
    if (!options.length && GF.isSearchBox(input)) {
      before = optionsKey(input);
      GF.pressEnterToSearch(input);
      options = await waitForFreshOptions(input, before, 4000); // the site asks its server: give it time
      if (options.length) state.enter = true;
    }
    return options;
  }

  // The visible options' texts as one string, to tell a NEW list from the one already showing.
  function optionsKey(box) {
    return visibleOptions(box).map((o) => GF.cleanText(o.textContent)).join("|");
  }

  // Results that are new (different from `before`) and have stopped changing for 300 ms. Without this,
  // a list left open from the previous skill looks like "results" and GoForIt races past every skill.
  async function waitForFreshOptions(box, before, ms) {
    let last = null;
    let steady = 0;
    for (let waited = 0; waited <= ms; waited += 100) {
      const key = optionsKey(box);
      if (key && key !== before) {
        steady = key === last ? steady + 1 : 0;
        if (steady >= 3) return visibleOptions(box);
      }
      last = key;
      await GF.sleep(100);
    }
    return last && last !== before ? visibleOptions(box) : [];
  }

  // ---------- Tag boxes (Workday "Type to Add Skills", IBM skills) ----------
  //
  // Each skill becomes a separate tag. GoForIt does what you'd do by hand, one skill at a time:
  // type the skill (and press Enter if the picker searches only then), wait for the site's results,
  // click the result that IS that skill, clear the box, next skill.
  // A suggestion counts if it's the skill itself ("Python") or starts with it ("Python (Programming
  // Language)"), so "C" never picks "C++" or "Cloud Computing".
  function tagMatch(skill, texts) {
    const s = skill.toLowerCase().trim();
    const low = texts.map((t) => t.toLowerCase().trim());
    let i = low.findIndex((t) => t === s);
    // "Python (Programming Language)", "C - language"
    if (i < 0) i = low.findIndex((t) => t.startsWith(`${s} (`) || t.startsWith(`${s} -`));
    // "Hyper Text Markup Language (HTML)": the skill as the abbreviation in brackets
    if (i < 0) i = low.findIndex((t) => t.endsWith(`(${s})`));
    return i;
  }

  // Is this result already ticked / selected? (Clicking a ticked Workday result would UN-tick it.)
  // Only a TICK decides. Workday marks the highlighted (blue) row aria-selected="true" even when
  // its box is empty, so aria-selected is NOT read here (that skipped every first result).
  function tickBoxOf(option) {
    return option.querySelector('input[type="checkbox"], [role="checkbox"]');
  }
  function isPicked(option) {
    const box = tickBoxOf(option);
    if (box) return box.checked === true || box.getAttribute("aria-checked") === "true";
    return option.getAttribute("aria-checked") === "true";
  }
  function hasTickBox(option) {
    return !!tickBoxOf(option) || option.hasAttribute("aria-checked");
  }

  // A small "please wait" banner while skills are added one by one, so clicks don't get in the way.
  function progressBanner() {
    const host = document.createElement("div");
    host.id = "goforit-progress-host";
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `<style>div { position: fixed; top: 12px; left: 50%; transform: translateX(-50%); z-index: 2147483647;
      background: #1f2328; color: #fff; padding: 8px 14px; border-radius: 8px; font: 13px system-ui, sans-serif;
      box-shadow: 0 4px 14px rgba(0,0,0,.25); }</style><div role="status"></div>`;
    document.body.append(host);
    return {
      set: (text) => (shadow.querySelector("div").textContent = text),
      remove: () => host.remove(),
    };
  }

  GF.applyTags = async function (input, skills) {
    // "TensorFlow/Keras" is two skills on most sites.
    const wanted = [...new Set(skills.flatMap((s) => (/\//.test(s) ? s.split("/").map((x) => x.trim()) : [s])).filter(Boolean))];
    const added = [];
    const missed = [];
    const state = {}; // remembers whether this box needs Enter to search
    const banner = progressBanner();
    try {
      for (const [n, skill] of wanted.entries()) {
        banner.set(`GoForIt is adding skills: ${n + 1} of ${wanted.length} (${skill}). Please don't click until it's done.`);
        input.focus();
        let options = await searchFor(input, skill, state);
        if (!options.length && !added.length && !missed.length) {
          // Not even one result for the first skill (even after Enter, if allowed): this box isn't a
          // picker GoForIt can use, so stop now instead of waiting on every skill.
          GF.setNativeValue(input, "");
          missed.push(...wanted);
          break;
        }
        let i = tagMatch(skill, options.map((o) => GF.cleanText(o.textContent)));
        if (i < 0 && options.length) {
          // The list may still be loading the rest: one more look before calling it "not offered".
          await GF.sleep(1500);
          options = visibleOptions(input);
          i = tagMatch(skill, options.map((o) => GF.cleanText(o.textContent)));
        }
        if (i < 0) {
          missed.push(skill);
        } else if (isPicked(options[i])) {
          added.push(skill); // already ticked (an earlier Fill, or you): never click it again
        } else {
          try {
            GF.press(options[i]); // an option click, like picking from a dropdown
            await GF.sleep(600); // let the site add the tag, like a person would
            // Check it took: if the result has a tick box that's still empty, click once more.
            if (options[i].isConnected && hasTickBox(options[i]) && !isPicked(options[i])) {
              const box = tickBoxOf(options[i]);
              GF.press(box || options[i]); // the row didn't take: click the tick box itself
              await GF.sleep(600);
            }
            added.push(skill);
          } catch (err) {
            missed.push(skill);
          }
        }
        GF.setNativeValue(input, ""); // empty the box for the next skill
      }
    } finally {
      banner.remove();
    }
    GF.signalFocus(input, false);
    if (!added.length) {
      return { status: "review", reason: `No suggestions appeared, so add these yourself, one at a time: ${wanted.join(", ")}` };
    }
    return {
      status: "review",
      reason: `Added ${added.join(", ")}: check the tags` + (missed.length ? `. Not found on this site, add yourself if needed: ${missed.join(", ")}` : ""),
    };
  };

  async function waitForOptions(box, ms = 1500) {
    for (let waited = 0; waited <= ms; waited += 100) {
      const found = visibleOptions(box);
      if (found.length) return found;
      await GF.sleep(100);
    }
    return [];
  }

  // What the box shows now (its value, or its text for div-based widgets).
  function shownText(box) {
    return GF.cleanText(("value" in box && box.value) || box.getAttribute("aria-valuetext") || box.textContent || "");
  }

  // value: the answer, or a list of acceptable answers in order of preference
  // (e.g. ["Asian - Indian Subcontinent", "Indian", "South Asian"]): the first one the list has wins.
  GF.applyCombobox = async function (box, value) {
    const choices = (Array.isArray(value) ? value : [value]).map(String).filter(Boolean);
    const wanted = choices[0];
    if (!wanted) return { status: "review", reason: "Pick an option from the list" };
    try {
      GF.press(box);
    } catch (err) {
      return { status: "review", reason: `Pick "${wanted}" from the list` };
    }
    let options = await waitForOptions(box);
    const texts = () => options.map((o) => GF.cleanText(o.textContent));
    let index = -1;
    for (const choice of choices) {
      index = GF.findOption(choice, texts());
      if (index >= 0) break;
    }
    // Searchable dropdowns (IBM, Workday): type to filter, then look again. Each acceptable answer
    // is tried in turn ("Computer Science and Engineering", then "Computer Science", ...).
    if (index < 0 && box.tagName === "INPUT" && !box.readOnly) {
      for (const choice of choices) {
        options = await searchFor(box, choice);
        index = GF.findOption(choice, options.map((o) => GF.cleanText(o.textContent)));
        if (index >= 0) break; // (no results for one wording doesn't mean none for the next: keep trying)
      }
      if (index < 0) GF.setNativeValue(box, ""); // don't leave a half-typed search behind
    }
    if (index < 0) {
      if (box.getAttribute("aria-expanded") === "true") GF.press(box); // close the list again
      return { status: "review", reason: `Pick "${wanted}" from the list (no matching option found)` };
    }
    const option = options[index];
    const chosen = GF.cleanText(option.textContent);
    GF.press(option);
    await GF.sleep(200);
    GF.signalFocus(box, false);
    // Check it took: the box now shows the option, or the option is marked selected.
    const took = GF.normalize(shownText(box)).includes(GF.normalize(chosen)) || option.getAttribute("aria-selected") === "true";
    return took ? { status: "filled", reason: "" } : { status: "review", reason: `Check that "${chosen}" is selected` };
  };

  // The ONLY button GoForIt may click (allowed 2026-10-14): "Add Education"-type
  // buttons, so the education boxes appear on sites like Oracle Cloud. It refuses
  // anything that could submit the form or leave the page. Save / Next / Submit
  // are never clicked. Note: a <button> with no type inside a <form> IS a submit
  // button in HTML, so it's refused too.
  const ADD_SECTION = /^\+?\s*add\s+(an?\s+|another\s+|new\s+)?(education|qualification|degree|school)\b/i;
  GF.clickAddSection = function (el) {
    const text = GF.cleanText(el.innerText || el.textContent || "");
    if (!ADD_SECTION.test(text) || text.length > 40) throw new Error(`Not an "Add Education" button: ${text}`);
    if (el.matches('input[type="submit"], input[type="image"]')) throw new Error("Refused: submit input");
    if (el.tagName === "BUTTON" && el.form && (el.getAttribute("type") || "submit").toLowerCase() === "submit") {
      throw new Error("Refused: this button would submit the form");
    }
    // A link may only be a page-internal one ("#..." or "javascript:..."). An EMPTY href (<a href="">)
    // means "this same page" and reloads it, so it's refused too.
    if (el.tagName === "A" && el.hasAttribute("href") && !/^\s*(#|javascript:)/i.test(el.getAttribute("href"))) {
      throw new Error("Refused: link that loads a page");
    }
    if (GF.reloadsPage(el)) throw new Error("Refused: this button reloads the page");
    el.click();
  };

  // Old-style sites wire some boxes or buttons to reload / submit the page by themselves
  // ("on change: submit the form", ASP.NET's __doPostBack). Typing by hand triggers it too, but
  // GoForIt filling many boxes in a row would lose everything. Such elements are left alone.
  // (Only inline handlers written in the page's HTML can be seen; code attached by scripts can't.)
  const RELOADS = /\bsubmit\s*\(|__doPostBack|location\s*\.\s*(reload|replace|assign)|location(\.href)?\s*=|\.reload\s*\(/i;
  GF.reloadsPage = function (el) {
    const attrs = ["onchange", "oninput", "onblur", "onclick", "onkeyup", "onfocusout"];
    const own = attrs.map((a) => el.getAttribute(a) || "").join(" ");
    const form = el.form || el.closest("form");
    return RELOADS.test(own) || (!!form && RELOADS.test(form.getAttribute("onchange") || ""));
  };

  // Sets an input/textarea/select value in a way that React/Vue-based forms notice.
  //
  // Why not just `el.value = x`? Frameworks like React wrap the `value`
  // property to track changes. Setting it directly updates the box on screen,
  // but React's copy keeps the old value and resubmits that. Calling the
  // browser's original setter (from the prototype) and then firing "input" and
  // "change" events is the standard workaround that autofill tools use.
  GF.setNativeValue = function (el, value) {
    const proto =
      el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype :
      el.tagName === "SELECT" ? HTMLSelectElement.prototype :
      HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    el.focus({ preventScroll: true });
    GF.signalFocus(el, true);
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
    GF.signalFocus(el, false);
  };

  // Sites like Workday check a box when you LEAVE it (the "blur"/"focusout"
  // events): that's when a red "required" error is cleared. But when you click
  // Fill in the GoForIt popup, the popup has the keyboard focus, so Chrome
  // ignores el.focus()/el.blur() on the page and those events never happen.
  // Sending them ourselves makes the site re-check the box. (FocusEvent is just
  // the event type for focus changes; it can't submit anything.)
  GF.signalFocus = function (el, entering) {
    const [plain, bubbling] = entering ? ["focus", "focusin"] : ["blur", "focusout"];
    el.dispatchEvent(new FocusEvent(plain));                       // what onfocus/onblur listen to
    el.dispatchEvent(new FocusEvent(bubbling, { bubbles: true })); // what React listens to
  };

  // Fallback after filling: a box that now has a value but is still marked
  // invalid (aria-invalid="true", used by Workday) gets the "left the box"
  // signals once more, so the site re-validates it.
  GF.revalidate = function (elements) {
    let fixed = 0;
    for (const el of elements) {
      if (!el || !("value" in el) || el.getAttribute("aria-invalid") !== "true" || !String(el.value).trim()) continue;
      GF.signalFocus(el, true);
      el.dispatchEvent(new Event("change", { bubbles: true }));
      GF.signalFocus(el, false);
      fixed += 1;
    }
    return fixed;
  };

  GF.sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // ---------- Matching a profile value to one of a field's options ----------

  GF.normalize = function (s) {
    return String(s)
      .toLowerCase()
      .replace(/[’']/g, " ")
      .replace(/[^a-z0-9+#%]+/g, " ")
      .trim();
  };

  // The backend's Mapper already chose the option (synonyms, ranges, etc.
  // live in backend/services/option_match.py) and sends its exact text, so
  // here we only need to find that option again. Returns its index or -1.
  GF.findOption = function (wanted, options) {
    const w = GF.normalize(wanted);
    return w ? options.findIndex((o) => GF.normalize(o) === w) : -1;
  };

  // ---------- Applying values to standard HTML controls ----------

  function asText(value) {
    return Array.isArray(value) ? value.join(", ") : String(value);
  }

  // Text-like inputs and textareas.
  GF.applyText = async function (el, value) {
    GF.setNativeValue(el, asText(value));
    return { status: "filled", reason: "" };
  };

  // Native <select>.
  GF.applySelect = async function (el, value) {
    const i = GF.findOption(asText(value), [...el.options].map((o) => o.text));
    if (i < 0) return { status: "missing", reason: `Option "${asText(value)}" not found on the page` };
    GF.setNativeValue(el, el.options[i].value);
    return { status: "filled", reason: "" };
  };

  // A group of choices (radio buttons or a checkbox list), native or custom.
  // `choices` is a list of { text, el, isChecked() }. For a checkbox list,
  // `value` is the list of option texts to tick.
  GF.applyChoice = async function (choices, value, multiple) {
    const texts = choices.map((c) => c.text);
    const wanted = multiple && Array.isArray(value) ? value : [asText(value)];
    let found = 0;
    for (const w of wanted) {
      const i = GF.findOption(w, texts);
      if (i < 0) continue;
      found += 1;
      if (!choices[i].isChecked()) GF.safeClick(choices[i].el);
    }
    if (!found) return { status: "missing", reason: `Option "${wanted.join(", ")}" not found on the page` };
    return { status: "filled", reason: "" };
  };

  // ---------- Attaching a file (resume) ----------
  //
  // Web pages can't normally set a file input's value (so a site can't steal
  // your files). But a DataTransfer object, the same thing drag-and-drop uses,
  // can carry a File we build ourselves, and its file list can be assigned
  // to the input. Then we fire "input" and "change" so the site notices.

  // Does the input's accept="..." list allow this file? Empty accept = anything.
  GF.acceptsFile = function (input, name, type) {
    const accept = (input.getAttribute("accept") || "").toLowerCase();
    if (!accept.trim()) return true;
    const ext = `.${name.split(".").pop().toLowerCase()}`;
    return accept.split(",").map((a) => a.trim()).some((a) => a === ext || a === type || (a.endsWith("/*") && type.startsWith(a.slice(0, -1))));
  };

  // resume: { name, type, data (base64) }. Returns true if the input now holds the file.
  GF.attachFile = function (input, resume) {
    const bytes = Uint8Array.from(atob(resume.data), (c) => c.charCodeAt(0));
    const file = new File([bytes], resume.name, { type: resume.type || "application/pdf" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return input.files.length === 1 && input.files[0].name === resume.name;
  };
})();
