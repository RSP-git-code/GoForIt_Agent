# Field classifier dataset (Phase 5)

Predicts which profile key a form field asks for (e.g. `education.class_12.percentage`),
or `free_text_question`, `yes_no_question`, `consent`, `resume_file`, `none`.

## Rebuild it

```bash
node extension/tests/run-harness.js --dump ml/classifier/data/descriptors.jsonl   # fields of every saved form
python ml/classifier/collect_greenhouse.py                                        # Greenhouse public API questions
backend/.venv/Scripts/python ml/classifier/build_dataset.py draft                 # first-guess labels -> data/labels.csv
#   ...check labels.csv by hand (Excel), then:
backend/.venv/Scripts/python ml/classifier/build_dataset.py build                 # -> data/fields.jsonl
```

## Files

| File | What |
|---|---|
| `data/descriptors.jsonl` | Field descriptions from saved forms (`test-forms/`, `test-forms/raw/`): labels, attributes, option texts. Never what was typed. |
| `data/greenhouse.jsonl` | 720 application questions from 27 companies via Greenhouse's public job-board API (2026-10-11). |
| `data/labels.csv` | One row per field: classifier input text, the rules' first guess, the checked label. All 822 rows checked; 43 borderline rows checked by the owner. |
| `variants.py` | Hand-written Indian campus wordings ("SSC Marks (%)", "Mob No.", "No. of Current Arrears") and the augmentation. |
| `data/fields.jsonl` | The dataset: `text`, `label`, `source`, `split`, `origin` (real / handwritten / augmented), `rules` (baseline prediction, real rows only). |

## Input text

One string per field, in a fixed order, built the same way at runtime:

```
Grade-XII Board Name | section: Academic Details | type: select | options: CBSE, ICSE, State Board
```

## Split (by source form, never by row)

| Split | Sources | Examples |
|---|---|---|
| **test** | My 3 real forms (Grafyn Google Form, IBM, Amazon) + 6 held-out companies (Groww, Druva, HackerRank, Duolingo, Okta, Reddit) | 191 |
| **val** | Rubrik, Coursera, Twilio, Stripe | 72 |
| **train** | The other 18 companies, my synthetic test forms, hand-written wordings, and augmentation | 2,536 |

- Augmentation and hand-written wordings are **train only**, so the test score is on real questions only.
- Only 11 of 191 test questions appear word-for-word in training (e.g. "Phone | name: phone").
- Duplicates within a split are removed (case-insensitive text + label).

## Known limits

- My 3 real forms were also used to build the rules (44/44 correct), so they can't show the classifier improving. The held-out companies are the meaningful part of the test.
- Few real Indian campus forms in test: most Class 10/12, CGPA and backlog examples come from hand-written wordings. Saving more real TPO forms (Ctrl+S, before filling) and moving them into test is the best way to improve the score's meaning.
- One labeller (Claude), with the owner checking the borderline rows. Label policy: a field's label is what a correct answer comes from, not whether GoForIt can answer it. Questions about a named foreign country's work authorization/visa are `yes_no_question`, not the India profile answer.
