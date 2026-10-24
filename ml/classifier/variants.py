"""Hand-written field wordings (Indian campus / TPO forms) and augmentation.

Greenhouse forms rarely ask Class 10/12 marks, CGPA, backlogs or JEE ranks, so
these wordings fill that gap. They are TRAINING data only: the test set uses
real forms, so the score never rewards memorising my own phrasing.
"""

import random
import re

# key -> label wordings. A tuple (label, kind, options) sets the box type.
HANDWRITTEN = {
    "personal.full_name": ["Full Name", "Name of the Candidate", "Student Name", "Name (as per 10th certificate)",
                           "Candidate's Full Name", "Name in Full (Capital Letters)", "Applicant Name", "Your Full Name",
                           "Name as per Aadhaar", "Name of Student"],
    "personal.first_name": ["First Name", "Given Name", "Fname", "First name (as per records)"],
    "personal.middle_name": ["Middle Name", "Middle name (if any)", "Father's Name / Middle Name"],
    "personal.last_name": ["Last Name", "Surname", "Family Name", "Lname"],
    "personal.email": ["Email ID", "Personal Email", "E-mail Address", "Mail ID", "Email (Gmail preferred)",
                       "Personal Mail ID", "Email Id (personal)", "Contact Email"],
    "personal.college_email": ["College Email ID", "Institute Mail ID", "University Email", "Official College Email",
                               "College mail id (ending with .ac.in)", "VIT Email ID"],
    "personal.phone": ["Mobile Number", "Mob No.", "Contact Number", "Phone No.", "WhatsApp Number",
                       "Mobile No. (10 digits)", "Contact No", "Primary Mobile Number", "Cell Number", "Ph. No."],
    "personal.alternate_phone": ["Alternate Mobile Number", "Alternate Contact No.", "Secondary Phone Number",
                                 "Parent's / Alternate Number"],
    "personal.date_of_birth": ["Date of Birth", "DOB", "D.O.B (DD/MM/YYYY)", "Birth Date", "Date of birth (as per 10th marksheet)"],
    "personal.gender": [("Gender", "radio", ["Male", "Female", "Other"]), ("Sex", "select", ["Male", "Female"]),
                        ("Gender", "select", ["Select", "Male", "Female", "Prefer not to say"])],
    "personal.category": [("Category", "select", ["General", "OBC", "SC", "ST", "EWS"]), "Caste Category", "Reservation Category"],
    "personal.nationality": ["Nationality", "Citizenship", "Country of Citizenship"],
    "personal.current_city": ["Current City", "City of Residence", "Current Location", "Present City", "Where are you currently located?"],
    "personal.current_state": ["State", "Current State", "State of Residence"],
    "personal.permanent_city": ["Hometown", "Native Place", "Permanent City", "Home Town / Native City"],
    "personal.permanent_state": ["Home State", "Native State", "Permanent State"],
    "personal.permanent_address": ["Permanent Address", "Residential Address", "Address for Communication", "Full Postal Address"],
    "personal.pincode": ["Pincode", "PIN Code", "Postal Code", "Zip Code", "Area Pin"],
    "links.linkedin": ["LinkedIn Profile Link", "LinkedIn URL", "Linkedin ID", "LinkedIn profile (public link)"],
    "links.github": ["GitHub Profile", "GitHub Link", "Github ID / URL", "Git repository profile link"],
    "links.portfolio": ["Portfolio Website", "Personal Website", "Portfolio Link (if any)", "Website / Blog"],
    "links.leetcode": ["LeetCode Profile", "LeetCode ID", "Leetcode link", "Coding profile (LeetCode)"],
    "links.resume_link": ["Resume Drive Link", "Google Drive link of Resume", "Resume link (view access)", "CV link (Drive/OneDrive)"],
    "education.degree.name": [("Degree", "select", ["B.Tech", "B.E.", "M.Tech", "MCA"]), "Course", "Current Degree",
                              "Highest Qualification", "Program Enrolled", "UG Degree"],
    "education.degree.branch": [("Branch", "select", ["CSE", "IT", "ECE", "EEE", "Mechanical"]), "Department", "Stream (UG)",
                                "Branch of Study", "Discipline", "Engineering Branch"],
    "education.degree.specialization": ["Specialization", "Specialisation (if any)", "Minor / Specialization"],
    "education.degree.college": ["College Name", "Institute Name", "Name of the College", "Current College / University",
                                 "Institution", "Name of Institute (UG)"],
    "education.degree.university": ["University", "Affiliated University", "University Name"],
    "education.degree.registration_number": ["Registration Number", "Reg. No.", "Roll Number", "Enrollment No.",
                                             "University Roll No", "Register Number", "USN", "Hall Ticket Number"],
    "education.degree.cgpa": ["CGPA", "B.Tech CGPA", "Current CGPA (out of 10)", "UG CGPA till last semester",
                              "Aggregate CGPA", "CGPA (upto latest sem)", "Graduation CGPA", "Cumulative GPA", "Degree CGPA"],
    "education.degree.percentage_equivalent": ["B.Tech Percentage", "UG Aggregate %", "Graduation Percentage",
                                               "Degree Percentage (CGPA x 10)", "Engineering Aggregate Percentage"],
    "education.degree.graduation_year": [("Year of Passing", "select", ["2025", "2026", "2027", "2028"]), "Passing Out Year",
                                         "Batch", "Graduation Year", "Expected Year of Graduation", "YOP (UG)", "Passout Batch"],
    "education.degree.start_year": ["Year of Joining (UG)", "B.Tech Start Year", "Admission Year", "Joining Year of Degree"],
    "education.degree.status": [("Degree Status", "select", ["Pursuing", "Completed"]),
                                ("Highest Qualification - Completed or Pursuing?", "select", ["Completed", "Pursuing"]),
                                ("Current status of your degree", "radio", ["In progress", "Completed"])],
    "education.degree.active_backlogs": [("Active Backlogs", "select", ["0", "1", "2", "3+"]), "No. of Current Arrears",
                                         "Number of Active Backlogs", "Standing Arrears", "Current Backlogs (if any)"],
    "education.degree.backlog_history": ["History of Backlogs", "Total Backlogs (cleared + active)", "History of Arrears",
                                         "Number of backlogs till date"],
    "education.class_12.percentage": ["12th Percentage", "Class XII %", "Intermediate Marks (%)", "HSC Percentage",
                                      "12th Aggregate", "Senior Secondary %", "Inter Percentage", "PUC Percentage",
                                      "Class 12 Marks/CGPA", "XII Std Percentage", "12th Grade Score"],
    "education.class_12.board": [("12th Board", "select", ["CBSE", "ICSE/ISC", "State Board"]), "Class XII Board",
                                 "Intermediate Board", "HSC Board Name"],
    "education.class_12.school": ["12th School/College Name", "Junior College Name", "Intermediate College", "Name of School (XII)"],
    "education.class_12.year": ["12th Year of Passing", "Class XII Passing Year", "Intermediate Passout Year", "HSC Year"],
    "education.class_12.stream": ["12th Stream", "Intermediate Group (MPC/BiPC)", "Class XII Stream"],
    "subject_marks": ["12th Maths Marks", "Mathematics % in Class XII", "Maths score in Intermediate"],
    "education.class_10.percentage": ["10th Percentage", "Class X %", "SSC Marks (%)", "Tenth Aggregate", "Matriculation %",
                                      "SSLC Percentage", "10th Std Percentage", "Class 10 Marks/CGPA", "X Std %",
                                      "10th CGPA / Percentage", "Secondary School %"],
    "education.class_10.board": [("10th Board", "select", ["CBSE", "ICSE", "State Board"]), "Class X Board", "SSC Board Name"],
    "education.class_10.school": ["10th School Name", "Name of School (X)", "SSC School"],
    "education.class_10.year": ["10th Year of Passing", "Class X Passing Year", "SSC Passout Year", "Year of Matriculation"],
    "education.gap_years": [("Gap in Education (years)", "select", ["0", "1", "2"]), "Year Gap", "Any gap in studies? (in years)",
                            "Education Gap"],
    "education.entrance_exams.jee_main": ["JEE Main Percentile", "JEE Mains Score", "JEE Main Rank/Percentile"],
    "education.entrance_exams.jee_advanced": ["JEE Advanced Rank", "JEE Adv. AIR"],
    "skills.all": ["Technical Skills", "Key Skills", "Skill Set", "Technologies Known", "Tools & Technologies"],
    "skills.languages": ["Programming Languages Known", "Coding Languages", "Languages you code in"],
    "languages_spoken": ["Languages Known", "Languages Spoken", "Language Proficiency"],
    "projects.all": ["Projects", "Major Projects", "Academic Projects", "Projects done"],
    "certifications.all": ["Certifications", "Certificates / Courses", "Online Certifications"],
    "achievements": ["Achievements", "Awards and Achievements", "Extra-curricular Activities", "Hackathons / Competitions"],
    "experience.summary": ["Internship Experience", "Work Experience (if any)", "Previous Internships", "Industry Experience"],
    "experience.total_years": [("Total Experience", "select", ["Fresher", "0-1 years", "1-2 years"]), "Years of Experience",
                               "Work Ex (in months/years)", "Total Work Experience"],
    "experience.current_company": ["Current Company", "Current Organisation", "Present Employer"],
    "experience.current_title": ["Current Designation", "Present Designation", "Current Job Title"],
    "preferences.notice_period": ["Notice Period", "Notice period (in days)", "Serving notice?"],
    "preferences.available_from": ["When can you join?", "Earliest Joining Date", "Date of availability to join",
                                   "How soon can you join?", "Available to join from"],
    "preferences.willing_to_relocate": [("Willing to relocate?", "radio", ["Yes", "No"]), "Ready to relocate anywhere in India?",
                                        "Open to relocation", "Are you okay with relocating to Bangalore?"],
    "preferences.preferred_locations": ["Preferred Location", "Preferred Job Location(s)", "Location Preference"],
    "preferences.expected_ctc": ["Expected CTC", "Expected Stipend", "Expected Salary (LPA)", "Salary Expectation"],
    "preferences.has_job_offer": [("Do you already have an offer?", "radio", ["Yes", "No"]), "Placed already?",
                                  "Holding any offer letter?", "Already placed through campus?"],
    "preferences.work_authorization_india": [("Are you authorized to work in India?", "radio", ["Yes", "No"])],
    "resume_file": [("Upload Resume", "file", []), ("Resume (PDF only)", "file", []), ("Attach CV", "file", [])],
    "standard_answers.about_me": [("Tell us about yourself", "textarea", []), ("Brief introduction", "textarea", []),
                                  ("Profile Summary", "textarea", []), ("About You", "textarea", [])],
    "standard_answers.why_hire_me": [("Why should we hire you?", "textarea", []), ("Why are you a good fit for this role?", "textarea", [])],
    "standard_answers.strengths": [("Your strengths", "textarea", []), ("What are your key strengths?", "textarea", [])],
    "standard_answers.weaknesses": [("Your weaknesses", "textarea", []), ("Areas of improvement", "textarea", [])],
    "free_text_question": [("Why do you want to join our company?", "textarea", []),
                           ("Describe a challenging project you worked on.", "textarea", []),
                           ("What do you know about our company?", "textarea", []),
                           ("Explain your best project in 100 words.", "textarea", [])],
    "consent": [("I hereby declare that the information provided is true to the best of my knowledge.", "checkbox", ["I agree"]),
                ("Declaration", "checkbox", ["I confirm the above details are correct"])],
    "none": ["How did you come to know about this opportunity?", "Referral Code (if any)", "Name of the referrer",
             "Father's Name", "Mother's Occupation", "Aadhaar Number", "PAN Number", "Blood Group", "T-shirt Size",
             "Emergency Contact Name"],
}

SECTIONS = {
    "personal": ["Personal Details", "Basic Information", "Contact Details"],
    "links": ["Profiles", "Online Presence"],
    "education": ["Academic Details", "Educational Qualification", "Education"],
    "experience": ["Work Experience", "Internships"],
    "preferences": ["Other Details", "Job Preferences"],
}

# Abbreviations and synonyms swapped during augmentation (both directions).
SWAPS = [("percentage", "%"), ("percentage", "marks"), ("number", "no."), ("mobile", "mob"), ("mobile", "contact"),
         ("date of birth", "dob"), ("year", "yr"), ("10th", "class x"), ("10th", "ssc"), ("12th", "class xii"),
         ("12th", "intermediate"), ("email id", "e-mail"), ("email", "mail id"), ("university", "univ"),
         ("college", "institute"), ("b.tech", "btech"), ("b.tech", "b.e."), ("address", "addr"), ("qualification", "qual"),
         ("profile", "url"), ("current", "present"), ("name", "full name"), ("cgpa", "gpa")]


def descriptor(key: str, item) -> dict:
    label, kind, options = (item, "text", []) if isinstance(item, str) else item
    return {"label": label, "kind": kind, "options": options, "placeholder": "", "name": "", "aria_label": "",
            "helper_text": "", "section": "", "label_key": key}


def handwritten() -> list[dict]:
    return [descriptor(key, item) for key, items in HANDWRITTEN.items() for item in items]


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 5:
        return word
    i = rng.randrange(1, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def augment(d: dict, label: str, rng: random.Random, n: int = 3) -> list[dict]:
    """n new versions of a field description: case, abbreviations, typos, required marks, sections, missing hints."""
    out = []
    for _ in range(n):
        v = dict(d)
        text = v.get("label") or ""
        for a, b in rng.sample(SWAPS, len(SWAPS)):
            src, dst = (a, b) if rng.random() < 0.5 else (b, a)
            if re.search(rf"(?<![a-z]){re.escape(src)}(?![a-z])", text, re.I) and rng.random() < 0.6:
                text = re.sub(rf"(?<![a-z]){re.escape(src)}(?![a-z])", dst, text, count=1, flags=re.I)
        r = rng.random()
        text = text.lower() if r < 0.25 else text.upper() if r < 0.35 else text.title() if r < 0.5 else text
        if rng.random() < 0.15:
            words = text.split()
            if words:
                k = rng.randrange(len(words))
                words[k] = _typo(words[k], rng)
                text = " ".join(words)
        if not re.search(r"optional|if any", text, re.I):
            text += rng.choice(["", "", " *", ":", " (required)"])
        v["label"] = text
        for extra in ("placeholder", "name", "helper_text"):
            if v.get(extra) and rng.random() < 0.4:
                v[extra] = ""
        group = label.split(".")[0]
        if not v.get("section") and group in SECTIONS and rng.random() < 0.4:
            v["section"] = rng.choice(SECTIONS[group])
        out.append(v)
    return out
