"""LinkedIn/Indeed job alerts -> tracker rows. The LinkedIn fixture is a cleaned
copy of a real alert (2026-10-05): fake tokens, fake recipient."""

from pathlib import Path

from agents.inbox import process_alert, process_alerts, title_fit
from services.alert_parser import parse_alert, read_eml
from services.tracker_xlsx import load_rows, upsert

FIXTURE = Path(__file__).parent / "fixtures" / "linkedin_alert.eml"
PROFILE = {
    "personal": {"full_name": "Test Student"},
    "education": {"degree": {"specialization": "AI and ML"}},
    "skills": {"languages": ["Python", "SQL"], "ml_ai": ["scikit-learn", "LangChain"]},
    "projects": [],
}


def mail():
    return read_eml(FIXTURE.read_bytes())


def test_reads_the_eml():
    m = mail()
    assert "linkedin.com" in m["from"] and m["date"] == "2026-10-05"


def test_one_record_per_job_no_duplicates_no_footer():
    jobs = parse_alert(mail())
    assert [j["title"] for j in jobs] == ["Python + AI Engineer", "AI / ML Engineer", "Sales Executive"]
    first = jobs[0]
    assert (first["company"], first["location"]) == ("Innova ESI", "Bengaluru")
    assert first["signals"] == ["This company is actively hiring", "Apply with resume & profile"]
    assert first["alert_query"] == "Artificial Intelligence Engineer in India"


def test_links_never_keep_tokens_or_tracking():
    for job in parse_alert(mail()):
        assert job["link"].startswith("https://www.linkedin.com/jobs/view/") and "?" not in job["link"]
        assert "FAKESECRETTOKEN" not in str(job)
    assert "Test Student" not in str(parse_alert(mail()))  # footer with the recipient's name is ignored


def test_title_fit_from_profile_terms():
    assert title_fit("Python + AI Engineer", PROFILE) == ("High", ["AI", "Python"], "")
    assert title_fit("Artificial Intelligence Engineer", PROFILE) == ("Medium", ["AI"], "")
    assert title_fit("Sales Executive", PROFILE) == ("Low", [], "")


def test_rows_have_next_morning_reminder_and_go_into_the_tracker(tmp_path):
    rows = process_alert(mail(), PROFILE)
    assert rows[0]["reminder"] == "2026-10-06 09:00"
    assert rows[0]["fit_score"] == "High (AI, Python)"
    path = tmp_path / "applications.xlsx"
    assert len(upsert(path, process_alerts([mail(), mail()], PROFILE))["added"]) == 3  # same alert twice: no dupes
    assert load_rows(path)["linkedin:4473898815"]["company"] == "Accenture services Pvt Ltd"


def test_other_senders_are_ignored():
    assert parse_alert({"from": "Swiggy <orders@swiggy.example>", "body": "View job: https://www.linkedin.com/jobs/view/1/"}) == []


INDEED = Path(__file__).parent / "fixtures" / "indeed_alert.eml"


def test_indeed_alert_one_job_per_paragraph():
    jobs = parse_alert(read_eml(INDEED.read_bytes()))
    assert [j["title"] for j in jobs] == ["AIML Engineer Digital & AI", "Machine Learning Engineer",
                                          "Senior AI Engineer", "Principal Site Reliability Engineer"]
    first = jobs[0]
    assert (first["company"], first["location"]) == ("IQ-EQ", "Gachibowli, Hyderabad, Telangana")
    assert first["signals"] == ["Easily apply", "Just posted"]
    assert first["link"] == "https://in.indeed.com/viewjob?jk=b2a0947f0af15aa3"
    assert "cross-functional" in first["snippet"]
    assert jobs[2]["signals"][0].startswith("₹15,00,000")
    assert jobs[0]["alert_query"] == "ai/ml engineer"


def test_indeed_personalised_links_never_stored():
    jobs = parse_alert(read_eml(INDEED.read_bytes()))
    sponsored = jobs[-1]
    assert "Sponsored" in sponsored["signals"] and sponsored["job_key"].startswith("indeed:ad-")
    assert sponsored["link"].startswith("https://in.indeed.com/jobs?q=")
    assert "FAKEPERSONALTOKEN" not in str(jobs)


def test_fresher_fit_drops_for_senior_or_experienced_roles():
    assert title_fit("Senior AI Engineer", PROFILE)[0::2] == ("Low", "senior role")
    level, _, why = title_fit("Machine Learning Engineer", PROFILE, "seeking an experienced ML Engineer (4–6 years) to")
    assert (level, why) == ("Low", "asks for 4+ years")
    assert title_fit("AIML Engineer Digital & AI", PROFILE, "build scalable digital products")[0] == "High"


def test_posted_date_from_indeed_age_lines():
    from agents.inbox import posted_date
    assert posted_date("2026-10-05", ["Easily apply", "Just posted"]) == "2026-10-05"
    assert posted_date("2026-10-05", ["3 days ago"]) == "2026-10-02"
    assert posted_date("2026-10-05", ["30+ days ago"]) == "2026-09-05"
    assert posted_date("2026-10-05", []) == "2026-10-05"  # LinkedIn: no age line
    rows = process_alerts([read_eml(INDEED.read_bytes())], PROFILE)
    assert {r["title"]: r["posted"] for r in rows}["Machine Learning Engineer"] == "2026-10-04"


def test_phd_and_masters_roles_are_low_for_a_bachelors_student():
    btech = {**PROFILE, "education": {"degree": {"name": "B.Tech", "specialization": "AI and ML"}}}
    assert title_fit("Research Intern (PhD), Storage Systems for AI", btech)[0::2] == ("Low", "for PhD students")
    assert title_fit("Research Intern (PhD), AI-Scale Protocols & Simulation", btech)[0::2] == ("Low", "for PhD students")
    assert title_fit("ML Intern - Master's students only", btech)[0::2] == ("Low", "for Master's students")
    assert title_fit("AI Research Intern", btech, "We are looking for students pursuing a PhD in ML")[0::2] == \
        ("Low", "for PhD students")
    assert title_fit("AI Software Engineer Intern", btech)[0] == "Medium"  # bachelor's-level role is fine
    mtech = {**PROFILE, "education": {"degree": {"name": "M.Tech", "specialization": "AI and ML"}}}
    assert title_fit("ML Intern - Master's students only", mtech)[0] != "Low"


def test_years_in_the_title_make_entry_level_roles_low():
    assert title_fit("Python Developer (3+ Yrs)", PROFILE)[0::2] == ("Low", "asks for 3+ years")
    assert title_fit("AI Engineer | 2-5 years | Entry level", PROFILE)[0::2] == ("Low", "asks for 2+ years")
    assert title_fit("AI Engineer (0-2 years)", PROFILE)[0] != "Low"  # freshers welcome


def test_linkedin_extra_description_line_is_used():
    body = ("Your job alert for AI Engineer in India\nAI Engineer\nAcme\nBengaluru\n"
            "Looking for candidates with 4+ years of experience in ML\n"
            "View job: https://www.linkedin.com/comm/jobs/view/123/?otpToken=X\n")
    rows = process_alerts([{"from": "LinkedIn <jobalerts-noreply@linkedin.com>", "date": "2026-10-09", "body": body}], PROFILE)
    assert rows[0]["fit_score"] == "Low (asks for 4+ years)"


def test_experience_signal():
    from agents.inbox import experience_signal
    assert experience_signal("AI/ML Intern", "", "") == "Fresher-friendly"
    assert experience_signal("Graduate Engineer Trainee - 2027 batch", "", "") == "Fresher-friendly"
    assert experience_signal("Associate Software Engineer", "", "") == "Fresher-friendly"
    assert experience_signal("AI Engineer", "", "") == "Not stated: check"
    assert experience_signal("AI Engineer", "", "asks for 3+ years") == "Asks 3+ years"
    assert experience_signal("ML Engineer", "Freshers welcome to apply", "") == "Fresher-friendly"


def test_companies_you_found_needing_experience_are_demoted():
    from agents.inbox import companies_needing_experience
    history = [{"company": "Innova ESI", "status": "Not eligible"}, {"company": "Innova ESI Pvt Ltd", "status": "Not eligible"},
               {"company": "Acme", "status": "Not eligible"}, {"company": "Beta", "status": "Not eligible"},
               {"company": "Beta", "status": "Not eligible"}, {"company": "Beta", "status": "Applied"}]
    needs = companies_needing_experience(history)
    assert needs == {"innova esi"}  # Acme: only once; Beta: you applied there
    rows = process_alerts([read_eml(FIXTURE.read_bytes())], PROFILE, needs_exp=needs)
    innova = [r for r in rows if r["company"] == "Innova ESI"]
    assert innova and all(r["fit_score"] == "Low (this company's roles you checked needed experience)" for r in innova)
