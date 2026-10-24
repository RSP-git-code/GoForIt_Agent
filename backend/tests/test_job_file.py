"""Agent Octo's job-description upload: PDF / .txt -> text, with clear errors for what can't be read."""

import base64

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_pdf(lines: list[str]) -> bytes:
    """A minimal one-page PDF with the given text lines (built by hand: no PDF library needed)."""
    content = "BT /F1 12 Tf 72 720 Td 16 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


def upload(name: str, data: bytes):
    return client.post("/octo/read-file", json={"name": name, "data_base64": base64.b64encode(data).decode()})


def test_pdf_text_comes_back_line_by_line():
    resp = upload("QC Associate JD.pdf", make_pdf(["Required Hard Skills:", "Proficient in MINITAB or SPSS systems."]))
    assert resp.status_code == 200
    assert resp.json()["pages"] == 1
    assert resp.json()["text"].splitlines() == ["Required Hard Skills:", "Proficient in MINITAB or SPSS systems."]


def test_txt_file_is_read_as_is():
    assert upload("jd.txt", b"Requirements:\n- Python").json()["text"] == "Requirements:\n- Python"


def test_unreadable_files_get_a_clear_message():
    assert "PDF or .txt" in upload("jd.docx", b"PK\x03\x04 not a pdf").json()["detail"]
    assert "couldn't open" in upload("broken.pdf", b"%PDF-1.4 garbage").json()["detail"]
    assert upload("big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024)).status_code == 400
