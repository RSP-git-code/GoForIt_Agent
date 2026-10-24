// Google Forms adapter (docs.google.com/forms/...).
//
// Google Forms doesn't use normal <input type=radio> or <select>. Each
// question is a div[role=listitem] with a div[role=heading] title, and:
//   - radio buttons are div[role=radio] with aria-checked="true|false"
//   - checkboxes are div[role=checkbox]
//   - dropdowns are div[role=listbox] that open a list of div[role=option]
// "role" and "aria-*" attributes are accessibility hints for screen readers;
// they are also the most stable thing to select on, because Google's CSS
// class names are random-looking and change often.

(() => {
  const GF = (globalThis.GoForIt = globalThis.GoForIt || {});
  GF.adapters = GF.adapters || {};

  const TEXT_INPUTS = 'input[type="text"], input[type="email"], input[type="number"], input[type="url"], input[type="tel"], input[type="date"], textarea';

  function isChecked(el) {
    return el.getAttribute("aria-checked") === "true";
  }

  // Description text under the title (e.g. "10 digits, without +91").
  function helperText(item) {
    const copy = item.cloneNode(true);
    copy.querySelectorAll('[role="heading"], [role="radiogroup"], [role="listbox"], [role="list"], [role="checkbox"], input, textarea').forEach((n) => n.remove());
    return GF.cleanText(copy.textContent).replace(/^(your answer|required)$/i, "").slice(0, 200);
  }

  function choiceField(item, base, widgets, kind) {
    const choices = widgets.map((w) => ({
      text: GF.cleanText(w.getAttribute("data-value") || w.getAttribute("data-answer-value") || w.getAttribute("aria-label") || w.textContent),
      el: w,
      isChecked: () => isChecked(w),
    }));
    return {
      descriptor: { ...base, kind, options: choices.map((c) => c.text).slice(0, 300) },
      highlightEl: item,
      hasValue: () => widgets.some(isChecked),
      apply: (value) => GF.applyChoice(choices, value, kind === "checkbox"),
    };
  }

  function dropdownField(item, base, listbox) {
    const options = [...listbox.querySelectorAll('[role="option"]')];
    const texts = options.map((o) => GF.cleanText(o.getAttribute("data-value") || o.textContent));
    const selected = () => listbox.querySelector('[role="option"][aria-selected="true"]');

    return {
      descriptor: { ...base, kind: "select", options: texts.filter(Boolean).slice(0, 300) },
      highlightEl: item,
      hasValue: () => !!(selected() && selected().getAttribute("data-value")),
      async apply(value) {
        const text = Array.isArray(value) ? value.join(", ") : String(value);
        const index = GF.findOption(text, texts);
        if (index < 0) return { status: "missing", reason: `Option "${text}" not found on the page` };
        const wanted = texts[index];

        // Open the dropdown, wait for the option to become visible, click it.
        GF.safeClick(listbox);
        let target = null;
        for (let tries = 0; tries < 20 && !target; tries++) {
          await GF.sleep(50);
          target = [...document.querySelectorAll('[role="option"]')].find(
            (o) => o.getAttribute("data-value") === wanted && GF.isVisible(o)
          );
        }
        if (!target) return { status: "review", reason: `Choose "${wanted}" from the dropdown` };
        GF.safeClick(target);
        await GF.sleep(100);

        const now = selected();
        if (!now || now.getAttribute("data-value") !== wanted) {
          return { status: "review", reason: `Couldn't confirm the selection. Choose "${wanted}"` };
        }
        return { status: "filled", reason: "" };
      },
    };
  }

  function extract() {
    const fields = [];
    const items = [...document.querySelectorAll('div[role="listitem"]')].filter((li) => li.querySelector('[role="heading"]'));

    for (const item of items) {
      const heading = item.querySelector('[role="heading"]');
      const base = {
        label: GF.cleanLabel(heading.textContent),
        placeholder: "",
        name: "",
        element_id: "",
        aria_label: "",
        helper_text: helperText(item),
        kind: "text",
        options: [],
        required: !!item.querySelector('[aria-required="true"]') || /[*]\s*$/.test(GF.cleanText(heading.textContent)),
        max_length: null,
      };

      const radios = [...item.querySelectorAll('[role="radio"]')];
      const checkboxes = [...item.querySelectorAll('[role="checkbox"]')];
      const listbox = item.querySelector('[role="listbox"]');
      const input = item.querySelector(TEXT_INPUTS);
      const file = item.querySelector('input[type="file"]');

      if (radios.length) fields.push(choiceField(item, base, radios, "radio"));
      else if (checkboxes.length) fields.push(choiceField(item, base, checkboxes, "checkbox"));
      else if (listbox) fields.push(dropdownField(item, base, listbox));
      else if (input) {
        fields.push({
          descriptor: { ...base, kind: GF.kindOf(input), aria_label: input.getAttribute("aria-label") || "", max_length: input.maxLength > 0 ? input.maxLength : null },
          highlightEl: input,
          hasValue: () => input.value.trim() !== "",
          currentValue: () => input.value,
          apply: (value) => GF.applyText(input, value),
        });
      } else if (file || /upload/i.test(item.textContent)) {
        fields.push({
          descriptor: { ...base, kind: "file" },
          highlightEl: item,
          hasValue: () => false,
          apply: async () => ({ status: "review", reason: "Upload the file yourself" }),
        });
      }
    }
    return fields;
  }

  GF.adapters.googleForms = {
    name: "Google Forms",
    matches: () =>
      (location.hostname === "docs.google.com" && location.pathname.startsWith("/forms")) ||
      !!document.querySelector('form[action*="docs.google.com/forms"]'),
    extract,
    // Google Forms has no job description; the form's own description is the closest thing.
    jobDescription: () => {
      const header = document.querySelector('[role="list"]');
      const intro = header && header.previousElementSibling;
      return intro ? GF.cleanText(intro.innerText) : "";
    },
  };
})();
