from services.option_match import match_option, mentions


def pick(value, options):
    m = match_option(value, options)
    return (m.option, m.exact) if m else None


def test_exact_and_synonyms():
    assert pick("Female", ["Select", "Male", "Female"]) == ("Female", True)
    assert pick("Female", ["--", "M", "F"]) == ("F", True)
    assert pick("B.Tech", ["High School", "Bachelor's Degree", "Master's Degree"]) == ("Bachelor's Degree", True)
    assert pick("Central Board of Secondary Education (CBSE)", ["CBSE", "ICSE", "State Board"]) == ("CBSE", True)
    assert pick("Computer Science and Engineering", ["Choose", "CSE", "ECE"]) == ("CSE", True)
    assert pick("Yes", ["--", "Yes", "No"]) == ("Yes", True)


def test_numeric_ranges():
    assert pick("93.4", ["Below 60%", "60-90", "Above 90%"]) == ("Above 90%", True)
    assert pick("8.42", ["Below 6", "6 to 8", "8 to 10"]) == ("8 to 10", True)
    assert pick("72", ["< 60", "60 - 75", "75+"]) == ("60 - 75", True)


def test_partial_and_none():
    assert pick("Data Science and Engineering", ["Data Science", "Other"]) == ("Data Science", False)
    assert pick("Java", ["JavaScript", "Python"]) is None
    assert pick("", ["Yes", "No"]) is None
    assert pick("Anything", ["Select...", "--"]) is None


def test_mentions():
    assert mentions("CSE (AI and ML)", "Computer Science and Engineering")
    assert mentions("CSE (AI & ML)", "AI and ML")
    assert not mentions("ECE", "Computer Science and Engineering")


def test_numbered_options():
    assert pick("Female", ["a. Male", "b. Female", "c. Prefer not to say"]) == ("b. Female", True)
    assert pick("Yes", ["(a) Yes", "(b) No"]) == ("(a) Yes", True)
    assert pick("B.Tech", ["1. B.Tech", "2. M.Tech"]) == ("1. B.Tech", True)
    assert pick("B.Tech", ["B.Tech", "M.Sc"]) == ("B.Tech", True)  # "B.Tech" itself is not a list marker
