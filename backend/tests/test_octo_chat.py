"""Agent Octo chat: job descriptions, skill questions, project and plan answers, LLM fallback without links."""

from fastapi.testclient import TestClient

from agents import octo_chat
from app.main import app
from services import ollama_client

from tests.test_coach import JD, PROFILE


def ask(message, result=None, history=None):
    return octo_chat.reply(message, PROFILE, result, history)


def ask_plan(message, result=None, plan=None, history=None):
    return octo_chat.reply(message, PROFILE, result, history, "", plan)


def test_pasted_job_description_gets_the_analysis_as_messages():
    out = ask(JD)
    texts = " ".join(m["text"] for m in out["messages"])
    assert out["result"]["verdict"].startswith("Apply") and "Docker" in texts and "You already have" in texts
    assert "How do I learn Docker?" in out["chips"] and "Which project should I mention?" in out["chips"]


def test_skill_question_uses_curated_resources(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM needed")))
    out = ask("How do I learn Docker?", ask(JD)["result"])
    msg = out["messages"][0]
    urls = [link["url"] for link in msg["links"]]
    assert msg["text"].startswith("Docker: about") and "freecodecamp" in urls[0]          # free first
    assert any("techworld" in u for u in urls) and any(u.startswith("https://docs.docker.com") for u in urls)
    assert any("google.com/search" in u for u in urls)                                    # more free resources


def test_project_and_plan_answers():
    result = ask(JD)["result"]
    assert "Smart Resume Scanner" in ask("Which project should I mention?", result)["messages"][0]["text"]
    plan = ask("Make me a plan", result)["messages"][0]
    assert "• Docker:" in plan["text"] and "not in your calendar yet" in plan["text"] and plan["links"]


def test_free_chat_goes_to_the_local_llm_and_links_are_removed(monkeypatch):
    monkeypatch.setattr(ollama_client, "ollama_running", lambda timeout=0.5: True)
    seen = {}

    def fake_chat(system, user, **kw):
        seen["prompt"] = user
        return "You'd do well here! See https://evil.example.com for tips.", 0.1
    monkeypatch.setattr(ollama_client, "chat", fake_chat)
    out = ask("Am I good enough for this role?", ask(JD)["result"])
    assert "evil.example.com" not in out["messages"][0]["text"] and "Missing: Docker" in seen["prompt"]


def test_without_ollama_octo_says_what_he_can_still_do(monkeypatch):
    monkeypatch.setattr(ollama_client, "ollama_running", lambda timeout=0.5: False)
    out = ask("Tell me a joke")
    assert "Ollama" in out["messages"][0]["text"] and out["mood"] == "concerned"


def test_octo_endpoint(caplog):
    with caplog.at_level("INFO"):
        body = TestClient(app).post("/octo", json={"message": JD, "profile": PROFILE}).json()
    assert body["result"]["missing_required"][0]["skill"] == "Docker" and body["messages"]
    assert "Docker" not in caplog.text  # messages are never logged



class FakeCalendar:
    """Just enough of the Google Calendar client for Octo's study-plan tool."""
    def __init__(self, existing=()):
        self.store = {f"old{i}": e for i, e in enumerate(existing)}
        self.inserted = []

    def events(self):
        return self

    def list(self, **kw):
        return _Exec({"items": [{"id": k, **v} for k, v in self.store.items()]})

    def delete(self, calendarId, eventId):
        self.store.pop(eventId, None)
        return _Exec({})

    def insert(self, calendarId, body):
        self.inserted.append(body)
        return _Exec({"id": f"new{len(self.inserted)}", **body})


class _Exec:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


def test_plan_goes_into_the_calendar_and_asks_before_replacing(monkeypatch):
    from services import google_auth
    cal = FakeCalendar()
    monkeypatch.setattr(google_auth, "service", lambda *a, **k: cal)
    first = ask(JD)
    result, plan = first["result"], first["plan"]
    out = ask_plan("Add this plan to my calendar", result, plan)
    assert out["messages"][0]["text"].startswith("Done!") and len(cal.inserted) == 1 and out["plan"]["in_calendar"]
    event = cal.inserted[0]
    assert "Learn Docker" in event["summary"] and event["recurrence"][0].startswith("RRULE:FREQ=DAILY;COUNT=")
    assert event["start"]["dateTime"].endswith("T20:00:00") and "freecodecamp" in event["description"]
    assert "@" not in event["description"]                       # no personal details in the event
    # A second time: Octo asks first, and only replaces when told to.
    cal2 = FakeCalendar(existing=[{"summary": "📚 Learn SQL (Agent Octo plan)"}])
    monkeypatch.setattr(google_auth, "service", lambda *a, **k: cal2)
    ask_again = ask_plan("Add this plan to my calendar", result, plan)
    assert "replace it" in ask_again["messages"][0]["text"] and not cal2.inserted
    assert "Yes, replace my plan" in ask_again["chips"]
    ask_plan("Yes, replace my plan", result, plan)
    assert not cal2.store and len(cal2.inserted) == 1


def test_todays_jobs_come_from_the_tracker(monkeypatch, tmp_path):
    from app import config
    from services.tracker_xlsx import upsert
    path = tmp_path / "applications.xlsx"
    monkeypatch.setattr(config, "TRACKER_PATH", path)
    from datetime import date
    today = date.today().isoformat()
    upsert(path, [
        {"job_key": "li:1", "source": "LinkedIn", "received": today, "posted": today, "title": "AI Intern", "company": "Acme",
         "location": "Pune", "link": "https://www.linkedin.com/jobs/view/1/", "fit_score": "High (ai)", "experience_signal": "Fresher-friendly"},
        {"job_key": "li:2", "source": "LinkedIn", "received": today, "posted": today, "title": "ML Engineer", "company": "Beta",
         "location": "Remote", "link": "https://www.linkedin.com/jobs/view/2/", "fit_score": "Medium (ml)", "experience_signal": "Asks 3+ years"},
        {"job_key": "li:3", "source": "LinkedIn", "received": today, "posted": today, "title": "Sales", "company": "Gamma",
         "location": "Delhi", "link": "https://www.linkedin.com/jobs/view/3/", "fit_score": "Low", "experience_signal": ""},
    ])
    msg = ask("Which jobs should I apply to today?")["messages"][0]
    assert msg["text"].index("AI Intern") < msg["text"].index("ML Engineer") and "Sales" not in msg["text"]
    assert "⚠ Asks 3+ years" in msg["text"] and len(msg["links"]) == 2


def test_tutorials_request_lists_free_resources_for_the_gaps():
    msg = ask("ya i want tutorials", ask(JD)["result"])["messages"][0]
    assert msg["links"] and msg["links"][0]["title"].startswith("Docker: ▶ freeCodeCamp")


def test_resources_follow_the_topic_octo_just_talked_about(monkeypatch):
    # The screenshot case: Octo (LLM) suggested CUDA / OpenCL, then "can u provide resources".
    last = ("Focus on learning computer architecture concepts and memory systems. Practice with tools like CUDA or OpenCL.")
    monkeypatch.setattr(ollama_client, "ollama_running", lambda: True)
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: ("CUDA, Computer architecture, Rust", {}))
    history = [{"role": "student", "text": "how do i do that"}, {"role": "octo", "text": last}]
    msg = ask("can u provide resources", None, history)["messages"][0]
    titles = [link["title"] for link in msg["links"]]
    assert "CUDA" in msg["text"] and any(t.startswith("CUDA: ▶ freeCodeCamp") for t in titles)
    assert not any(t.startswith("Rust") for t in titles)  # not in Octo's reply: never invented


def test_learn_that_uses_known_skills_from_the_last_reply():
    history = [{"role": "octo", "text": "You'd need Docker and Kubernetes for this role."}]
    msg = ask("how do i learn that", None, history)["messages"][0]
    assert [link["title"].split(":")[0] for link in msg["links"]][:1] == ["Docker"] and "Kubernetes" in msg["text"]


QC_JOB = """Required Education, Knowledge, and Certifications:
• Bachelor's degree in IT, Computer Science, or a related field.
• In-depth understanding of ITSM principles and frameworks.
• Knowledge of QC, and QA concepts
• Certification in ITIL Foundation or equivalent is mandatory. Higher level is an advantage.
Required Hard Skills:
• Proficient in MINITAB or SPSS systems.
• Proficient in BI, Office 365, and SharePoint tools.
Required Soft Skills:
• Exceptional problem-solving and critical-thinking skills.
Experience:
• Demonstrated experience in conducting process capability optimization utilizing the six-sigma DMAIC methodology."""


def test_quality_control_job_names_its_real_gaps_not_dsa():
    # Real case: an ITSM / QC job; "problem-solving" (a soft skill) used to count as DSA.
    out = ask(QC_JOB)
    result = out["result"]
    names = [m["skill"] for m in result["missing_required"]] + [m["skill"] for m in result["matched"]]
    assert {"ITIL / ITSM", "QA / QC concepts", "Six Sigma (DMAIC)", "Minitab / SPSS"} <= set(names)
    assert "Data structures & algorithms" not in names
    assert result["certifications"][0]["skill"] == "ITIL / ITSM" and not result["certifications"][0]["have"]
    assert any(m["text"].startswith("Mandatory certification: ITIL") for m in out["messages"])


def test_where_am_i_lacking_answers_from_the_analysis_not_the_llm(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM used")))
    result = ask(QC_JOB)["result"]
    text = ask("where am i lacking in this role", result)["messages"][0]["text"]
    assert "ITIL" in text and "Six Sigma" in text and "machine learning" not in text.lower()


def test_same_on_one_line_like_a_right_click_selection():
    # Chrome's right-click selection text has no line breaks.
    result = ask(QC_JOB.replace("\n", " "))["result"]
    assert "Minitab / SPSS" in [m["skill"] for m in result["missing_required"]]



def test_the_screenshot_conversation_edits_a_real_plan(monkeypatch):
    """Real chat: Octo ignored "not Airflow", the days and the dates, then the LLM claimed it had changed the plan."""
    from datetime import date
    from agents import octo_plan
    from services import google_auth
    monkeypatch.setattr(octo_plan, "date", type("D", (date,), {"today": classmethod(lambda c: date(2026, 10, 20))}))
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM used")))
    result = {"missing_required": [{"skill": "Spark"}, {"skill": "Airflow"}], "matched": [], "missing_nice": []}

    out = ask_plan("i dont want to learn airflow i am talking about langchain and pyspark", result, None)
    plan = out["plan"]
    assert [it["skill"] for it in plan["items"]] == ["LangChain", "Spark"] and "Removed Airflow" in out["messages"][0]["text"]

    out = ask_plan("i am doing langchain within 2 days and pyspark for 5 days so make a plan from 20 october to 24 october",
                   result, plan)
    plan = out["plan"]
    assert [(it["skill"], it["start"], it["days"]) for it in plan["items"]] == [("LangChain", "2026-10-20", 2), ("Spark", "2026-10-22", 3)]
    assert "shortened Spark to 3 (you said 5)" in out["messages"][0]["text"] and "Keep the full days" in out["chips"]
    full = ask_plan("Keep the full days", result, plan)["plan"]
    assert full["items"][1]["days"] == 5

    status = ask_plan("did u change it", result, plan)["messages"][0]["text"]
    assert "LangChain: 20 Oct – 21 Oct" in status and "NOT in your calendar" in status

    cal = FakeCalendar()
    monkeypatch.setattr(google_auth, "service", lambda *a, **k: cal)
    added = ask_plan("did u add in calendar", result, plan)       # a question, not an order: nothing added
    assert not cal.inserted and "NOT in your calendar" in added["messages"][0]["text"]
    added = ask_plan("add this plan to my calendar at 7 pm", result, plan)
    assert len(cal.inserted) == 2 and cal.inserted[0]["start"]["dateTime"] == "2026-10-20T19:00:00"
    cal.store = {"a": {"summary": "📚 Learn LangChain (Agent Octo plan)", "start": {"dateTime": "2026-10-20T20:00:00"}},
                 "b": {"summary": "📚 Learn LangChain (Agent Octo plan)", "start": {"dateTime": "2026-10-21T20:00:00"}}}
    dates = ask_plan("which dates did u add the plan to", result, added["plan"])["messages"][0]["text"]
    assert "LangChain: 20 Oct – 21 Oct, 8 PM (2 sessions)" in dates


def test_how_do_i_learn_is_not_a_plan_change():
    plan = {"items": [{"skill": "Docker", "start": "2026-10-21", "days": 3, "asked_days": 3}], "start": "2026-10-21",
            "end": None, "hour": 20, "in_calendar": False}
    out = ask_plan("How do I learn Docker?", None, plan)
    assert out["messages"][0]["text"].startswith("Docker: about") and out["plan"] == plan


def test_second_plan_goes_alongside_the_first_at_its_own_time(monkeypatch):
    """Real chat: Spark was in the calendar at 8 PM; LangChain should go in at 11 AM WITHOUT replacing it."""
    from services import google_auth
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM used")))
    spark = {"summary": "📚 Learn Spark (Agent Octo plan)", "start": {"dateTime": "2026-10-21T20:00:00"}}
    cal = FakeCalendar(existing=[spark])
    monkeypatch.setattr(google_auth, "service", lambda *a, **k: cal)
    plan = {"items": [{"skill": "LangChain", "start": "2026-10-21", "days": 2, "asked_days": 2}], "start": "2026-10-21",
            "end": None, "hour": 20, "in_calendar": False}

    asked = ask_plan("add this plan to my calendar", None, plan)
    text = asked["messages"][0]["text"]
    assert "Spark: 21 Oct, 8 PM" in text and "alongside" in text and "Add it alongside" in asked["chips"]
    assert not cal.inserted

    out = ask_plan("ya but spark is 8 pm right u can schedule it on 11am no need to replace it i can do both", None, plan)
    assert out["messages"][0]["text"].startswith("Done!") and out["plan"]["in_calendar"]
    assert cal.store, "Spark must still be in the calendar"
    assert [e["summary"] for e in cal.inserted] == ["📚 Learn LangChain (Agent Octo plan)"]
    assert cal.inserted[0]["start"]["dateTime"] == "2026-10-21T11:00:00"


def test_make_it_11am_and_yes_add_it_are_understood(monkeypatch):
    from services import google_auth
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM used")))
    cal = FakeCalendar()
    monkeypatch.setattr(google_auth, "service", lambda *a, **k: cal)
    plan = {"items": [{"skill": "LangChain", "start": "2026-10-21", "days": 2, "asked_days": 2}], "start": "2026-10-21",
            "end": None, "hour": 20, "in_calendar": False}
    plan = ask_plan("make it 11am", None, plan)["plan"]
    assert plan["hour"] == 11
    out = ask_plan("yes add it", None, plan)
    assert out["messages"][0]["text"].startswith("Done!") and cal.inserted[0]["start"]["dateTime"].endswith("T11:00:00")
    monkeypatch.setattr(ollama_client, "ollama_running", lambda: False)
    ask_plan("should I learn both?", None, plan)
    assert len(cal.inserted) == 1   # "both" in a question doesn't add anything


def test_llm_cannot_pretend_it_added_something(monkeypatch):
    monkeypatch.setattr(ollama_client, "ollama_running", lambda: True)
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: ("Your plan to study LangChain is now in your calendar. Keep it up!", {}))
    text = ask("tell me something nice")["messages"][0]["text"]
    assert text.startswith("I haven't changed anything")


def test_what_is_questions_get_explained_even_with_a_job_pasted(monkeypatch):
    """Real chat: "what is SAP TECHNICAL?" was refused ("not in the job requirements")."""
    calls = []
    monkeypatch.setattr(ollama_client, "ollama_running", lambda: True)
    monkeypatch.setattr(ollama_client, "chat", lambda system, prompt, **k: (calls.append(system) or "SAP technical roles build and support SAP systems.", {}))
    result = ask(JD)["result"]
    for q in ("what is SAP TECHNICAL?",
              "no i am just asking cause i am applying to HCL TECH there they mentioned SAP technical role what do they do"):
        msg = ask(q, result)["messages"][0]
        assert msg["text"].startswith("SAP technical") and any("SAP Learning" in l["title"] for l in msg["links"])
    assert all("Explain the term" in s for s in calls)
    calls.clear()
    ask("what is my fit for this job", result)          # about the student: the job-aware answer
    assert calls and "Explain the term" not in calls[0]


def test_list_my_skills_comes_from_the_profile_not_the_llm(monkeypatch):
    # Real chat: "ok list my technical skillsets" got a repeat of the previous job pep talk.
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM used")))
    result = ask(JD)["result"]
    text = ask("ok list my technical skillsets", result)["messages"][0]["text"]
    assert text.startswith("Your skills") and "Python" in text and "Airflow" not in text
    assert ask("what are my projects", result)["messages"][0]["text"].startswith("Your projects")


def test_job_context_only_for_job_questions_and_no_repeats(monkeypatch):
    prompts = []
    answers = iter(["Same old answer about the job and Airflow.", "A fresh, direct answer."])
    monkeypatch.setattr(ollama_client, "ollama_running", lambda: True)
    monkeypatch.setattr(ollama_client, "chat", lambda system, prompt, **k: (prompts.append(prompt) or next(answers), {}))
    result = ask(JD)["result"]
    history = [{"role": "octo", "text": "Same old answer about the job and Airflow."}]
    text = ask("how are you doing today octo", result, history)["messages"][0]["text"]
    assert text == "A fresh, direct answer."                       # the repeat was caught and re-asked
    assert "Current job analysis" not in prompts[0]                # not a job question: no job context
    prompts.clear()
    monkeypatch.setattr(ollama_client, "chat", lambda system, prompt, **k: (prompts.append(prompt) or "ok", {}))
    ask("how hard will the interview for this role be", result)
    assert "Current job analysis" in prompts[0]


def test_should_i_apply_works_without_ollama(monkeypatch):
    # Real chat: "so should i apply" got "My chatty brain (Ollama) is off" three times.
    monkeypatch.setattr(ollama_client, "ollama_running", lambda: False)
    result = ask(JD)["result"]
    text = ask("so should i apply", result)["messages"][0]["text"]
    assert "Ollama" not in text and ("apply" in text.lower() or "skip" in text.lower())
    assert "Docker" in text or "skip" in text
