// Greenhouse adapter (boards.greenhouse.io, job-boards.greenhouse.io).
// The form itself is standard HTML, so field extraction reuses the generic
// adapter. This adapter adds site detection and the job description, which
// the Matcher/Drafter agents use later.

(() => {
  const GF = (globalThis.GoForIt = globalThis.GoForIt || {});
  GF.adapters = GF.adapters || {};

  GF.adapters.greenhouse = {
    name: "Greenhouse",
    // Hostname for the real site; the DOM check also recognises saved copies (test-forms/).
    matches: () =>
      /(^|\.)greenhouse\.io$/.test(location.hostname) ||
      !!document.querySelector("form#application_form, form#application-form[action*='greenhouse']"),
    extract: () => GF.genericExtract(document.querySelector("#application_form, #application-form") || document),
    jobDescription: () => {
      const el = document.querySelector("#content, .job__description, [class*='job-description']");
      return el ? GF.cleanText(el.innerText) : "";
    },
  };
})();
