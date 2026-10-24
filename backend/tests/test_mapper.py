from agents.mapper import map_field
from services.rules import classify

PROFILE = {
    "personal": {"full_name": "", "first_name": "Ananya", "middle_name": "", "last_name": "Rao",
                 "phone": "+91 90000 12345", "date_of_birth": "2004-06-15", "gender": "Female"},
    "education": {"degree": {"branch": "Computer Science and Engineering", "specialization": "AI and ML",
                             "cgpa": "8.5", "cgpa_scale": "10", "percentage_equivalent": "", "active_backlogs": 0}},
    "skills": {"languages": ["Python", "Java"], "ml_ai": ["TensorFlow/Keras"]},
    "preferences": {"willing_to_relocate": ""},
    "standard_answers": {"about_me": "I build ML apps."},
}


def f(label="", kind="text", options=None, **extra):
    return {"id": "x", "label": label, "kind": kind, "options": options or [], "placeholder": "", "helper_text": "", **extra}


def test_name_is_composed_from_parts():
    a = map_field(f("Name"), "personal.full_name", PROFILE)
    assert (a["status"], a["value"]) == ("filled", "Ananya Rao")


def test_phone_and_date_formats():
    assert map_field(f("Mobile", helper_text="10 digits only"), "personal.phone", PROFILE)["value"] == "9000012345"
    assert map_field(f("Phone"), "personal.phone", PROFILE)["value"] == "+91 90000 12345"
    assert map_field(f("DOB"), "personal.date_of_birth", PROFILE)["value"] == "15/06/2004"
    assert map_field(f("DOB", placeholder="MM/DD/YYYY"), "personal.date_of_birth", PROFILE)["value"] == "06/15/2004"
    assert map_field(f("DOB", kind="date"), "personal.date_of_birth", PROFILE)["value"] == "2004-06-15"


def test_zero_backlogs_is_a_real_value():
    a = map_field(f("Active backlogs", kind="number"), "education.degree.active_backlogs", PROFILE)
    assert (a["status"], a["value"]) == ("filled", "0")


def test_never_invents_missing_values():
    a = map_field(f("Relocate?", kind="radio", options=["Yes", "No"]), "preferences.willing_to_relocate", PROFILE)
    assert a["status"] == "missing" and a["value"] is None
    pct = map_field(f("B.Tech percentage"), "education.degree.percentage_equivalent", PROFILE)
    assert pct["status"] == "missing" and "only CGPA" in pct["reason"]


def test_branch_prefers_specialization_option():
    a = map_field(f("Branch", "select", ["Choose", "CSE", "CSE (AI and ML)", "ECE"]), "education.degree.branch", PROFILE)
    assert (a["status"], a["value"]) == ("filled", "CSE (AI and ML)")
    plain = map_field(f("Branch", "select", ["Choose", "CSE", "ECE"]), "education.degree.branch", PROFILE)
    assert plain["value"] == "CSE"


def test_cgpa_scale_conversion_is_flagged():
    same = map_field(f("CGPA (out of 10)"), "education.degree.cgpa", PROFILE)
    assert (same["status"], same["value"]) == ("filled", "8.5")
    four = map_field(f("CGPA on a 4 point scale"), "education.degree.cgpa", PROFILE)
    assert four["status"] == "review" and four["value"] == "3.4"


def test_options_exact_partial_missing():
    assert map_field(f("Gender", "select", ["--", "M", "F"]), "personal.gender", PROFILE)["value"] == "F"
    none = map_field(f("Gender", "radio", ["Male", "Other"]), "personal.gender", PROFILE)
    assert none["status"] == "missing"


def test_checkbox_list_ticks_matching_skills():
    a = map_field(f("Skills", "checkbox", ["Python", "Go", "TensorFlow"]), "skills.all", PROFILE)
    assert a["status"] == "review" and a["value"] == ["Python", "TensorFlow"]


def test_special_keys():
    assert map_field(f("Resume", "file"), "resume_file", PROFILE)["status"] == "review"
    assert map_field(f("I declare", "checkbox", ["I declare"]), "consent", PROFILE)["status"] == "review"
    assert map_field(f("How did you hear?"), None, PROFILE)["status"] == "skipped"
    about = map_field(f("About me", "textarea"), "standard_answers.about_me", PROFILE)
    assert about["status"] == "review" and about["value"] == "I build ML apps."


DATES = {"education": {"degree": {"start_year": "2023", "start_month": "07", "graduation_year": "2027", "graduation_month": "05"}}}


def test_month_and_year_fields():
    assert map_field(f("Start month", "select", ["Month", "Jun", "Jul", "Aug"]), "education.degree.start_month", DATES)["value"] == "Jul"
    assert map_field(f("Graduation month"), "education.degree.graduation_month", DATES)["value"] == "May"
    assert map_field(f("Start date (MM/YYYY)"), "education.degree.start_date", DATES)["value"] == "07/2023"
    assert map_field(f("To", kind="month"), "education.degree.graduation_date", DATES)["value"] == "2027-05"
    full = map_field(f("Graduation date", kind="date"), "education.degree.graduation_date", DATES)
    assert (full["value"], full["status"]) == ("2027-05-01", "review")


def test_dates_need_both_month_and_year():
    only_year = {"education": {"degree": {"graduation_year": "2027", "graduation_month": ""}}}
    assert map_field(f("Graduation date"), "education.degree.graduation_date", only_year)["status"] == "missing"


def test_school_passing_month():
    school = {"education": {"class_12": {"year": "2023", "month": "03"}, "class_10": {"year": "2021", "month": ""}}}
    assert map_field(f("12th passing month", "select", ["Feb", "Mar", "Apr"]), "education.class_12.month", school)["value"] == "Mar"
    assert map_field(f("12th passing date (MM/YYYY)"), "education.class_12.passing_date", school)["value"] == "03/2023"
    assert map_field(f("10th passing date"), "education.class_10.passing_date", school)["status"] == "missing"


def test_school_start_dates():
    school = {"education": {"class_12": {"start_year": "2021", "start_month": "06", "year": "2023", "month": "03"}}}
    assert map_field(f("12th start date (MM/YYYY)"), "education.class_12.start_date", school)["value"] == "06/2021"
    assert map_field(f("12th start month"), "education.class_12.start_month", school)["value"] == "June"


VIT = {"education": {"degree": {"college": "VIT-AP University, Vijayawada", "university": "VIT-AP University", "college_aliases": []}}}
VIT_ALIASES = {"education": {"degree": {**VIT["education"]["degree"],
               "college_aliases": ["Vellore Institute of Technology", "Vellore Institute of Technology, Amaravati"]}}}
CAMPUSES = ["Select", "Vellore Institute of Technology, Vellore", "Vellore Institute of Technology, Amaravati", "IIT Bombay"]


def college(options, profile):
    a = map_field(f("College Name", "select", options), "education.degree.college", profile)
    return a["value"], a["status"]


def test_college_alias_exact_match_is_green():
    assert college(CAMPUSES, VIT_ALIASES) == ("Vellore Institute of Technology, Amaravati", "filled")
    assert college(["--", "VIT-AP University", "Other"], VIT) == ("VIT-AP University", "filled")


def test_college_closest_match_is_yellow():
    assert college(["Select", "Vellore Institute of Technology", "IIT Bombay"], VIT) == ("Vellore Institute of Technology", "review")


def test_ambiguous_campus_is_asked_not_guessed():
    value, status = college(CAMPUSES, VIT)
    assert value is None and status == "review"


def test_unknown_college_is_missing():
    assert college(["Select", "IIT Bombay", "NIT Trichy"], VIT) == (None, "missing")


PHONE = {"personal": {"phone": "+91 9876543210"}}


def test_country_code_options():
    for options, expected in [
        (["+1", "+44", "+91"], "+91"),
        (["Select", "United States (+1)", "India (+91)"], "India (+91)"),
        (["US 1", "IN 91"], "IN 91"),
    ]:
        a = map_field(f("Country code", "select", options), "personal.phone_country_code", PHONE)
        assert (a["value"], a["status"]) == (expected, "filled")
    assert map_field(f("Code", "select", ["+1", "+44"]), "personal.phone_country_code", PHONE)["status"] == "missing"
    no_code = {"personal": {"phone": "9876543210"}}
    assert map_field(f("Code", "select", ["+91"]), "personal.phone_country_code", no_code)["status"] == "missing"


def test_phone_without_code_when_form_has_code_field():
    from agents.mapper import mapper
    fields = [{"id": "c", "label": "Mobile Phone", "kind": "select", "options": ["+1", "India (+91)"]},
              {"id": "p", "label": "Mobile Phone", "kind": "tel", "options": []}]
    classified = [{"field_id": "c", "key": "personal.phone_country_code"}, {"field_id": "p", "key": "personal.phone"}]
    plan = mapper({"fields": fields, "classified": classified, "profile": PHONE})["fill_plan"]
    assert [a["value"] for a in plan] == ["India (+91)", "9876543210"]


def test_date_with_month_name_hint():
    p = {"personal": {"date_of_birth": "2004-06-15"}}
    assert map_field(f("Date of Birth", placeholder="DD MMM YYYY"), "personal.date_of_birth", p)["value"] == "15 Jun 2004"
    assert map_field(f("Date of Birth", placeholder="dd-mmm-yyyy"), "personal.date_of_birth", p)["value"] == "15-Jun-2004"


def test_long_values_are_shortened_in_reasons():
    long = {"personal": {"gender": "x" * 200}}
    a = map_field(f("Gender", "select", ["Male", "Female"]), "personal.gender", long)
    assert a["status"] == "missing" and len(a["reason"]) < 80


def test_workday_phone_block():
    from services.rules import classify
    p = {"personal": {"phone": "+91 9876543210"}}
    device = f("Phone Device Type", "select", ["Select", "Landline", "Mobile"])
    assert classify(device) == "personal.phone_type"
    assert map_field(device, "personal.phone_type", p)["value"] == "Mobile"
    assert classify(f("Phone Extension")) is None  # never gets the phone number
    assert classify(f("Phone Number")) == "personal.phone"
    code = f("Country Phone Code", "combobox")  # options not on the page yet
    a = map_field(code, classify(code), p)
    assert (a["value"], a["status"]) == (None, "review") and "India (+91)" in a["reason"]
    long_list = f("Country Phone Code", "select", [f"Country {i} (+{i + 100})" for i in range(150)] + ["India (+91)"])
    assert map_field(long_list, "personal.phone_country_code", p)["value"] == "India (+91)"



def test_education_from_to_values():
    p = {"education": {"degree": {"name": "B.Tech", "start_year": "2023", "start_month": "07",
                                  "graduation_year": "2027", "graduation_month": "05"}}}
    a = map_field(f("From"), "education.entry.from", p)
    assert (a["value"], a["status"]) == ("2023", "review") and "B.Tech" in a["reason"]
    assert map_field(f("To"), "education.entry.to", p)["value"] == "2027"
    assert map_field(f("To", kind="month"), "education.entry.to", p)["value"] == "2027-05"
    assert map_field(f("From", placeholder="MM/YYYY"), "education.entry.from", p)["value"] == "07/2023"


def test_date_of_birth_split_into_day_month_year_boxes():
    p = {"personal": {"date_of_birth": "2004-01-15"}}
    def box(label, options=()):
        d = {"id": "x", "label": label, "kind": "select" if options else "combobox", "options": list(options),
             "placeholder": "", "helper_text": ""}
        return map_field(d, classify(d), p)
    assert box("Date of Birth Day")["value"] == "15"
    assert box("Date of Birth Month")["value"] == "January"
    assert box("Date of Birth Year")["value"] == "2004"
    assert box("Date of Birth Month", ["Select", "Jan", "Feb", "Mar"])["value"] == "Jan"
    assert box("Date of Birth")["value"] == "15/01/2004"


def test_branch_text_box_uses_how_you_write_it():
    full = "Computer Science with Specialization in Artificial Intelligence and Machine Learning"
    p = {"education": {"degree": {"branch": "Computer Science and Engineering", "specialization": "AI and ML",
                                  "branch_full": full}}}
    def box(label, kind="text", options=()):
        d = {"id": "x", "label": label, "kind": kind, "options": list(options), "placeholder": "", "helper_text": ""}
        return map_field(d, classify(d), p)["value"]
    assert box("Branch ( branch and specialization)") == full
    assert box("Branch") == full
    assert box("Specialization") == "AI and ML"
    # Dropdowns still pick the matching option.
    assert box("Branch", "select", ["CSE", "CSE (AI and ML)", "ECE"]) == "CSE (AI and ML)"
    # Without branch_full, a box asking both gets them combined.
    p["education"]["degree"]["branch_full"] = ""
    assert box("Branch (branch and specialization)") == "Computer Science and Engineering with Specialization in AI and ML"
