"""Rule classifier tests (ported from the Phase 2 extension tests)."""

import pytest

from services.rules import FREE_TEXT, classify


def d(label="", **extra):
    return {"id": "x", "label": label, "placeholder": "", "name": "", "element_id": "", "aria_label": "",
            "helper_text": "", "kind": "text", "options": [], **extra}


# Labels written the way real Indian campus and ATS forms phrase them.
CASES = [
    ("Full Name (as per records)", "personal.full_name"),
    ("Name of the Student", "personal.full_name"),
    ("First Name", "personal.first_name"),
    ("Surname", "personal.last_name"),
    ("Personal Email ID", "personal.email"),
    ("College email ID", "personal.college_email"),  # its own profile field since 2026-10-08
    ("Mob No.", "personal.phone"),
    ("WhatsApp Number", "personal.phone"),
    ("Alternate Mobile Number", "personal.alternate_phone"),
    ("Father's Mobile Number", None),
    ("Date of Birth (DD/MM/YYYY)", "personal.date_of_birth"),
    ("Gender", "personal.gender"),
    ("Category (GEN/OBC/SC/ST)", "personal.category"),
    ("Pincode", "personal.pincode"),
    ("Permanent Address", "personal.permanent_address"),
    ("10th Percentage", "education.class_10.percentage"),
    ("SSC %", "education.class_10.percentage"),
    ("Class X Board", "education.class_10.board"),
    ("Tenth year of passing", "education.class_10.year"),
    ("12th / Intermediate Percentage", "education.class_12.percentage"),
    ("Aggregate % in Class XII", "education.class_12.percentage"),
    ("HSC Board", "education.class_12.board"),
    ("12th Stream", "education.class_12.stream"),
    ("Name of 12th College", "education.class_12.school"),
    ("B.Tech CGPA (up to latest semester)", "education.degree.cgpa"),
    ("Current CGPA", "education.degree.cgpa"),
    ("B.Tech Percentage", "education.degree.percentage_equivalent"),
    ("College Name", "education.degree.college"),
    ("University", "education.degree.university"),
    ("Year of Passing", "education.degree.graduation_year"),
    ("Expected graduation year", "education.degree.graduation_year"),
    ("Branch", "education.degree.branch"),
    ("Discipline", "education.degree.branch"),
    ("Registration Number", "education.degree.registration_number"),
    ("University Roll No", "education.degree.registration_number"),
    ("No. of Active Backlogs", "education.degree.active_backlogs"),
    ("History of backlogs", "education.degree.backlog_history"),
    ("Gap in education (years)", "education.gap_years"),
    ("Reason for gap", "education.gap_reason"),
    ("LinkedIn Profile URL", "links.linkedin"),
    ("GitHub URL", "links.github"),
    ("Website", "links.portfolio"),
    ("Current location", "personal.current_city"),
    ("Preferred job location", "preferences.preferred_locations"),
    ("Willing to relocate anywhere in India?", "preferences.willing_to_relocate"),
    ("Are you legally authorized to work in India?", "preferences.work_authorization_india"),
    ("Will you require visa sponsorship?", "preferences.requires_sponsorship"),
    ("Expected CTC (LPA)", "preferences.expected_ctc"),
    ("Technical skills", "skills.all"),
    ("Programming languages known", "skills.languages"),
    ("Languages known", "languages_spoken"),
    ("Tell us about yourself", "standard_answers.about_me"),
    ("Current company", "experience.current_company"),
    ("B.Tech start month", "education.degree.start_month"),
    ("Month of graduation", "education.degree.graduation_month"),
    ("Expected graduation date (MM/YYYY)", "education.degree.graduation_date"),
    ("Degree start date", "education.degree.start_date"),
    ("Earliest start date", "preferences.available_from"),  # job availability, not education
    ("Month of passing 12th", "education.class_12.month"),
    ("Class X passing month", "education.class_10.month"),
    ("12th passing date (MM/YYYY)", "education.class_12.passing_date"),
    ("12th start month", "education.class_12.start_month"),
    ("Class X start date", "education.class_10.start_date"),
    ("Year of joining 12th", "education.class_12.start_year"),
    ("Country code", "personal.phone_country_code"),
    ("ISD Code", "personal.phone_country_code"),
]


@pytest.mark.parametrize("label,expected", CASES)
def test_classify(label, expected):
    assert classify(d(label)) == expected


def test_falls_back_to_name_and_id():
    assert classify(d(name="urls[GitHub]")) == "links.github"
    assert classify(d(name="job_application[first_name]")) == "personal.first_name"


def test_open_questions_only_in_text_boxes():
    assert classify(d("Why do you want to work with Acme?", kind="textarea")) == FREE_TEXT
    assert classify(d("Describe a project where you used Python", kind="textarea")) == FREE_TEXT
    assert classify(d("How did you hear about this job?", kind="select", options=["LinkedIn", "Other"])) is None


def test_consent_is_its_own_key():
    assert classify(d("I hereby declare that the above information is true", kind="checkbox", options=["I hereby declare"])) == "consent"


def test_file_inputs():
    assert classify(d("Resume/CV", kind="file")) == "resume_file"
    assert classify(d("Cover photo", kind="file")) == "file_other"


def test_phone_dropdown_is_the_country_code():
    assert classify(d("Mobile Phone", kind="select", options=["+1", "+91"])) == "personal.phone_country_code"
    assert classify(d("Mobile Phone", kind="tel")) == "personal.phone"


def test_saved_answers_never_used_for_choice_fields():
    opt_in = "Tell us more about yourself and we'll keep you up to date regarding upcoming events"
    assert classify(d(opt_in, kind="radio", options=["Yes", "No thanks, continue to apply"])) is None
    assert classify(d("Tell us about yourself", kind="textarea")) == "standard_answers.about_me"



def test_education_from_to_boxes():
    from_box = d("From", name="education-2--firstYearAttended")
    to_box = d("To", name="education-2--lastYearAttended")
    assert classify(from_box) == "education.entry.from"
    assert classify(to_box) == "education.entry.to"
    # A bare "To" with no education context is left alone.
    assert classify(d("To")) is None


def test_education_summary_only_from_visible_label():
    assert classify(d("To", name="education-summary")) != "education.summary"
    assert classify(d("Education", kind="text")) != "education.summary"
    assert classify(d("Education or relevant training", kind="textarea")) == "education.summary"



def test_captcha_boxes_are_never_profile_fields():
    assert classify(d("Captcha")) is None
    assert classify(d("Enter the characters shown in the image")) is None


def test_otp_boxes_are_never_filled_and_enter_name_is_the_name():
    # HCLTech sign-up (2026-10-20): "Enter OTP" named mobileOtp got the phone number; "Enter name *" stayed empty.
    assert classify({"label": "Enter OTP", "type": "text", "name": "mobileOtp"}) is None
    assert classify(d("One-time password")) is None and classify(d("Verification code")) is None
    assert classify({"label": "", "placeholder": "Enter name *", "type": "text", "name": "name"}) == "personal.full_name"
    assert classify(d("Enter mobile number *")) == "personal.phone"
    assert classify(d("Enter company name")) != "personal.full_name"


def test_marks_table_labels_from_column_headings():
    # HCLTech marks table: the extension labels boxes "<row> · <column heading>".
    assert classify(d("10th · School Name")) == "education.class_10.school"
    assert classify(d("12th · Obtained Percentage")) == "education.class_12.percentage"
    assert classify(d("10th · Marking Scheme")) == "education.marking_scheme"
    # A school roll number is NOT the college registration number (never guessed).
    assert classify(d("10th · Roll Number")) == "education.class_10.roll_number"
    assert classify(d("12th · Roll Number")) == "education.class_12.roll_number"
    assert classify(d("University Registration Number")) == "education.degree.registration_number"


def test_hcltech_ug_row_result_status_and_board_wording():
    from agents.mapper import map_field
    from services.option_match import match_option
    prof = {"education": {"degree": {"cgpa": "8.5", "graduation_year": "2099", "graduation_month": "05"}}}
    # "Result Status" is Declared / Awaited, never the marks (it used to get "80.3").
    f = {"id": "x", "label": "UG · Result Status", "kind": "select", "options": ["Select", "Declared", "Awaited"],
         "placeholder": "", "helper_text": "", "section": ""}
    assert classify(f) == "education.result_status"
    assert map_field(f, classify(f), prof)["value"] == "Awaited"
    f["options"] = ["Select", "Percentage", "CGPA / CPI"]
    f["label"] = "UG · Marking Scheme"
    assert map_field(f, classify(f), prof)["value"] == "CGPA / CPI"
    # One extra word ("State") and an abbreviation in brackets still find the board.
    opts = ["Select", "Telangana Board Of Intermediate Education", "Telangana State Board of Secondary Education"]
    assert match_option("Telangana State Board of Intermediate Education (TSBIE)", opts).option == opts[1]
    assert match_option("Karnataka State Board", opts) is None


def test_skillsets_and_one_line_lists():
    # Real form: "Current technical skillsets (if any)" stayed empty; certifications ran together in a one-line box.
    from agents.mapper import map_field
    prof = {"skills": {"languages": ["Python"], "ml_ai": ["LangChain"]},
            "certifications": [{"name": "IBM Generative AI", "issuer": "IBM"}, {"name": "AWS Academy Graduate", "issuer": "AWS Academy"}],
            "achievements": ["Research Team Co-Lead", "Hackathon finalist"]}
    f = {"id": "x", "label": "Current technical skillsets (if any)", "kind": "text", "options": [], "placeholder": "", "helper_text": "", "section": ""}
    assert classify(f) == "skills.all" and "Python" in map_field(f, "skills.all", prof)["value"]
    f["label"] = "Certifications and rankings/scores in practice portals (like HackerRank)"
    assert map_field(f, classify(f), prof)["value"] == "IBM Generative AI (IBM); AWS Academy Graduate (AWS Academy)"
    f["kind"] = "textarea"
    assert "\n" in map_field(f, classify(f), prof)["value"]
    f.update(kind="text", label="Special achievements (if any)")
    assert "\n" not in map_field(f, classify(f), prof)["value"]


def test_publications_and_memberships_are_facts_not_drafts():
    # Real form: publications got achievements; "professional bodies" got an AI draft calling certificates memberships.
    from agents.mapper import map_field
    prof = {"achievements": ["Research Team Co-Lead"], "certifications": [{"name": "IBM Generative AI", "issuer": "IBM"}],
            "publications": [], "memberships": ["Data Science Club, VIT-AP"]}
    pub = {"id": "x", "label": "Paper Publications and Presentations(Only 500 Words)", "kind": "textarea",
           "options": [], "placeholder": "", "helper_text": "", "section": ""}
    assert classify(pub) == "publications"
    a = map_field(pub, "publications", prof)
    assert a["value"] is None and "Publications" in a["reason"]                  # empty: left for you, not achievements
    mem = {**pub, "label": "Associations and Affiliation with Professional Bodies"}
    assert classify(mem) == "memberships"
    assert map_field(mem, "memberships", prof)["value"] == "Data Science Club, VIT-AP"   # never the certificates


def test_workday_education_years_and_field_of_study():
    # Real Workday form: two boxes labelled just "Year" (ids say first/lastYearAttended); "Field of Study" picker.
    from agents.mapper import map_field
    prof = {"education": {"degree": {"start_year": "2023", "graduation_year": "2027", "branch": "Computer Science and Engineering"}}}
    for which, want in (("first", "2023"), ("last", "2027")):
        f = {"id": "x", "label": "Year", "element_id": f"education-832--{which}YearAttended-dateSectionYear-input",
             "kind": "text", "section": "Education", "options": [], "placeholder": "", "helper_text": "", "name": ""}
        assert map_field(f, classify(f), prof)["value"] == want
    study = {"id": "s", "label": "Field of Study", "kind": "combobox", "section": "Education", "options": [],
             "placeholder": "", "helper_text": "", "name": "", "element_id": ""}
    assert map_field(study, classify(study), prof)["value"][:2] == ["Computer Science and Engineering", "Computer Science"]
    assert classify({"label": "Education", "kind": "textarea"}) == "education.summary"
