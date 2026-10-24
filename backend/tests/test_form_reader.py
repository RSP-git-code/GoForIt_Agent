"""Form Reader safety: what the model sees, and the grounding check on its answers (no Ollama needed)."""

from agents.form_reader import build_prompt, fact_key, ground, profile_facts

PROFILE = {
    "personal": {"full_name": "Asha Verma", "email": "asha@example.com", "phone": "+91 9876543210",
                 "date_of_birth": "2004-01-15", "category": "General", "nationality": "Indian",
                 "permanent_address": "1 Example Road", "pincode": "411001"},
    "links": {"leetcode": "https://leetcode.com/u/asha/"},
    "education": {"degree": {"cgpa": "8.42", "registration_number": "21XYZ0001", "branch": "CSE"}},
    "achievements": ["Smart India Hackathon 2024 finalist"],
    "languages_spoken": ["English", "Japanese"],
    "experience": [],
}


def test_private_details_never_reach_the_model():
    facts = profile_facts(PROFILE)
    text = " ".join(f"{k} {v}" for k, v in facts.items())
    for secret in ("asha@example.com", "9876543210", "2004-01-15", "General", "1 Example Road", "411001", "21XYZ0001"):
        assert secret not in text, secret
    assert facts["education.degree.cgpa"] == "8.42" and facts["links.leetcode"].startswith("https://")
    assert "none" in facts["experience"]  # an empty list is still a fact the model can cite
    prompt = build_prompt([{"id": "a", "label": "CGPA", "kind": "text"}], facts, __import__("datetime").date(2026, 10, 18))
    assert "9876543210" not in prompt and "18 October 2026" in prompt


def test_fact_key_accepts_key_value_citations():
    facts = profile_facts(PROFILE)
    assert fact_key("education.degree.cgpa: 8.42", facts) == "education.degree.cgpa"
    assert fact_key("made.up.key", facts) is None


def test_grounding_rejects_invented_answers():
    facts = profile_facts(PROFILE)
    text = {"id": "x", "kind": "text", "options": []}
    assert ground(text, "8.42", "education.degree.cgpa", facts)[0]
    assert ground(text, "84.2", "education.degree.cgpa", facts)[0]                 # CGPA x 10 is allowed
    assert not ground(text, "1850", "education.degree.cgpa", facts)[0]             # a rating it made up
    assert not ground(text, "Python", None, facts)[0]                              # nothing cited
    assert not ground(text, "AWS Hackathon winner", "achievements", facts)[0]      # not what the fact says
    assert ground(text, "Smart India Hackathon 2024 finalist", "achievements", facts)[0]
    assert ground(text, None, None, facts)[0]                                      # leaving it empty is always fine


def test_grounding_checks_options():
    facts = profile_facts(PROFILE)
    radio = {"id": "x", "kind": "radio", "options": ["LeetCode", "Codeforces"]}
    assert ground(radio, "LeetCode", "links.leetcode", facts)[0]
    assert not ground(radio, "HackerEarth", "links.leetcode", facts)[0]            # not an option
