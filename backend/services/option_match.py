"""Pick the dropdown/radio option that matches a profile value.

Handles exact text, synonyms common on Indian and Western forms
(F = Female, CBSE = Central Board of Secondary Education, B.Tech = Bachelor's
Degree), whole-word containment, and numeric ranges ("90-100", "Above 80%").
"""

import re
from dataclasses import dataclass

SYNONYMS = [
    {"male", "m", "man"},
    {"female", "f", "woman"},
    {"yes", "y", "true"},
    {"no", "n", "false"},
    {"general", "gen", "open", "unreserved", "ur", "general category"},
    {"obc", "other backward class", "other backward classes"},
    {"sc", "scheduled caste"},
    {"st", "scheduled tribe"},
    {"ews", "economically weaker section"},
    {"indian", "india"},
    {"b tech", "btech", "bachelor of technology", "bachelor s degree", "bachelors degree", "bachelor degree", "bachelors"},
    {"b e", "be", "bachelor of engineering"},
    {"m tech", "mtech", "master of technology"},
    {"cse", "computer science and engineering", "computer science engineering", "computer science"},
    {"ece", "electronics and communication engineering", "electronics and communication"},
    {"eee", "electrical and electronics engineering", "electrical and electronics"},
    {"it", "information technology"},
    {"mech", "mechanical", "mechanical engineering"},
    {"cbse", "central board of secondary education"},
    {"icse", "isc", "council for the indian school certificate examinations"},
    {"ai and ml", "ai ml", "aiml", "artificial intelligence and machine learning", "ai & ml"},
    {"0", "0 years", "fresher", "freshers", "no experience", "none", "nil"},
]

# Months: "July" = "Jul" = "07" = "7".
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
SYNONYMS += [{name, name[:3], f"{i:02d}", str(i)} for i, name in enumerate(MONTHS, start=1)]
SYNONYMS[-4].add("sept")

PLACEHOLDER = re.compile(r"^(|select.*|choose.*|please select|-+|none selected|pick one)$")


def normalize(s) -> str:
    s = str(s).lower().replace("&", " and ").replace("'", " ").replace("’", " ")
    return re.sub(r"[^a-z0-9+#%.]+", " ", s).replace(" . ", " ").strip(" .")


# Numbered options: "a. Yes", "b) No", "1. Male", "(c) Other". Needs a space after the
# marker, so "B.Tech" or "M.Sc" are never touched.
LIST_MARKER = re.compile(r"^\s*\(?[a-zA-Z0-9]{1,2}[.)]\s+")


def strip_marker(s) -> str:
    return LIST_MARKER.sub("", str(s), count=1)


def words(s: str) -> str:
    """Normalized text without dots or list markers, for word comparisons ("b.tech" -> "b tech", "a. Yes" -> "yes")."""
    return re.sub(r"\s+", " ", normalize(strip_marker(s)).replace(".", " ")).strip()


@dataclass
class Match:
    index: int
    option: str
    exact: bool


def _range_of(option: str):
    """(low, high) for options like '90-100', '60 to 70 %', 'Above 80%', 'Below 6'."""
    t = str(option).lower().replace("%", " ")  # raw text: normalize() would drop "-" and "<"
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", t)]
    if len(nums) == 2 and re.search(r"\d\s*(-|to)\s*\d", t):
        return min(nums), max(nums)
    if len(nums) == 1:
        if re.search(r"\b(above|more than|greater than|over|atleast|at least)\b|>|\+", t):
            return nums[0], float("inf")
        if re.search(r"\b(below|less than|under|upto|up to)\b|<", t):
            return float("-inf"), nums[0]
    return None


def mentions(option: str, value: str) -> bool:
    """True if `option` contains `value`, or a synonym of it, as whole words.

    "CSE (AI and ML)" mentions "Computer Science and Engineering" (via CSE)
    and "AI and ML".
    """
    o, v = f" {words(option)} ", words(value)
    if not v:
        return False
    phrases = {v}
    for group in SYNONYMS:
        if v in group or any(len(w) >= 3 and f" {w} " in f" {v} " for w in group):
            phrases |= group
    return any(f" {p} " in o for p in phrases)


def match_option(value, options: list[str]) -> Match | None:
    v = words(value)
    if not v:
        return None
    opts = [words(o) for o in options]
    usable = [not PLACEHOLDER.match(o) for o in opts]

    # 1. Same text.
    for i, o in enumerate(opts):
        if usable[i] and o == v:
            return Match(i, options[i], True)

    # 2. Synonyms, including a synonym phrase inside a longer value:
    #    "Central Board of Secondary Education (CBSE)" -> "CBSE".
    for group in SYNONYMS:
        if v in group or any(len(w) >= 3 and f" {w} " in f" {v} " for w in group):
            for i, o in enumerate(opts):
                if usable[i] and o in group:
                    return Match(i, options[i], True)

    # 3. Numeric ranges: 8.42 -> "8-9", 93.4 -> "Above 90%".
    try:
        number = float(str(value).strip().rstrip("%"))
    except ValueError:
        number = None
    if number is not None:
        for i, o in enumerate(options):
            r = _range_of(o) if usable[i] else None
            if r and r[0] <= number <= r[1]:
                return Match(i, options[i], True)

    # 4. One contains the other as whole words. Prefer the longest overlap.
    best = None
    for i, o in enumerate(opts):
        if not usable[i] or len(o) < 2:
            continue
        if f" {o} " in f" {v} " or f" {v} " in f" {o} ":
            if best is None or len(o) > len(opts[best]):
                best = i
    if best is not None:
        return Match(best, options[best], False)

    # 5. Same words, one extra or missing: "Telangana State Board of Intermediate Education" (profile)
    #    vs "Telangana Board Of Intermediate Education" (HCLTech). Every meaningful word of the
    #    option must be in the value (or the other way round), with at least 3 such words, and
    #    the two may differ by one word at most. Only a single clear winner counts.
    stop = {"of", "the", "and", "for", "in", "at", "a", "an"}
    sig = lambda s: {w for w in s.split() if w not in stop}
    vw = sig(words(re.sub(r"\([^)]*\)", " ", str(value))))  # without "(TSBIE)"-style abbreviations
    scored = []
    for i, o in enumerate(opts):
        ow = sig(o)
        if not usable[i] or len(ow) < 3 or len(vw) < 3:
            continue
        if (ow <= vw or vw <= ow) and len(ow ^ vw) <= 1:
            scored.append(i)
    if len(scored) == 1:
        return Match(scored[0], options[scored[0]], False)
    return None
