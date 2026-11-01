# GoForIt's non-negotiable rules

These rules hold everywhere in the code, and the tests check the most important ones (for example, `extension/tests/never-submit.test.js` fails the build if any script could submit a form). Code comments refer to them as "docs/RULES.md rule N".

1. **Never submit a form.** GoForIt never clicks, triggers or calls a submit / apply / next-step button, never calls `form.submit()` and never dispatches submit events. You always review and submit the form yourself. Four narrow exceptions exist, each guarded and tested:
   - an **"Add Education"-type** button that only opens empty education boxes (once per Fill, only when none are showing, never a button that could submit);
   - **Enter inside a picker's search box** (e.g. Workday "Type to Add Skills", Field of Study) so the site shows its results, which GoForIt then clicks. Only in search/combobox inputs, only right after typing a value, only when no results are showing; never in an ordinary text box.
   - a **dropdown button** that only opens a list (Workday "Select One": `aria-haspopup="listbox"`, `type="button"`, or no type outside a form), then the matching option (approved 2026-10-30). Buttons that could submit, and buttons whose text is an action (Save, Next, Add, Delete...), are refused.
   - a **letter key-up inside a picker's search box** (SuccessFactors "No Selection" lists like Major, which filter only on a key-up), right after typing (approved 2026-11-01). Only a letter or digit, never Enter or any other key; only in search/combobox inputs.
2. **No job-board automation.** No logging in, no scraping behind logins, no bots on LinkedIn, Indeed or Naukri. GoForIt only acts on a page you opened yourself, when you click "Fill", and refuses to fill on those job boards (e.g. Easy Apply).
3. **No CAPTCHA solving or bot-detection bypass** of any kind. CAPTCHA boxes and frames are never touched.
4. **Profile data stays local.** The profile lives in `chrome.storage.local`; the backend listens on `127.0.0.1` only. Full profiles, phone numbers, emails and marks are never logged and never sent to any external server. The one outside lookup: for a "Why us? / What interests you about X?" answer (and when you ask Octo what a company does), the backend may read what the company does from its own homepage (only when the page you're filling links to it) or from Wikipedia's public API. Only the company's name or that link is sent, never anything from your profile, and the draft says where the company facts came from.
5. **No external LLM APIs.** All AI runs on your machine (our classifier and a small model served by Ollama).
6. **Never invent profile data.** If a field has no matching value in your profile, it's left empty and flagged for you.
7. **AI drafts are always marked as drafts** and highlighted for review, and must pass the Verifier agent first.
8. **Mail access is read-only and limited to LinkedIn and Indeed job-alert emails** (Gmail `gmail.readonly` scope). Mail is never sent, deleted, labelled or marked; links in emails are only recorded, never opened. Email contents are never logged and never leave the machine, except as calendar reminders (job title, company, location, fit and the job link).

## What the AI agents may see

Only non-sensitive parts of the profile go to the Matcher, Drafter and Verifier: skills, projects, education level and experience summaries. Never phone, email, address, date of birth, category, relatives or diversity answers.
