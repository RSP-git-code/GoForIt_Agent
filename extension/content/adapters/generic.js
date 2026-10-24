// Generic adapter: standard HTML forms (<input>, <select>, <textarea>).
// Used for any site without its own adapter, and reused by the Greenhouse
// and Lever adapters, whose forms are mostly standard HTML.

(() => {
  const GF = (globalThis.GoForIt = globalThis.GoForIt || {});
  GF.adapters = GF.adapters || {};

  const SKIP_TYPES = ["hidden", "submit", "button", "reset", "image", "password", "search"];

  function isCandidate(el) {
    if (el.closest("#goforit-panel-host")) return false;
    if (GF.isCaptcha(el)) return false; // CLAUDE.md rule 3: never touched
    if (GF.isOneTimeCode(el)) return false; // OTP boxes: the code the site sends you, never filled
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (SKIP_TYPES.includes(type) || el.disabled) return false;
    if (type === "file") return true; // usually hidden behind a styled button
    // Read-only boxes are kept: calendar date pickers are usually read-only
    // text inputs. apply() then checks whether the value actually stuck.
    if (type === "radio" || type === "checkbox") {
      return GF.isVisible(el) || (el.labels && [...el.labels].some(GF.isVisible));
    }
    return GF.isVisible(el);
  }

  // Smallest element containing all the given elements.
  function commonAncestor(els) {
    let node = els[0].parentElement;
    while (node && !els.every((e) => node.contains(e))) node = node.parentElement;
    return node || document.body;
  }

  function optionText(input) {
    if (input.labels && input.labels.length) return GF.textWithoutControls(input.labels[0]);
    return GF.cleanText(input.getAttribute("aria-label") || input.value);
  }

  // One text box, textarea, select, date, etc.
  // Libraries like Select2 hide the real <select> (1px, invisible) and draw
  // their own widget right after it. Highlight that widget instead.
  function visibleBox(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width > 2 && rect.height > 2) return el;
    const widget = el.nextElementSibling;
    return widget && GF.isVisible(widget) ? widget : el.parentElement || el;
  }

  function inputField(el) {
    const descriptor = GF.describe(el);
    if (descriptor.kind === "select") descriptor.options = [...el.options].map((o) => GF.cleanText(o.text)).slice(0, 300);
    return {
      descriptor,
      highlightEl: visibleBox(el),
      hasValue() {
        if (el.tagName === "SELECT") return el.selectedIndex > 0 && el.value !== "";
        return el.value.trim() !== "" && !GF.isPlaceholderValue(el.value);
      },
      // What's in the box now, as text (for "page has X, profile says Y").
      currentValue() {
        if (el.tagName === "SELECT") return el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : "";
        return el.value;
      },
      async apply(value) {
        if (descriptor.kind === "select") return GF.applySelect(el, value);
        if (descriptor.kind === "combobox") {
          // The site's own dropdown: press it, pick the matching option (applier.js).
          return GF.applyCombobox(el, value);
        }
        if (el.readOnly) {
          const text = Array.isArray(value) ? value.join(", ") : String(value);
          GF.setNativeValue(el, text);
          return el.value === text
            ? { status: "review", reason: `Date picker box: check it shows ${text}` }
            : { status: "review", reason: `Pick ${text} with the date picker` };
        }
        return GF.applyText(el, value);
      },
    };
  }

  // A file input (resume upload). Filling these comes in Phase 7.
  function fileField(el) {
    const box = el.closest(".field, .application-question, li, fieldset, label") || el.parentElement;
    const descriptor = GF.describe(el, { label: GF.labelFor(el) || GF.cleanLabel(GF.precedingText(box)) });
    return {
      descriptor,
      input: el, // content.js attaches the saved resume here
      highlightEl: GF.isVisible(el) ? el : box,
      // Sites that keep your resume show "ResumeATS.pdf Uploaded: ..." near the
      // input instead of a file in it. Look a few levels up for that. A file
      // name needs letters before the dot, so "Allowed types: .pdf" doesn't count.
      hasValue() {
        if (el.files && el.files.length > 0) return true;
        if (/uploaded|\w\.(pdf|docx?)\b/i.test(descriptor.label)) return true; // e.g. Amazon: label is the stored file
        let node = el.parentElement;
        for (let depth = 0; depth < 4 && node && node !== document.body; depth++, node = node.parentElement) {
          if (/\buploaded\b|\w\.(pdf|docx?)\b/i.test(node.textContent)) return true;
        }
        return false;
      },
      async apply() {
        return { status: "review", reason: "Upload this file yourself" };
      },
    };
  }

  // Radio buttons with the same name, or several checkboxes with the same name.
  function choiceGroupField(inputs, kind) {
    const container = inputs[0].closest("fieldset") || commonAncestor(inputs);
    const legend = container.tagName === "FIELDSET" && container.querySelector("legend");
    const label = GF.cleanLabel(legend ? legend.textContent : GF.precedingText(container));
    const choices = inputs.map((input) => ({ text: optionText(input), el: input, isChecked: () => input.checked }));
    return {
      descriptor: GF.describe(inputs[0], {
        label,
        kind,
        options: choices.map((c) => c.text).slice(0, 300),
        required: inputs.some((i) => i.required || i.getAttribute("aria-required") === "true"),
      }),
      highlightEl: container,
      hasValue: () => inputs.some((i) => i.checked),
      apply: (value) => GF.applyChoice(choices, value, kind === "checkbox"),
    };
  }

  // A single checkbox (e.g. "I agree to the terms").
  function singleCheckboxField(input) {
    const label = optionText(input) || GF.labelFor(input);
    return {
      descriptor: GF.describe(input, { label, kind: "checkbox", options: [label] }),
      highlightEl: input.labels && input.labels[0] ? input.labels[0] : input,
      hasValue: () => input.checked,
      apply: (value) => GF.applyChoice([{ text: label, el: input, isChecked: () => input.checked }], value, true),
    };
  }

  // A dropdown drawn as <div role="combobox"> showing its current choice as text.
  function divComboboxField(el) {
    const descriptor = GF.describe(el);
    descriptor.kind = "combobox";
    const shown = () => GF.cleanText(el.textContent || "");
    return {
      descriptor,
      highlightEl: el,
      hasValue: () => !!shown() && !GF.isPlaceholderValue(shown()),
      currentValue: shown,
      apply: (value) => GF.applyCombobox(el, value),
    };
  }

  function extract(root = document) {
    const controls = GF.queryAllDeep("input, textarea, select", root).filter(isCandidate);

    // Group radios/checkboxes by name; keep the page order.
    const groups = new Map();
    for (const el of controls) {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if ((type === "radio" || type === "checkbox") && el.name) {
        const key = `${type}:${el.name}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(el);
      }
    }

    const fields = [];
    const seen = new Set();
    // Sites' own dropdowns drawn with a <div role="combobox"> (Oracle, IBM...): no <input> inside.
    // (<button>-based ones are skipped: GoForIt never presses buttons.)
    const divBoxes = GF.queryAllDeep('[role="combobox"]', root).filter((el) =>
      !el.matches("input, select, textarea, button") && !el.querySelector("input, select, textarea")
      && !el.closest("#goforit-panel-host") && GF.isVisible(el));
    for (const el of divBoxes) fields.push(divComboboxField(el));
    for (const el of controls) {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (type === "file") {
        fields.push(fileField(el));
      } else if ((type === "radio" || type === "checkbox") && el.name) {
        const key = `${type}:${el.name}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const members = groups.get(key);
        fields.push(type === "checkbox" && members.length === 1 ? singleCheckboxField(el) : choiceGroupField(members, type));
      } else if (type === "checkbox") {
        fields.push(singleCheckboxField(el));
      } else if (type === "radio") {
        fields.push(choiceGroupField([el], "radio"));
      } else {
        fields.push(inputField(el));
      }
    }
    return fields;
  }

  GF.adapters.generic = {
    name: "Generic form",
    matches: () => true,
    extract,
    // For the Matcher: page title, main heading, and the job description if the
    // page marks one; otherwise the page's main text outside the form. Capped at 6000 chars.
    jobDescription: () => {
      const described = document.querySelector(
        "[class*='job-description' i], [class*='jobdescription' i], [id*='job-description' i], [class*='description' i], [itemprop='description']"
      );
      let body = described ? described.innerText : "";
      if (!body) {
        const main = document.querySelector("main, [role='main'], article") || document.body;
        const copy = main.cloneNode(true);
        copy.querySelectorAll("form, nav, header, footer, script, style, #goforit-panel-host").forEach((n) => n.remove());
        body = copy.textContent;
      }
      const heading = document.querySelector("h1");
      return GF.cleanText(`${document.title} ${heading ? heading.innerText : ""} ${body}`).slice(0, 6000);
    },
  };
  // Shared with the other adapters.
  GF.genericExtract = extract;
})();
