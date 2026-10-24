"""Website / URL boxes, including Workday's bare "URL" under a "Websites" heading."""

from agents.mapper import map_field
from services.rules import classify

WITH_PORTFOLIO = {"links": {"github": "https://github.com/me", "linkedin": "https://linkedin.com/in/me",
                            "portfolio": "https://me.dev"}}
NO_PORTFOLIO = {"links": {"github": "https://github.com/me", "linkedin": "https://linkedin.com/in/me", "portfolio": ""}}


def f(label, section=""):
    return {"id": "x", "label": label, "section": section, "kind": "url", "options": [], "placeholder": "", "helper_text": ""}


def fill(label, section, profile):
    field = f(label, section)
    key = classify(field)
    return key, map_field(field, key, profile)


def test_bare_url_under_websites_gets_portfolio_or_github():
    key, a = fill("URL", "Websites 1", NO_PORTFOLIO)
    assert key == "links.portfolio" and a["value"] == "https://github.com/me" and a["status"] == "review"
    assert "GitHub" in a["reason"]
    assert fill("URL", "Websites", WITH_PORTFOLIO)[1]["value"] == "https://me.dev"


def test_section_names_the_link():
    assert classify(f("URL", "GitHub Profile")) == "links.github"
    assert classify(f("Link", "LinkedIn")) == "links.linkedin"


def test_website_labels_fall_back_to_github():
    for label in ("Website", "Personal website", "Portfolio URL"):
        key, a = fill(label, "", NO_PORTFOLIO)
        assert key == "links.portfolio" and a["value"] == "https://github.com/me" and a["status"] == "review"


def test_education_from_to_uses_the_section_heading():
    assert classify({**f("From", "Education"), "kind": "text"}) == "education.entry.from"
    assert classify({**f("To", "Education 1"), "kind": "text"}) == "education.entry.to"
    assert classify({**f("To", "Work Experience"), "kind": "text"}) is None


def test_bare_school_uses_the_section_heading():
    def school(label, section):
        return classify({**f(label, section), "kind": "text"})
    assert school("School", "Education *") == "education.degree.college"       # Oracle / Workday entry
    assert school("Institution", "Academic Details") == "education.degree.college"
    assert school("School", "Class X details") == "education.class_10.school"
    assert school("School", "12th Standard") == "education.class_12.school"
    assert school("School", "") is None                                         # no context: you decide
