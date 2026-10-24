# Test forms

Offline copies of real application-form layouts, for repeatable tests. All companies, jobs and data are made up.

| File | Layout |
|---|---|
| `google-form.html` | Google Forms TPO registration (custom radio, checkbox and dropdown widgets) |
| `greenhouse.html` | Classic Greenhouse job board (`boards.greenhouse.io`) |
| `lever.html` | Lever application page (`jobs.lever.co/.../apply`) |
| `shadow-dom.html` | Inputs inside web components' shadow DOM, like SAP UI5 (SuccessFactors) |
| `sections.html` | Labels that only make sense with their section heading (Workday-style "URL" under "Websites", "From/To" under "Education") |

Every form loads `tripwire.js`. If anything submits the form or clicks its submit button, a red **SUBMITTED** banner appears and `window.__goforitSubmitted` becomes `true`. GoForIt must never trigger it.

## Open them in Chrome

Serve the folder over HTTP. Chrome extensions can't touch `file://` pages unless you turn on a special setting.

```bash
cd test-forms
python -m http.server 5500
```

Then open http://localhost:5500/google-form.html (or `greenhouse.html`, `lever.html`) and click **Fill this page** in the GoForIt popup.
