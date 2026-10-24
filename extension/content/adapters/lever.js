// Lever adapter (jobs.lever.co). Like Greenhouse, the form is standard HTML:
// each question is li.application-question with the label in
// .application-label, which the generic "preceding text" lookup already finds.

(() => {
  const GF = (globalThis.GoForIt = globalThis.GoForIt || {});
  GF.adapters = GF.adapters || {};

  GF.adapters.lever = {
    name: "Lever",
    matches: () =>
      location.hostname === "jobs.lever.co" ||
      !!document.querySelector("form[action*='lever.co'] .application-question"),
    extract: () => GF.genericExtract(document.querySelector("#application-form, form") || document),
    jobDescription: () => {
      // querySelectorAll returns each element once, even if it matches several selectors.
      const parts = [...document.querySelectorAll(".posting-headline, .posting-description, .section-wrapper.page-full-width")];
      return GF.cleanText(parts.map((p) => p.innerText).join("\n"));
    },
  };
})();
