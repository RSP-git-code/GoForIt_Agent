# Design decisions

A short log of design choices and the reasons for them.

## 2026-10-03: Python 3.11 for the backend
LangGraph and the `X | None` type syntax in the spec need Python 3.10 or newer. 3.11 is well supported by PyTorch and Transformers. Fine-tuning with Unsloth runs on Colab or Kaggle, so the local version doesn't constrain it.

## 2026-10-03: Backend bound to 127.0.0.1 only
Profile data (marks, phone, email) must never leave the machine. The extension reaches the backend through `host_permissions`, so no CORS middleware is needed for extension pages.

## 2026-10-03: Backend calls will go through the extension, not the page
In MV3, a content script's `fetch` is subject to the host page's CORS rules. From Phase 3 on, the content script will send messages to the background service worker, and the service worker will call the backend.

## 2026-10-03: Profile editor opens in a full tab, not inside the popup
A Chrome popup closes as soon as it loses focus, which would throw away unsaved edits, and opening the file picker for "Import JSON" can close it too. The schema has about 60 fields, too many for a popup. The popup shows a summary and an "Edit profile" button that opens `popup/profile.html` as the extension's options page.

## 2026-10-03: The editor form is built from the schema
`shared/profile-schema.js` is the single source of truth. The editor generates inputs from it, and `normalizeProfile()` cleans anything loaded or imported (drops unknown keys, converts types, fills defaults). Adding a field to the schema adds it to the editor automatically.

## 2026-10-03: Content scripts are injected on click, not on every page
The extension uses `activeTab` + `scripting` instead of `content_scripts` with broad host permissions. Nothing runs on any page until you click "Fill this page", and only on that tab. This enforces rule 2 (act only when the user asks) by construction, and Chrome shows no "read all your data on all websites" warning.

## 2026-10-03: Every click goes through `safeClick()`
Filling Google Forms needs clicks (custom radio, checkbox and dropdown widgets). `GF.safeClick` only allows radios, checkboxes, options and listboxes, and throws on anything inside a button or link. A static test (`never-submit.test.js`) fails if any script calls `.submit()` or `.requestSubmit()`, fires submit or keyboard events, or calls `.click()` outside `safeClick`. Each test form has a tripwire that turns the page red if it's ever submitted.

## 2026-10-03: Consent and declaration checkboxes are never ticked
Even with the full profile available, "I declare the above is true" is a statement the student has to make themselves. These are always flagged yellow.

## 2026-10-03: Adapters are thin; extraction is mostly generic
Greenhouse and Lever forms are standard HTML, so their adapters reuse the generic extractor and only add site detection and job-description lookup. Google Forms gets a real adapter because its widgets are ARIA divs (`role=radio/checkbox/listbox`), not native inputs. Selectors use roles and ARIA attributes, not Google's CSS class names, which change often.

## 2026-10-03: Field descriptors are plain data
The extractor produces DOM-free descriptors (label, placeholder, name, id, aria-label, helper text, kind, options). The same objects will be sent to `/run-fill` in Phase 3 and become classifier training text in Phase 5.

## 2026-10-04: Python is the single source of truth for rules and option matching
Phase 2's JS rules were ported to `backend/services/` and the JS copy was deleted. The extension now only extracts fields and applies the plan; it finds the option the Mapper chose by exact text. Two copies of the rules would drift, and the Phase 6 classifier (Python) needs the same rules as its baseline.

## 2026-10-04: The extension talks to the backend only through the background service worker
Content scripts run under the page's origin and CORS. `background.js` uses `host_permissions` for `127.0.0.1:8000`, reads the profile from `chrome.storage.local`, and adds it to the request, so page scripts never see the profile.

## 2026-10-04: Draft branch decided per run, with a trace
Routing uses LangGraph conditional edges, and every node appends to `trace` (via an `operator.add` reducer). The response returns it, so tests assert the exact path (e.g. "drafter ran 3 times then assemble"), and the demo can show which agents ran.

## 2026-10-04: Drafter/Verifier are stubs with swappable functions
`drafter.write_draft` and `verifier.check_draft` are plain module functions. Tests replace them to simulate hallucinated drafts and rejections, so the retry loop and red-flag fallback are tested now, before any LLM exists.

## 2026-10-04: Degree start/graduation month added to the profile
Workday and Oracle ask for education "From/To" as month + year. Added `start_month` / `graduation_month` ("01"–"12") next to the existing year fields, so old profiles stay valid. A bare "Start date" is not mapped (on job forms it usually means availability); site adapters will provide the education context in Phase 3b.

## 2026-10-04: College names: saved aliases first, abbreviations only as a yellow guess
College dropdowns list the same place many ways ("VIT-AP", "Vellore Institute of Technology", "…, Amaravati"). The Mapper tries the college, the university and every saved alias; only an exact match is green. Otherwise it scores options by shared words and initials ("VIT"); a single best option is filled yellow, and a tie between campuses fills nothing and asks the student to choose. Guessing the wrong campus silently would be worse than asking.

## 2026-10-04: Resume upload moved up; Inbox agent added as Phase 3c
Every platform I apply on asks for a resume, and sites like Workday and Keka parse it themselves, so upload is built together with the Workday adapter (upload first, let the site fill, then fill only the gaps). Phase 3c adds an Inbox agent: Gmail read-only (`gmail.readonly`) → company/role/deadline/link extraction (rules + local LLM) → a local `.xlsx` tracker → Microsoft To Do reminders. Read-only mail is a hard rule (rule 8): links are only recorded, never opened, so job boards are never automated.

## 2026-10-04: Yes/No questions are answered from evidence, not mapped to fields
A Yes/No dropdown is detected from its options, not its wording. The answer comes from a topic (degree level, language, tool/skill, work experience), a subject pulled from the question, and a search of the profile (skills, project tech and summaries, experience, certifications, languages, education). "Yes" is given only with evidence, and the reason names it ("Found 'Python' in your skills"). Missing evidence is flagged, never turned into "No". The exception is a work-experience question when the profile lists no experience, which is answered "No" and always flagged. A degree in progress is never claimed as completed. This generalises across wordings without a rule per question, and it's the same "answer only from profile facts" principle the Verifier will enforce on LLM drafts.

## 2026-10-04: Saved real pages are tested as script-free snapshots
`test-forms/raw/` (git-ignored, may contain personal data) holds pages saved from real sites. Offline, their own JS re-renders or wipes the form, so the harness serves them with `<script>` tags removed: `node extension/tests/run-harness.js "raw/<file>.html"`.

## 2026-10-04: Existing values are never overwritten, but differences are flagged
Workday, Keka and Amazon fill fields from your uploaded resume, and their parsers make mistakes (an address came out as "Kadapa, Hyderabad"). GoForIt still never overwrites a filled field, but if the value differs from the profile, the field turns yellow with both values ("Page already has X; your profile says Y"), so a wrong value can't hide behind green. The profile editor also turns off Chrome's own autofill, so its suggestions don't leak into the profile.

## 2026-10-04: Non-LLM Matcher/Drafter/Verifier before the fine-tuned model
Motivation questions ("Why would you like to join RingTrunk?") are on almost every form, so a first version ships now without waiting for Phase 8. The Matcher ranks projects by shared technologies and keywords with the job description. The Drafter fills templates only with profile facts: degree line, the best project's own summary, and the matched skills. The Verifier rejects anything too long, or containing a number or technology not in the profile. These agents see only `safe_profile()` (no contact details). This keeps the pipeline honest by construction and gives the LLM version a baseline to beat: does the fine-tuned model write better answers *and* still pass the same Verifier?

## 2026-10-04: Relocation, experience and education boxes answered from the profile
"Relocate to X?" is Yes (yellow, with the reason) when X is in the preferred locations or is the current city; otherwise the saved Willing-to-relocate answer is used; otherwise it's flagged. Years of experience is computed from Experience entries (0 for a fresher; "Fresher" options match 0). "Education or relevant training" boxes get a summary built from degree, school results and certifications.

## 2026-10-05: Resume upload: attach first, let the site parse, then fill the gaps
The resume PDF is stored in `chrome.storage.local` separately from the profile (exporting the profile JSON doesn't drag the PDF along). On Fill, it's attached only to boxes classified as resume/CV, via `DataTransfer` (the drag-and-drop file container, the standard way to set a file input from script), and only if the box's `accept` list allows the file type and the site doesn't already have a resume. Resume boxes are handled first, then GoForIt waits ~2.5 s so sites that read the resume (Keka, Workday) can fill fields, then fills only empty fields and flags any differences. Many sites upload the file to their server as soon as it's attached, so the popup has an "Attach my resume" switch.

## 2026-10-05: CAPTCHAs are never touched, and the panel says so
Companies add CAPTCHAs to stop automated submissions. GoForIt never submits, so CAPTCHAs don't block it, and rule 3 forbids solving them. Any field that looks like a CAPTCHA (reCAPTCHA, hCaptcha, Turnstile, "enter the characters shown") is excluded from extraction, CAPTCHA frames are skipped entirely, and the panel reminds the student to solve it before submitting.

## 2026-10-05: Employment and offer questions answered from the profile
"Are you currently employed / partnered / associated with any company?" is No when no experience entry is ongoing (green, with the reason). "Have you worked for X before?" checks the experience list. "Already placed / holding an offer?" comes from a new profile field (`preferences.has_job_offer`), because that can't be inferred.

## 2026-10-05: Inbox reads only LinkedIn and Indeed job alerts; GoForIt never fills on job boards
The job emails I care about are LinkedIn and Indeed alerts. Reading my own Gmail (read-only) is not job-board automation, but opening their links would be, so links are only recorded. Alerts list many jobs and carry no deadline or full JD, so each job becomes its own row, and the fit score uses only the title and snippet. As a hard guard for rule 2, the extension refuses to fill forms on linkedin.com / indeed.com / naukri.com (e.g. Easy Apply) and says why; it works as usual on the company's own application site.

## 2026-10-05: Job-alert links are stored clean; alert fit is a title rating
LinkedIn alert links carry tracking IDs and an `otpToken` (a one-time sign-in token). The parser keeps only `https://www.linkedin.com/jobs/view/<id>/` (Indeed: `viewjob?jk=<id>`), and the footer with the recipient's name is ignored; tests assert neither leaks. Alerts give only a title, so "Fit" is High/Medium/Low from terms in the profile itself (specialization "AI and ML", skills, project tech, with AI/ML ↔ artificial intelligence/machine learning), and it names the matched terms.

## 2026-10-06: Apply reminders in Google Calendar, not Microsoft To Do; High/Medium only; one event per morning
Microsoft To Do is only reachable through Graph, which needs an Azure app registration; personal accounts can no longer register apps without an Azure account (card verification) or a work/school tenant, and using the college tenant would collide with the TPO's account rules. The spare Google account's project already exists, so reminders go to its Google Calendar (`calendar.events` scope; mail stays `gmail.readonly`). Only High/Medium-fit jobs still marked New get a reminder, once each (event id stored in the tracker). Ten matching jobs shouldn't mean ten 9 AM notifications, so by default there's one "Apply to N jobs" event per morning listing them best-first with links; later runs that day add to it (`--per-job` for one event per job).

## 2026-10-06: "✓ Applied / ✗ Expired" links inside the calendar reminder
Each job line in the morning event has two links to the local backend (`GET /inbox/mark`). A click sets that job's Status in the Excel and re-renders the event from the tracker (struck-through job, updated "Apply to N jobs" / "All done"). Links are HMAC-signed with a random key in Documents\GoForIt, so a web page can't forge a request to the local server, and only these two statuses can be set this way. Event text is always rebuilt from the tracker (never appended), so `--refresh` can sync edits made in Excel. Limit: the backend runs on the laptop, so the links work from the laptop's browser, not the phone.

## 2026-10-06: Daily auto-scan via Windows Task Scheduler, not a background service
A resident process would cost memory all day for a job that takes ~10 seconds. The scheduled task runs `pythonw -m app.inbox --scheduled` at 8:30 AM (before the 9 AM reminder), at low priority, only when online, killed after 5 minutes, and at next logon if the laptop was off. Scheduled runs never open a browser: if Google's sign-in has expired (apps in "Testing" get 7-day tokens; publishing the app removes that), the log says to double-click `check-jobs.bat` once.

## 2026-10-06: Fit checks the degree a role is meant for
"Research Intern (PhD), Storage Systems for AI" matched AI and was rated Medium. Titles (and clear snippet phrases like "pursuing a PhD") that target a higher degree than the profile's (PhD, Master's/M.Tech/MBA/postgraduate) now make the fit Low with the reason ("for PhD students"). The profile's own degree decides, so the same role is fine for an M.Tech profile. Each run also re-renders recent calendar events, so jobs that became Low leave the reminder. On the real tracker (54 jobs) this flagged exactly the 3 PhD internships and nothing else.

## 2026-10-06: Scam jobs: learn from the student's own "Scam" marks, plus red flags in the alert text
GoForIt can't verify a company by visiting its page (rule 2), so it uses two signals it already has. (1) A "⚑ Scam" link in the reminder and a Scam status in the Excel; every company marked Scam is remembered (names compared without "Pvt Ltd"/"Private Limited" etc.), so its other and future jobs are rated Low, get no reminder, and leave existing events. (2) Red flags in Indeed snippets: asking for a fee or deposit, WhatsApp/Telegram contact, "earn ₹X per day", "no interview". These make the job Low with the reason shown; it's a warning, not a verdict. LinkedIn alerts have no snippet, so there only (1) applies.

## 2026-10-08: "Other" is only a fallback for years and numbers
A dropdown of years 2020–2026 + "Other" with a 2027 graduation now picks "Other" (yellow). The fallback is limited to numeric values: for a Gender question with "Male / Other", picking "Other" for a female profile would be wrong data, and a test guards that.

## 2026-10-09: When a label names both CGPA and %, the first one mentioned is what it wants
"Bachelor Percentage (if marks in CGPA, please convert to %)" wants a percentage; "CGPA (7/10 if CGPA, 70 if %)" wants the CGPA. Using the first mention handles both. A CGPA is never sent as a percentage: without a saved percentage equivalent the field is red ("only CGPA is saved; conversion formulas differ by university").

## 2026-10-09: Master's/PG fields are left empty for a bachelor's student, and conditional follow-ups are skipped
"Master Degree/Percentage/Year/Branch/College" are optional for undergraduates; filling them with B.Tech data was wrong. They're now skipped with a reason. Questions starting "If others…", "If yes…", "If no…" depend on another answer, so GoForIt leaves them to the student.

## 2026-10-09: "Entry level, 3+ years" postings: check what the email shows, let the student mark the rest
LinkedIn alert emails carry no job description, and GoForIt can't open LinkedIn pages (rule 2), so a mislabelled "entry level" job asking for 3+ years is usually invisible in the email. GoForIt now checks years in the title ("Python Developer (3+ Yrs)") and in any description line LinkedIn includes, as it already did for Indeed snippets. For the rest, the reminder has a "⏳ Needs experience" link that marks just that job "Not eligible" (per job, not per company, since the same company may also hire freshers). Setting LinkedIn's own alert filter to Internship + Entry level reduces the noise at the source.

## 2026-10-09: Sort reminders by "fresher-friendly" and learn from "Needs experience" clicks
Since the email rarely states experience, GoForIt ranks instead of guessing: titles with Intern, Graduate, Trainee, Fresher, Junior, Associate, Entry level, Apprentice, Campus or "2027 batch" are tagged "Fresher-friendly" and listed first in the 9 AM reminder. Other jobs go below under "Experience not shown in the alert", and jobs that name years are Low. A company where the student marked 2+ roles "Needs experience" and applied to none has its later non-fresher titles rated Low. The threshold is 2 because one mislabelled posting shouldn't hide a whole company, and intern/graduate titles from that company still come through. A new Excel "Experience" column shows the tag.

## 2026-10-09: "Start/End of Course" date pickers get the 1st of the saved month
The profile stores the degree's month and year, not a day. When a box wants a full date ("16 June 2014" as placeholder, or DD/MM/YYYY), GoForIt fills the 1st of that month in the same style ("1 June 2023") and flags it yellow, rather than leaving it empty or guessing a day silently.

## 2026-10-11: Classifier training data from Greenhouse's public job-board API
Saving pages by hand gave 102 fields from 8 forms, only 3 of them real, far from the 1,500 needed. Greenhouse publishes every job's application questions as JSON for companies' own career pages (no login, no HTML scraping, nothing personal sent), so ~25 companies give hundreds of real, differently worded questions in a few minutes. They are mostly Western ATS wording, so Indian campus phrasing ("Tenth %", "Mob No.") comes from my own saved forms plus hand-written variants. To keep the score honest, the test set is split by source and built from my own real forms and companies never seen in training.

## 2026-10-11: Synthetic data for training only; split by source form
Indian campus questions (Class 10/12 %, CGPA, backlogs) are rare on Greenhouse, so I hand-wrote wordings and augmented them (abbreviations like "SSC"/"Mob No.", typos, case, missing hints). They go into training only: if they were in the test set, the score would mostly measure whether the model learned my phrasing. The split is by source form or company, never by row, because the same company asks the same question on every job, and a row-level split would let the model see the test question in training.

## 2026-10-11: The classifier ships switched off until it beats the rules
The first MiniLM classifier scored 83.8% on the held-out test set against 88.0% for the rules, even though it looked better on the (small) validation set. Using it would have made filling worse on real forms, so `meta.json` sets it to "off" and the Page Analyzer uses the rules alone. The code path (model-first / rules-first with a tuned threshold, and the rules' safety guards applied to every model prediction) is in place and tested, so turning it on is a config change once a retrained model wins. Reporting a model that lost is more useful than tuning on the test set until it wins.

## 2026-10-14: GoForIt may click "Add Education", and nothing else
On Oracle Cloud the education step is empty until "Add Education" is clicked, so GoForIt found nothing and the panel just said "Skipped 1", which made more work instead of less. Clicking an Add button doesn't submit or advance anything, so it's now allowed through a separate, narrow function (`GF.clickAddSection`): only buttons named like "Add Education / Qualification / Degree / School", once per Fill, only when no education boxes are showing, and refused if the button could submit (type="submit", or a `<button>` with no type inside a form, which HTML treats as submit). "Add Experience" is never clicked (no experience in the profile), nor Save / Next / Submit. When nothing can be filled and an Add button can't be clicked safely, the panel says which button to click. Both cases are in the headless-Chrome harness.

## 2026-10-14: Send focus/leave events ourselves, plus a re-check fallback
Workday showed red "required" errors on boxes GoForIt had filled, until the student clicked each one. Workday validates a box when you leave it (blur/focusout). GoForIt called `el.focus()`/`el.blur()`, but Fill is clicked in the extension popup, so the page doesn't have keyboard focus and Chrome ignores those calls: the "left the box" event never happened. Now `GF.setNativeValue` also dispatches focus/focusin and blur/focusout events directly, and after filling, any box that has a value but is still `aria-invalid="true"` gets the signals once more. A harness page reproduces it (page without focus: old code left 3 red boxes, new code 0).

## 2026-10-18: The local LLM doesn't fill normal fields; it drafts written answers
I built a Form Reader (the LLM reads the whole page and answers from profile facts, citing each fact, with a grounding check) because rule matching kept missing context. Tested on 138 questions the rules had never been tuned on, rules alone got 129 right with 3 invented answers; adding Qwen3 1.7B or Llama 3.2 3B for the leftovers fixed 1-2 fields but invented 5-7 more (conferences attended, "already serving notice", ticking a consent box) and added a minute per page on this CPU. For a tool whose first rule is "never invent profile data", that trade is wrong. So field filling stays rules + evidence engine (Yes/No eligibility answers never go to the LLM), and the LLM's job is free-text drafting (Phase 9), where rules can't write anything and the Verifier checks every claim with retries. The Form Reader code and both benchmarks stay, so a fine-tuned model (Phase 8) can be re-tested with one command.

## 2026-10-18: AI drafts are opt-in and arrive after Fill
On the laptop CPU each AI answer takes 10-30 s (up to a few minutes with retries), and the drafts still contain invented details about a third of the time. So Fill never waits for the model: it fills everything else at once, then (only if the student turns on "AI drafts") requests one draft at a time from `POST /draft` and places each in its box when ready. A draft never overwrites text the student typed, and it is always yellow with "check every sentence". This keeps the safe path fast and makes the risky part visible and optional, while the drafts get better through Phase 8 fine-tuning.

## 2026-10-19: GoForIt operates site-drawn dropdowns (but still never buttons)
On SAP SuccessFactors (HSBC), Oracle and IBM, most choices are drawn by the site: a box with role="combobox" whose options (role="option") appear only after it's pressed. GoForIt recognised them but could only say "Pick Female from the list", so on those forms it filled almost nothing beyond names and email. It now presses the box (mousedown + click, since widgets open on either), waits for the options, types to filter searchable ones, clicks the matching option and checks the box shows it; otherwise it stays yellow as before. Only the dropdown box and its options can be pressed: `GF.press` refuses anything inside a button or link, so rule 1 is unchanged (Workday's <button>-based dropdowns stay manual). Placeholder values like "No Selection" now count as empty, so those boxes are no longer reported as "already filled". Sensitive questions (disability, ethnicity, D&I consent) stay untouched. Tested in the harness on SAP-style, div-based and searchable dropdowns.

## 2026-10-20: Optional diversity answers, and a second look after filling
Diversity questions (D&I consent, ethnicity, disability, veteran status) were always left for the student. That's still the default, but the student asked to answer them the same way every time, so the profile has an optional "Diversity answers" section: empty = untouched, filled = used for those dropdowns only (free-text accessibility questions are never filled), never passed to the AI. Ethnicity lists differ by country, so the saved wording is tried first and then broader equivalents ("Asian or Asian British - Indian", "Indian", "South Asian"), marked yellow when not exact. On SAP SuccessFactors those questions stay disabled until consent is answered, so after filling GoForIt now looks at the page once more and fills fields that appeared or unlocked because of its answers (one extra round, never more).

## 2026-10-20: Agent Octo, a job-fit coach in a side panel (deterministic first)
Reminders list jobs, but deciding which are worth applying to still meant reading every vague description. Agent Octo (Chrome side panel, opened from the popup) takes a pasted job description and returns: skills the job requires vs nice-to-have, which ones the profile already shows (and where), hard requirements a course can't fix (degree level, years, batch, CGPA/percentage cut-offs) checked against the profile, and for each learnable gap a rough effort, free resources and a "show it" tip tied to the student's own project. It's rule-based on purpose: the resources come from a hand-curated list because small local models invent links; an LLM-written learning plan can come later on top. The description is pasted by the student, not fetched: GoForIt still never opens LinkedIn/Indeed pages (rule 2), and automatic lookup on public job boards was rejected because coverage for startups and Workday/Oracle employers would be low. Kept deliberately small so it doesn't pull focus from form filling.

## 2026-10-20: Octo uses tools (calendar, tracker), and free courses come first
Octo answered like a chatbot: "I can recommend YouTube channels…" with nothing behind it. Now the common requests are handled by tools, not the LLM: today's best jobs come from the Excel tracker (open High/Medium, newest first, "asks N+ years" flagged); "add this plan to my calendar" writes one recurring weekday study block per missing skill into the spare Google Calendar (tagged, so a second request asks before replacing). Opening job links is still not something Octo does: they're LinkedIn/Indeed pages (rule 2). Resources now lead with free video courses (freeCodeCamp, a topic-specialist channel), then Coursera (audit free), then a web search for more, all as search links opened by the student, so nothing points to a dead or invented video and the backend makes no web requests. Suggestion buttons moved inside the chat so they never cover a long answer.

## 2026-10-20: Select text → Octo (instead of copy-paste), only when the student asks
Copying a job description (Ctrl+A, Ctrl+C, paste) was the slowest step. Now the student selects text on the page and right-clicks "Ask Agent Octo about this" (Chrome passes the selected text to the extension; no script runs on the page) or presses Alt+Shift+O (activeTab reads the current selection once). The text goes to the side panel via chrome.storage.session (memory only). A whole description is checked at once; a short snippet goes into the box for a question. A Gemini-style panel that watches every selection automatically was rejected: it would need a content script on every site at all times, reading pages the student never asked about. This works on job-board pages too, because it is the same as the student copying their own selection: no automation, scraping or link-following (rules 2 and 8 hold). Needs the "contextMenus" permission.

## 2026-10-20: Upload a job PDF to Octo (pdfplumber), and a day/night switch
Some job descriptions only arrive as PDFs (e.g. a 5-page Malomatia JD with tables), where selecting everything is awkward. Octo's 📎 button sends the file to the local backend (`POST /octo/read-file`, base64 inside JSON so no multipart dependency is needed), which pulls out the text with **pdfplumber**, the library already planned for resume parsing (Phase 4). Nothing is stored or logged but the page count. Scanned PDFs have no text and there is no OCR, so Octo says so and asks for selected or pasted text. Dark mode used to follow only the Windows setting; a 🌙/☀️ button now overrides it (remembered per panel), and the night sea has dim rays and glowing bubbles and jellyfish.

## 2026-10-20: Octo's study plan is state, not chat text
In a real chat Octo ignored "I don't want Airflow", "LangChain in 2 days, PySpark 5 days, 20-24 October", then the LLM said "I adjusted the plan" when nothing had changed, and "which dates did you add?" repeated the old plan. The plan is now a small object (`agents/octo_plan.py`): topics, days, dates, study hour, and whether it is in the calendar. The side panel sends it back with every message. Plain-word edits are parsed without AI (skills named or excluded, "N days/weeks" after a skill, date ranges, "at 7 pm"). When the days don't fit the dates, the longest topic is shortened and Octo says so, offering "Keep the full days". "Did you change/add it?" and "which dates?" are answered from the plan and from the calendar itself, and the LLM is told it can't do actions, so it can no longer claim it did. Calendar events are one daily series per topic. Dark mode is now bioluminescent: Octo, the student's messages and the buttons glow teal instead of red.

## 2026-10-22: Enter only inside a picker's search box (rule 1 exception)
Workday's skills and field-of-study pickers search only when Enter is pressed, so GoForIt could never fill them and listed the skills instead. Approved exception: `GF.pressEnterToSearch` may simulate Enter, but only in a picker's search box (combobox / searchbox / autocomplete input, or Workday's `searchBox`), only right after typing a value, and only when no results are showing (so Enter can't accept a highlighted suggestion). A script's key press is untrusted, and browsers never submit a form because of one; only the site's own search code reacts. The never-submit test still forbids Enter everywhere else and checks that this single function keeps its search-box guard. A test page records any Enter in an ordinary box. Workday's result items (`promptOption`, often without `role="option"`) were added to the clickable choices.
