"""Agent Octo (Coach): skills required vs nice-to-have, hard requirements, verdicts, resources."""

from fastapi.testclient import TestClient

from agents.coach import coach
from app.main import app

PROFILE = {
    "education": {"degree": {"name": "B.Tech", "graduation_year": "2027", "cgpa": "8.4", "percentage_equivalent": "84"},
                  "class_10": {"percentage": "91"}, "class_12": {"percentage": "93"}},
    "skills": {"languages": ["Python", "Java"], "ml_ai": ["scikit-learn", "TensorFlow/Keras", "LangChain", "RAG"]},
    "projects": [{"title": "Smart Resume Scanner - RAG-based matching", "summary": "Django app with a RAG pipeline.",
                  "tech": ["Python", "Django", "LangChain", "RAG", "Gemini API"]}],
    "experience": [],
    "certifications": [{"name": "AWS Academy Graduate - Cloud Foundations", "issuer": "AWS Academy"}],
}
JD = """AI Engineer Intern
Requirements:
- B.Tech in CS, 2026 or 2027 batch
- Python, LangChain and RAG
- Docker
- Minimum 7.5 CGPA
Good to have:
- Kubernetes"""


def test_fit_gaps_and_resources():
    r = coach(JD, PROFILE)
    skills = {m["skill"] for m in r["matched"]}
    assert {"Python", "LangChain", "RAG"} <= skills
    assert [m["skill"] for m in r["missing_required"]] == ["Docker"]
    assert [m["skill"] for m in r["missing_nice"]] == ["Kubernetes"]       # nice-to-have, not required
    docker = r["missing_required"][0]
    urls = [r["url"] for r in docker["resources"]]
    assert "freecodecamp" in urls[0] and any(u.startswith("https://docs.docker.com") for u in urls)
    assert "Smart Resume Scanner" in docker["show"]
    assert r["verdict"].startswith("Apply") and all(h["ok"] for h in r["hard_requirements"])


def test_skills_shown_by_related_work():
    # LangChain + RAG projects show LLM experience; an AWS Academy certificate shows AWS.
    r = coach("Requirements: experience with LLMs and AWS", PROFILE)
    assert {m["skill"] for m in r["matched"]} == {"LLMs / Generative AI", "AWS"}


def test_hard_requirements_mean_skip():
    for jd, why in [("Requirements: M.Tech or PhD in Computer Science", "Master"),
                    ("Requirements: 3+ years of experience with Python", "3+ years"),
                    ("Eligibility: 2025 batch graduates only. Python.", "batch"),
                    ("Requirements: CGPA of 9 and above. Python.", "cut-off"),
                    ("Requirements: 95% throughout academics (10th, 12th, graduation).", "%")]:
        r = coach(jd, PROFILE)
        assert r["verdict"].startswith("Skip") and why.lower() in r["verdict"].lower() + str(r["hard_requirements"]).lower(), jd


def test_bachelor_or_master_is_fine_and_vague_jd_says_so():
    assert not any(not h["ok"] for h in coach("Requirements: B.Tech or M.Tech in CS. Python.", PROFILE)["hard_requirements"])
    assert coach("We are a fast-growing team looking for passionate people.", PROFILE)["fit_percent"] is None


def test_coach_endpoint_logs_nothing_personal(caplog):
    with caplog.at_level("INFO"):
        body = TestClient(app).post("/coach", json={"job_text": JD, "job_title": "AI Engineer Intern", "profile": PROFILE}).json()
    assert body["verdict"].startswith("Apply") and body["missing_required"][0]["skill"] == "Docker"
    assert "Smart Resume Scanner" not in caplog.text and "LangChain" not in caplog.text
