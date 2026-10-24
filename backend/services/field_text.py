"""The field classifier's input: everything the page says about a field, in a fixed order.

Used both to build the training data (ml/classifier/build_dataset.py) and at
runtime (services/classifier.py), so the model always sees the same format:

    Grade-XII Board Name | section: Academic Details | type: select | options: CBSE, ICSE, State Board
"""


def field_text(d: dict) -> str:
    parts = [d.get("label") or ""]
    for name, key in (("placeholder", "placeholder"), ("name", "name"), ("aria", "aria_label"),
                      ("helper", "helper_text"), ("section", "section")):
        if d.get(key):
            parts.append(f"{name}: {d[key]}")
    parts.append(f"type: {d.get('kind') or 'text'}")
    if d.get("options"):
        parts.append("options: " + ", ".join(d["options"][:6]))
    return " | ".join(p for p in parts if p)
