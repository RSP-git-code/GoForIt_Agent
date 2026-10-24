# Metrics

Every evaluation result, with date, dataset size, model and numbers.

## 2026-10-03 — Phase 2: rule-based filling on test forms

- **Method:** `node extension/tests/run-harness.js` runs the content scripts in headless Chrome on each form in `test-forms/`, using the made-up profile `extension/tests/fixtures/sample-student.json`. "Correct" was checked by hand: each field got the right value, or was correctly flagged.
- **Model:** in-extension regex rules (`extension/content/rules.js`). No ML yet.

| Form | Fields | Filled | Review | Missing | Skipped | Handled correctly | Submitted? |
|---|---|---|---|---|---|---|---|
| Google Forms (TPO registration) | 19 | 15 | 3 | 1 | 0 | 19/19 | no |
| Greenhouse (classic) | 16 | 11 | 3 | 1 | 1 | 16/16 | no |
| Lever | 15 | 9 | 3 | 3 | 0 | 15/15 | no |

- Rules unit tests: 53 label → key cases, all passing (`extension/tests/rules.test.js`).
- **Caveat:** the test forms and the rules were written together, so these numbers are optimistic. Real forms with unusual wording are the real test; that's what the Phase 5–6 held-out set is for.

## 2026-10-04 — Phase 3: same test forms through the backend agent pipeline

- **Method:** `node extension/tests/run-harness.js` with the backend running. Same made-up profile as Phase 2.
- **Model:** Page Analyzer = rules (`backend/services/rules.py`); Mapper = deterministic; Matcher/Drafter/Verifier = stubs.

| Form | Agent path | Filled | Review | Missing | Skipped | Submitted? |
|---|---|---|---|---|---|---|
| Google Forms | analyzer > mapper > matcher > drafter > verifier > assemble | 15 | 3 | 1 | 0 | no |
| Greenhouse | same | 11 | 3 | 1 | 1 | no |
| Lever | same | 9 | 3 | 3 | 0 | no |
| Greenhouse, backend offline | none | 0 (page untouched, error shown) | | | | no |

- Results are identical to Phase 2, as expected: the logic moved, it didn't change. New: "Branch" picks "CSE (AI and ML)" when the profile has that specialization.
- Backend tests: 88 passing (rules 58 cases, option matching, Mapper, every graph route including verifier-retry and LLM-offline, endpoint, no PII in logs). Extension tests: 22 passing.

## 2026-10-04 — Yes/No questions answered from profile evidence

- **Why:** on a real Amazon form, "Do you have a Bachelor's degree?" (Yes/No) was rote-matched to the degree *name* field. Yes/No questions are now detected from their options and answered by topic + subject + evidence lookup (`backend/services/evidence.py`).
- **Paraphrase test set** (`backend/tests/test_evidence.py`): 22 differently-worded questions across 4 topics (degree level, language, tools/skills, work experience), all passing. The first run failed 4/22 (subjects like "SQL databases", "machine learning frameworks", "hands-on knowledge of LangChain"), which led to the generic-word and last-cue fixes.
- **Real page** (saved Amazon form, made-up profile): 4/4 questions handled correctly. English → Yes (evidence: languages); Bachelor's → left for the student (degree in progress); MS Office and Excel → left for the student (no evidence); resume recognised as already uploaded.
- **Caveat:** I wrote these paraphrases myself, so they're not a blind test. The classifier (Phase 6) and the LLM (Phase 9) should be measured on questions collected from real forms.

## 2026-10-04 — Non-LLM drafting agents

- Matcher picks the job-relevant project: RL job → satellite PPO project; LLM/RAG job → resume-scanner project (`test_drafting.py`).
- Verifier on planted false claims: catches an invented CGPA (9.8), invented skills (Kubernetes, Docker) and over-length drafts; accepts a draft that only uses profile facts. A set of 3 planted + 1 clean is tiny; the proper Verifier evaluation (recall and false-reject rate on a larger planted set) is Phase 9.
- Backend tests: 140 passing.

## 2026-10-05 — LinkedIn job-alert parsing (real email)

- One real LinkedIn alert ("Artificial Intelligence Engineer in India", 6 jobs): 6/6 jobs extracted with correct title, company and location; 0 footer blocks mistaken for jobs; all links reduced to the clean job URL (no `otpToken`/tracking). Fit with the real profile: 4 High, 2 Medium.
- Indeed (real alert, 2026-10-06, "ai/ml engineer in Hyderabad", 22 jobs incl. 4 sponsored): 22/22 extracted with title, company, location, snippet and signals (salary, "Easily apply", age); header and footer ignored; personalised links replaced by clean `viewjob?jk=` or, for sponsored jobs without an ID, a plain Indeed search link. 0 tokens stored.
- Fresher fit on both real alerts (28 jobs, real profile): 7 High, 4 Medium, 17 Low; 13 of the Low are senior/lead roles or ask for 4+ years, which the rating now explains.

## 2026-10-08 — Real Google Form (Grafyn AI campus application, 33 questions)

- Fetched the public form page (read-only) and ran the extension on it in headless Chrome with the made-up profile.
- **Before:** 12 filled, 10 review, 1 missing, 10 skipped, and **3 wrong fills**: institute email got the personal email, "Name of Current/Last Institution" got the student's name, "Grade-XII Math %" got the overall 12th %.
- **After:** 17 filled, 12 review, 0 missing, 4 skipped (position, availability ×2, certificate link: the student's own choices), **0 wrong fills**.
- New profile fields this needed: college email, resume link (Drive), JEE Main/Advanced percentile + rank, 12th maths %.

## 2026-10-09 — Real forms: Hitachi internship (Turiyaskills) + an "Additional Info" form

From the student's screenshots / PDF (no saved HTML), each problem was turned into a unit test with the exact label.
- **Wrong values fixed:** Master's fields filled with B.Tech data (5 fields); "Bachelor Percentage (if CGPA, convert to %)" got the CGPA; DOB "(YYYY/MM/DD)" came out as MM/DD/YYYY; "If others, mention your Nationality" got "Indian"; "CGPA (Aggregated till date)" was read as a date question.
- **Newly handled:** backlogs asked as Yes/No (0 → No), "open for any location across India", current/permanent resident state and city, hometown, "Profile Summary/Highlights", "Final percentage/year", numbered options ("a. Yes", "b. Female").
- Regression: test forms and the Grafyn Google Form unchanged (Grafyn 17 filled / 12 review / 0 missing / 4 skipped). 225 backend tests pass.

## 2026-10-11 — Phase 5: field classifier dataset + rules baseline

- **Data:** 822 real fields from 35 sources (720 from 27 companies via Greenhouse's public API, 102 from saved forms), all labelled and checked; + 317 hand-written Indian campus wordings; + 1,815 augmented variants (train only). **2,799 examples, 81 labels.** Details: `ml/classifier/README.md`.
- **Split by source:** test 191 (3 real forms of mine + 6 held-out companies), val 72 (4 companies), train 2,536. Only 11/191 test questions appear word-for-word in train.
- **Rules baseline** (`backend/services/rules.py`, the current Page Analyzer):

| Split | Fields | Rules correct |
|---|---|---|
| val | 72 | 59 (81.9%) |
| test | 191 | 168 (88.0%) |
| test, my 3 real forms only | 44 | 44 (100%; the rules were tuned on these, so not a fair test) |

- **Most common rule misses (test):** "Describe your experience with X" text boxes taken as the skills list instead of a written answer (5); free-text vs Yes/No vs none confusions; salary and start-date questions phrased unusually.
- **Label review found a real bug:** "Are you authorized to work in the United States?" / "Need H-1B sponsorship?" were answered from the India profile (Yes / No), which would be false on a US form. Fixed in the rules (foreign country named → left for the student).

## 2026-10-11 — Phase 6 (first attempt): field classifier vs rules

- **Models:** `all-MiniLM-L6-v2` fine-tuned (mean pooling + linear head, 8 epochs, lr 5e-5, label smoothing 0.05, best epoch 5 by val macro F1; ~5 min/epoch on laptop CPU) and TF-IDF char n-grams + logistic regression. Data: Phase 5 dataset (2,536 train, of which 404 real).
- **Tuning on val** picked "classifier first, rules below confidence 0.3".

| | val acc | val macro F1 | test acc | test macro F1 | test acc, unseen wording (180) |
|---|---|---|---|---|---|
| Rules | 81.9% | 0.846 | **88.0%** | **0.897** | **87.2%** |
| TF-IDF + LR | 77.8% | 0.689 | 73.3% | 0.742 | 71.7% |
| MiniLM | 81.9% | 0.848 | 81.7% | 0.806 | 80.6% |
| MiniLM + rules fallback (chosen on val) | **86.1%** | **0.857** | 83.8% | 0.791 | 82.8% |

- **Result: the classifier does not beat the rules on test** (fixed 16 fields, broke 24). The Phase 6 "done" check is not met, so it is **switched off** (`meta.json` strategy "off"); GoForIt keeps filling with the rules. A rules-first variant (classifier only where the rules found nothing) was also worse on test (86.9% at threshold 0.9): where the rules find nothing, the right answer is usually "leave it" (21/24).
- **Why, as far as I can tell:**
  1. **Validation is too small** (72 fields, 4 companies): the val gain (+4 points) didn't hold on test.
  2. **Labels lean towards the rules:** I labelled by correcting the rules' first guesses, and 227/263 val+test labels equal the rules' draft. Borderline cases were settled the rules' way, which favours the rules.
  3. **Little real training data:** 404 real examples; the rest is augmentation and my hand-written wordings.
  4. Top confusions: "none" taken as yes_no_question (5), consent → none (3).
- **Next:** many more real questions (Greenhouse has thousands of boards), a larger validation set, fewer augmented copies, and a second labelling pass on test that doesn't start from the rules' guess.

## 2026-10-18 — Form Reader (local LLM for field answers): 3 models, two benchmarks

- **Setup:** Ollama 0.40.6 on the laptop CPU (i7-8665U, 16 GB, no GPU). Form Reader (`backend/agents/form_reader.py`): the model sees the page's questions + the profile as facts (no phone/email/address/DOB/category/reg no.), answers with a cited fact or null; a grounding check rejects answers the cited fact doesn't support. Made-up student profile, so nothing personal in the benchmark.
- **Benchmark A: this week's 25 problem questions** (`ml/llm/form_reader_bench.py`, 3 pages, 5 "leave it empty" traps). Biased towards the rules: I had just written rules for these exact questions.

| | Correct /25 | Invented (traps answered) | Seconds / page |
|---|---|---|---|
| Qwen3 1.7B alone | 16 | 2 | 44 |
| Llama 3.2 3B alone | 18 | 2 | 76 |
| Qwen3 4B alone | 18 | 2 | 99 |
| Rules + evidence engine | 24 | 0 | instant |

  All three models answered "authorized to work in the United States?" and "Indian passport?" from the India profile (wrong / unknown), so Yes/No eligibility questions stay with the evidence engine. All three chose LinkedIn for the "Profile / Evidence Link" after a coding-platform question (context miss).
- **Benchmark B: 138 unseen fields** (`ml/llm/unseen_bench.py`): the Phase 5 test split (held-out companies + my 3 real forms), checked labels, expected answer = the profile value for the checked label. The LLM only answers what the rules left empty, never Yes/No eligibility questions.

| | Correct /138 | Invented | Extra time |
|---|---|---|---|
| **Rules alone** | **129 (93.5%)** | **3** | 0 |
| Rules + Qwen3 1.7B | 126 | 8 | 62 s / page |
| Rules + Llama 3.2 3B | 123 | 10 | 92 s / page |

  The LLM fixed 1-2 fields ("Where are you currently located?", a salary in LPA). Read by hand, ~3 of its "wrong" answers were actually right (the scorer couldn't express "I can start immediately" or "Spring/Summer 2027"), but the rest were real inventions: conferences attended, "Already serving notice", ticking an "I agree" consent, "Yes" to a contract-role condition.
- **Decision:** the Form Reader is **not** used for normal field filling (see DECISIONS.md). The local LLM goes to free-text drafting (Phase 9), where rules can't help at all and the Verifier loop checks every claim.

## 2026-10-18 — Phase 9 (first runs): LLM Drafter + Verifier loop

- **Setup:** `ml/llm/draft_bench.py`, made-up student, models served by Ollama on the laptop CPU. Verifier = rule checks (length, numbers, concrete tools) + the same local model as judge.
- **Run 1 (judge accepted every claim it listed):** caught 10/10 planted lies but rejected **6/6 honest answers**; every real draft failed 3 times, so nothing reached the form. Causes: broad fields ("machine learning", "LLM") counted as invented skills, and the small judge flags almost anything.
- **Fix:** concrete tools only in the skills check; a judge claim counts only if it names something checkable that isn't in the profile (a name, a number, or a claim word: won, led, intern, certified, years...). Set B lies/honest answers were written after the fix.

| Judge model | Set A lies caught | Set A honest rejected | Set B (unseen) lies caught | Set B honest rejected |
|---|---|---|---|---|
| Qwen3 1.7B | 10/10 | 0/6 | 8/8 | 0/4 |
| Llama 3.2 3B | 8/10 | 0/6 | 6/8 | 0/4 |

- **Real drafts, read by hand (6 questions):** project and teamwork answers were fluent and specific, but **2 of the 4 accepted drafts contained invented details the Verifier passed** (a "predictive analytics model for student performance" that doesn't exist; the club "organising" Smart India Hackathon). Honest negations ("I have never managed direct reports") were wrongly rejected because of the word "managed"; "Why join Acme AI?" was always rejected because the company name isn't in the profile; "What are your key strengths?" got no draft (routed to the empty saved answer). 13-60 s per answer, up to 234 s with retries.
- **Status:** LLM drafting stays **off by default** until invented details are caught.

## 2026-10-18 — Phase 9 (third run): separate judge, fixes for negations / company names

- **Changes since the first runs:** honest negations ("I haven't...") pass; the company in the question counts as known; judge = Qwen3 1.7B for both writers; an empty "strengths" answer goes to the Drafter; the Drafter is told not to add features, data, users, events, results or roles to a project.
- **Verifier on planted lies (judge Qwen3 1.7B):** set A 10/10 caught, 0/6 honest rejected; set B (unseen) 8/8 caught, 0/4 honest rejected.
- **Real drafts, read by hand (6 questions):**

| Writer | Accepted | With invented details (passed the Verifier) | Seconds / answer |
|---|---|---|---|
| Qwen3 1.7B | 6/6 | 2-3 ("implemented a vector database", "collaborated with team members", a "student performance" project) | 9-25 |
| Llama 3.2 3B | 4/6 (1 rejected, 1 no draft) | 2 ("collaborated with faculty and industry professionals", "used PyTorch for the RAG model") | 21-106 |

  Honest trap answers were good ("I have not deployed any ML models to production at scale... [what I have built instead]").
- **Conclusion:** the Verifier reliably catches clear false claims (awards, companies, certifications, numbers, languages, years) but not fluent invented detail; both small models embellish about a third of their answers. Writer set to Qwen3 1.7B (faster, no worse). LLM drafting stays **off by default**; the fix for embellishment is Phase 8 (fine-tune on faithful answers), measured with this same benchmark.
