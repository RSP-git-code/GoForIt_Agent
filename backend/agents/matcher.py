"""Matcher agent: how well the profile fits the job, and which project to talk about.

No ML yet (Phase 9 adds embeddings): it compares the job description and the
form's questions with the profile's skills and project texts.
  - fit score: share of the job's tech terms that appear in the profile
  - best projects: ranked by shared technologies (weight 2) and shared
    keywords in title/summary (weight 1)
Only sees the non-sensitive slice of the profile (services/profile_facts.py).
"""

from services.option_match import words
from services.profile_facts import all_skills, safe_profile

# Common tech terms to look for in a job description, besides the profile's own skills.
TECH_TERMS = [
    "python", "java", "javascript", "typescript", "c++", "go", "rust", "sql", "nosql", "react", "node", "django",
    "flask", "fastapi", "aws", "azure", "gcp", "docker", "kubernetes", "linux", "git", "pytorch", "tensorflow",
    "keras", "scikit learn", "pandas", "numpy", "nlp", "llm", "llms", "rag", "langchain", "machine learning",
    "deep learning", "reinforcement learning", "computer vision", "data analysis", "data science", "statistics",
    "excel", "power bi", "tableau", "spark", "hadoop", "rest api", "apis", "generative ai", "transformers",
    "recommendation", "classification", "time series", "mlops", "devops",
]
STOPWORDS = set("""a an and are as at be by for from has have in is it its of on or our that the their this to we
will with you your who what why how would like join work role team about into using use used build built
also can more than such any all other within across""".split())


def _has(text: str, term: str) -> bool:
    return f" {words(term)} " in text


def _keywords(text: str) -> set[str]:
    return {w for w in words(text).split() if len(w) > 3 and w not in STOPWORDS}


def match(job_text: str, profile: dict) -> dict:
    facts = safe_profile(profile)
    jd = f" {words(job_text or '')} "
    skills = all_skills(facts)

    jd_terms = {t for t in TECH_TERMS if _has(jd, t)} | {words(s) for s in skills if _has(jd, s)}
    matched = [s for s in skills if _has(jd, s)]
    score = round(100 * len({words(s) for s in matched}) / len(jd_terms)) if jd_terms else None

    jd_words = _keywords(job_text or "")
    ranked = []
    for i, pr in enumerate(facts["projects"]):
        tech_hits = [t for t in pr.get("tech") or [] if _has(jd, t)]
        word_hits = _keywords(f"{pr.get('title', '')} {pr.get('summary', '')}") & jd_words
        ranked.append({
            "title": pr.get("title", ""),
            "score": 2 * len(tech_hits) + len(word_hits),
            "shared_tech": tech_hits,
            "index": i,
        })
    # Highest score first; ties keep resume order (usually strongest project first).
    ranked.sort(key=lambda r: (-r["score"], r["index"]))

    return {
        "score": score,
        "matched_skills": list(dict.fromkeys(matched))[:8],
        "missing_terms": sorted(jd_terms - {words(s) for s in matched})[:8],
        "best_projects": ranked[:3],
    }


def matcher(state: dict) -> dict:
    questions = " ".join(f["label"] for f in state["fields"] if f["id"] in state["free_text_fields"])
    fit = match(f"{state.get('job_description') or ''} {questions}", state.get("profile") or {})
    return {"fit": fit, "trace": ["matcher"]}
