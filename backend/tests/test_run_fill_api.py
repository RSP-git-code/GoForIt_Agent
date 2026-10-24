import logging

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PROFILE = {"personal": {"full_name": "Ananya Rao", "email": "ananya.secret@example.com", "phone": "+91 9000012345"}}
FIELDS = [
    {"id": "gf-0", "label": "Full name", "kind": "text"},
    {"id": "gf-1", "label": "Mobile No.", "kind": "tel", "helper_text": "10 digits"},
    {"id": "gf-2", "label": "Why us?", "kind": "textarea"},
]


def test_run_fill_returns_a_plan():
    resp = client.post("/run-fill", json={"fields": FIELDS, "profile": PROFILE})
    assert resp.status_code == 200
    body = resp.json()
    by_id = {a["field_id"]: a for a in body["actions"]}
    assert by_id["gf-0"]["value"] == "Ananya Rao"
    assert by_id["gf-1"]["value"] == "9000012345"
    assert by_id["gf-2"]["status"] == "review"
    assert body["trace"][0] == "page_analyzer" and body["trace"][-1] == "assemble"


def test_bad_request_is_rejected():
    assert client.post("/run-fill", json={"fields": [{"label": "no id"}], "profile": {}}).status_code == 422


def test_profile_is_never_logged(caplog):
    with caplog.at_level(logging.DEBUG):
        client.post("/run-fill", json={"fields": FIELDS, "profile": PROFILE})
    logged = caplog.text
    for secret in ("ananya.secret@example.com", "9000012345", "Ananya Rao"):
        assert secret not in logged
