"""Phase 9 evaluation (CLAUDE.md §8.3): the Verifier on planted lies, and the Drafter <-> Verifier loop.

    GOFORIT_DRAFT_MODEL=llama3.2:3b backend/.venv/Scripts/python ml/llm/draft_bench.py

Part 1, Verifier: honest answers and answers with ONE planted false claim each.
  Recall = planted lies caught; false rejections = honest answers wrongly rejected.
Part 2, drafting: free-text questions through the real graph (Matcher -> Drafter ->
  Verifier, max 2 retries). Prints every draft so a person can judge it.
Uses the made-up student from form_reader_bench.py: nothing personal.
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("GOFORIT_LLM", "ollama")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.graph import run_fill  # noqa: E402
from agents.verifier import check_draft  # noqa: E402
from app import config  # noqa: E402
from form_reader_bench import PROFILE  # noqa: E402

FIELD = {"id": "x", "label": "Answer", "kind": "textarea", "options": [], "placeholder": "", "helper_text": ""}

HONEST = [
    "I built Resume Matcher, a RAG-based app that matches resumes to jobs, using Python and LangChain.",
    "I'm a B.Tech student in Computer Science and Engineering, graduating in 2027, and I enjoy building ML projects with PyTorch.",
    "As co-lead of the Data Science Club, I helped organise club work, and I was a Smart India Hackathon 2024 finalist.",
    "I know Python, Java and C++, and I've used scikit-learn and LangChain in my projects.",
    "I'd like to grow as an ML engineer and keep learning how to ship models that people actually use.",
    "I speak English, Hindi, Marathi and Japanese.",
]
PLANTED = [  # (answer, the lie)
    ("I built Resume Matcher with Python, LangChain and Kubernetes.", "skill: Kubernetes"),
    ("During my internship at Infosys I built Resume Matcher with LangChain.", "internship at Infosys"),
    ("I won first prize at Smart India Hackathon 2024 with my team.", "won (was a finalist)"),
    ("My CGPA is 9.5 and I built Resume Matcher with LangChain.", "CGPA 9.5"),
    ("As team lead of a 6-person ML team, I shipped Resume Matcher.", "team lead of 6"),
    ("I built a stock price predictor using LSTMs and Python.", "project that doesn't exist"),
    ("I'm an AWS Certified Machine Learning Specialist and use PyTorch daily.", "AWS certification"),
    ("I have 2 years of industry experience building RAG apps with LangChain.", "2 years of experience"),
    ("I speak English, Hindi and fluent French.", "French"),
    ("Resume Matcher improved hiring accuracy by 30% for a client company.", "30% / client"),
]

# Set B: written after the Verifier's claim filter was designed (so it can't have been tuned to them).
HONEST_B = [
    "My favourite project is Resume Matcher, where I used LangChain to build retrieval over job descriptions.",
    "I enjoy learning new frameworks; for my projects I picked up PyTorch and LangChain on my own.",
    "I'm comfortable coding in Python and Java and would love to work on applied AI problems.",
    "Being a Smart India Hackathon 2024 finalist taught me to build quickly under a deadline.",
]
PLANTED_B = [
    ("I interned at TCS last summer, building dashboards in Python.", "internship at TCS"),
    ("I was a Google Summer of Code contributor for a LangChain plugin.", "GSoC"),
    ("My paper on resume matching was published at NeurIPS.", "NeurIPS paper"),
    ("I scored 99.2 percentile in JEE Main and chose CSE.", "JEE 99.2"),
    ("I have run Kafka pipelines in production for Resume Matcher.", "Kafka in production"),
    ("I mentored 20 juniors in the Data Science Club.", "mentored 20"),
    ("I speak English, Hindi and fluent German.", "German"),
    ("I ranked in the top 10 of a Kaggle competition with PyTorch.", "Kaggle top 10"),
]

QUESTIONS = [
    ("Why do you want to join Acme AI? (3-4 sentences)", "Acme AI builds LLM-powered hiring tools with Python, LangChain and RAG."),
    ("Tell us about the project you are most proud of.", None),
    ("What are your key strengths? Give an example.", None),
    ("Describe a time you worked in a team.", None),
    ("Describe your experience managing direct reports.", None),          # trap: should give no draft
    ("Tell us about ML models you have deployed to production at scale.", None),  # trap: no production work
]


def part1() -> None:
    for name, planted, honest in (("A", PLANTED, HONEST), ("B (unseen)", PLANTED_B, HONEST_B)):
        caught = [not check_draft({"text": t, "kind": "llm"}, FIELD, {"profile": PROFILE})["passed"] for t, _ in planted]
        wrong = [check_draft({"text": t, "kind": "llm"}, FIELD, {"profile": PROFILE}) for t in honest]
        print(f"Verifier set {name}: caught {sum(caught)}/{len(planted)} planted lies, "
              f"wrongly rejected {sum(not w['passed'] for w in wrong)}/{len(honest)} honest answers")
        for (t, lie), c in zip(planted, caught):
            if not c:
                print(f"  MISSED: {lie}")
        for t, w in zip(honest, wrong):
            if not w["passed"]:
                print(f"  wrongly rejected: {t[:60]} <- {'; '.join(w['reasons'])[:90]}")


def part2() -> None:
    for i, (question, jd) in enumerate(QUESTIONS):
        field = {"id": f"q{i}", "label": question, "kind": "textarea", "options": [], "placeholder": "", "helper_text": ""}
        start = time.time()
        result = run_fill([field], PROFILE, jd)
        a = next(x for x in result["actions"] if x["field_id"] == field["id"])
        print(f"\nQ: {question}\n   {time.time() - start:.0f} s, drafter ran {result['trace'].count('drafter')}x, "
              f"status {a['status']}: {a['reason'][:120]}\n   A: {a.get('value') or '(no draft)'}")


if __name__ == "__main__":
    print(f"model: {config.DRAFT_MODEL}")
    part1()
    part2()
