"""Draws docs/architecture.svg (GoForIt's agents), in the style of a paper figure."""
import sys
from html import escape

W, H = 1560, 820
FONT = "Lato, 'Segoe UI', Helvetica, Arial, sans-serif"
C = {  # fill, text
    "input": ("#cfcfcf", "#222"), "ext": ("#64b5f6", "#0d2a45"), "agent": ("#cdbbf2", "#2a1a52"),
    "model": ("#f57c00", "#fff"), "data": ("#a5d6a7", "#173d1a"), "you": ("#fff8d6", "#8b1a1a"),
    "out": ("#b3e5fc", "#0d2a45"),
}
out = []


def box(x, y, w, h, kind, lines, bold_first=True, size=15):
    fill, ink = C[kind]
    stroke = "#8b1a1a" if kind == "you" else "#555"
    sw = 3 if kind == "you" else 1
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
    n = len(lines)
    for i, t in enumerate(lines):
        ty = y + h / 2 + (i - (n - 1) / 2) * (size + 4) + size * 0.35
        weight = "700" if (i == 0 and bold_first) else "400"
        fs = size if i == 0 else size - 2
        out.append(f'<text x="{x + w / 2}" y="{ty:.1f}" text-anchor="middle" font-size="{fs}" font-weight="{weight}" fill="{ink}">{escape(t)}</text>')


def arrow(points, color="#444", dashed=False, width=2):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    marker = "url(#ah-blue)" if color != "#444" else "url(#ah)"
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} marker-end="{marker}"/>')


def text(x, y, t, size=14, color="#444", weight="400", anchor="start", italic=False):
    style = ' font-style="italic"' if italic else ""
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}"{style}>{escape(t)}</text>')


BLUE = "#1f5f8b"
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">')
out.append('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
           '<path d="M0,0 L10,5 L0,10 z" fill="#444"/></marker>'
           f'<marker id="ah-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
           f'<path d="M0,0 L10,5 L0,10 z" fill="{BLUE}"/></marker></defs>')
out.append(f'<rect width="{W}" height="{H}" fill="#fff"/>')

# ---------- 1. Fill this page ----------
text(20, 32, "1 · Fill this page", 19, "#222", "700")
text(185, 32, "Chrome extension (plain JS) + LangGraph agent pipeline", 15, "#666")
# backend container
out.append(f'<rect x="322" y="52" width="868" height="400" rx="8" fill="#f6f4fd" stroke="{BLUE}" stroke-width="1.5" stroke-dasharray="7 5"/>')
text(338, 73, "Backend · FastAPI + LangGraph · 127.0.0.1 only (nothing leaves the laptop)", 13, BLUE, "700")

y1, h1 = 95, 78
box(20, y1, 120, h1, "input", ["Form page", "you opened it", "Workday, Oracle…"])
box(168, y1, 130, h1, "ext", ["Extract fields", "content script", "labels, options"])
box(342, y1, 150, h1, "agent", ["Page Analyzer", "what each field", "is asking for"])
box(522, y1, 150, h1, "agent", ["Mapper", "profile → values", "CGPA, dates, options"])
# decision diamond
cx, cy = 752, y1 + h1 / 2
out.append(f'<polygon points="{cx},{cy - 44} {cx + 58},{cy} {cx},{cy + 44} {cx - 58},{cy}" fill="#fff" stroke="#555"/>')
text(cx, cy - 3, "free-text", 13, "#222", "700", "middle")
text(cx, cy + 14, "questions?", 13, "#222", "700", "middle")
box(1030, y1, 140, h1, "agent", ["Assemble", "one fill plan"])
box(1218, y1, 150, h1, "ext", ["Apply in page", "green · yellow · red", "+ summary panel"])
box(1396, y1, 144, h1, "you", ["You review", "& submit", "(OTP, CAPTCHA too)"])

arrow([(140, cy), (166, cy)])
arrow([(298, cy), (340, cy)])
arrow([(492, cy), (520, cy)])
arrow([(672, cy), (692, cy)])
arrow([(810, cy), (1028, cy)])
text(905, cy - 8, "no", 13, "#444", "700", "middle")
arrow([(1170, cy), (1216, cy)])
arrow([(1368, cy), (1394, cy)])

# draft branch
y2, h2 = 232, 72
box(682, y2, 140, h2, "agent", ["Matcher", "job fit + picks", "your projects"])
box(852, y2, 140, h2, "agent", ["Drafter", "writes the answer"])
box(1030, y2, 140, h2, "agent", ["Verifier", "only your facts?", "length ok?"])
arrow([(cx, cy + 44), (cx, y2 - 2)])
text(cx + 8, cy + 66, "yes", 13, "#444", "700")
arrow([(822, y2 + h2 / 2), (850, y2 + h2 / 2)])
arrow([(992, y2 + h2 / 2), (1028, y2 + h2 / 2)])
arrow([(1100, y2), (1100, y1 + h1 + 2)])
text(1108, y2 - 18, "pass", 13, "#444", "700")
# retry loop under drafter/verifier
arrow([(1080, y2 + h2), (1080, y2 + h2 + 22), (922, y2 + h2 + 22), (922, y2 + h2 + 2)], color="#8b1a1a")
text(1001, y2 + h2 + 40, "rejected → retry (max 2), then flagged red", 12, "#8b1a1a", "700", "middle")

# local models
box(342, 296, 150, 70, "model", ["Field classifier", "MiniLM, trained; on", "once it beats rules"], size=14)
arrow([(417, 300), (417, y1 + h1 + 2)], dashed=True)
text(425, 222, "rules first,", 12, "#666", italic=True)
text(425, 237, "model second", 12, "#666", italic=True)
box(852, 382, 318, 58, "model", ["Small LLM · Qwen3 1.7B · Ollama (local)", "fine-tune in progress"], size=14)
arrow([(875, 382), (875, y2 + h2 + 2)], dashed=True)
arrow([(1150, 382), (1150, y2 + h2 + 2)], dashed=True)
text(682, 410, "Ollama offline? drafts are", 12, "#666", italic=True)
text(682, 425, "skipped; everything else fills", 12, "#666", italic=True)

# profile
box(168, 300, 130, 64, "data", ["Your profile", "chrome.storage", ".local"], size=14)
arrow([(233, 300), (233, y1 + h1 + 2)])
text(240, 270, "sent with", 12, "#666", italic=True)
text(240, 285, "the fields", 12, "#666", italic=True)

# ---------- 2. Agent Octo ----------
y3 = 500
text(20, y3, "2 · Agent Octo", 19, "#222", "700")
text(158, y3, "side-panel chat", 15, "#666")
yb, hb = y3 + 20, 76
box(20, yb, 150, hb, "input", ["Job description", "pasted, selected", "or a PDF"])
box(200, yb, 190, hb, "agent", ["Coach agent", "required vs nice-to-have", "skills · degree, CGPA"])
box(420, yb, 170, hb, "out", ["Fit % + verdict", "Apply · Stretch · Skip", "cheers at 60%+"])
box(620, yb, 190, hb, "out", ["Missing skills", "effort + free courses", "+ how to show it"])
box(840, yb, 170, hb, "model", ["Local LLM", "answers follow-up", "questions"], size=14)
arrow([(170, yb + hb / 2), (198, yb + hb / 2)])
arrow([(390, yb + hb / 2), (418, yb + hb / 2)])
arrow([(590, yb + hb / 2), (618, yb + hb / 2)])
arrow([(810, yb + hb / 2), (838, yb + hb / 2)], dashed=True)

# ---------- 3. Inbox agent ----------
y4 = 660
text(20, y4, "3 · Inbox agent", 19, "#222", "700")
text(166, y4, "runs at 8:30 AM and 7 PM (Windows task)", 15, "#666")
yc, hc = y4 + 20, 76
box(20, yc, 170, hc, "input", ["Gmail (read-only)", "LinkedIn & Indeed", "job-alert emails"])
box(220, yc, 200, hc, "agent", ["Inbox agent", "1 alert → 1 row per job", "fit High · Medium · Low"])
box(450, yc, 150, hc, "data", ["Excel tracker", "local .xlsx", "no duplicates"])
box(630, yc, 190, hc, "out", ["Google Calendar", "\"Apply to N jobs\"", "9 AM / same evening"])
box(850, yc, 160, hc, "you", ["You apply", "✓ Applied · ✗ Expired"])
arrow([(190, yc + hc / 2), (218, yc + hc / 2)])
arrow([(420, yc + hc / 2), (448, yc + hc / 2)])
arrow([(600, yc + hc / 2), (628, yc + hc / 2)])
arrow([(820, yc + hc / 2), (848, yc + hc / 2)])
arrow([(930, yc + hc), (930, yc + hc + 22), (525, yc + hc + 22), (525, yc + hc + 2)], color=BLUE)
text(727, yc + hc + 40, "one click updates the tracker (and every repost of that job)", 12, BLUE, "700", "middle")

# ---------- legend ----------
lx, ly = 1110, 510
legend = [("ext", "Chrome extension (plain JS, MV3)"), ("agent", "AI agent (LangGraph / Python)"),
          ("model", "Local model on the laptop (no external AI APIs)"), ("data", "Your data, stays on the laptop"),
          ("input", "Input"), ("out", "Output to you"), ("you", "Only YOU do this: GoForIt never submits")]
for i, (kind, label) in enumerate(legend):
    fill, _ = C[kind]
    stroke, sw = ("#8b1a1a", 3) if kind == "you" else ("#555", 1)
    out.append(f'<rect x="{lx}" y="{ly + i * 34}" width="26" height="22" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
    text(lx + 38, ly + i * 34 + 16, label, 15, "#8b1a1a" if kind == "you" else "#333", "700" if kind == "you" else "400")
text(lx, ly + 7 * 34 + 14, "Never: submits forms, solves CAPTCHA/OTP, or automates", 13, "#555")
text(lx, ly + 7 * 34 + 31, "LinkedIn/Indeed (it only reads their alert emails).", 13, "#555")

out.append("</svg>")
open(sys.argv[1], "w", encoding="utf8").write("\n".join(out))
