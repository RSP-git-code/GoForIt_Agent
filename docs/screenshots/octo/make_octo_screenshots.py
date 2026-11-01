"""Screenshots of Agent Octo's real side panel (octo.html + octo.css) in each mood, light and dark.
Octo's chat is filled with his real answers for the demo jobs (Anya Forger's made-up profile)."""
import pathlib
import subprocess
import sys
from html import escape

ROOT = pathlib.Path(sys.argv[1])            # the repo
OUT = pathlib.Path(sys.argv[2])             # where the PNGs go
TMP = pathlib.Path(sys.argv[3])             # scratch folder for the pages
CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"
PANEL = ROOT / "extension" / "sidepanel"
JD = ("Graduate Engineer Trainee (AI/ML)\nRequirements\nB.Tech / B.E. in Computer Science, graduating in 2027\n"
      "Strong Python and SQL\nHands-on with LangChain and RAG\nREST APIs with FastAPI\nDocker and Git\nCloud deployment on AWS\n"
      "Good to have\nKubernetes, Apache Spark")


def octo(text, links=()):
    row = "".join(f'<a href="#">{escape(t)}</a>' for t in links)
    return f'<div class="msg octo restored">{escape(text)}' + (f'<div class="links">{row}</div>' if row else "") + "</div>"


def me(text):
    return f'<div class="msg me long restored">{escape(text)}</div>'


def chips(*labels):
    return '<div class="chips">' + "".join(f"<button>{escape(l)}</button>" for l in labels) + "</div>"


HELLO = octo("Hi, I'm Octo 🐙 your job-fit buddy! Paste a job description, or select one on any page and "
             "right-click → Ask Agent Octo. I'll tell you if it's worth applying and what to brush up.")
SHOTS = {
    "idle": ("your job-fit buddy", HELLO + chips("What can you do?", "Upload a job description")),
    "thinking": ("reading the job…", HELLO + me(JD) + '<div class="msg octo restored"><span class="typing"><i></i><i></i><i></i></span></div>'),
    "cheer": ("89% match!", me(JD)
              + octo("Apply: you match this well (brush up AWS). You have 89% of the required skills.")
              + octo("You already have: Python, SQL, RAG, LangChain, FastAPI / Flask, REST APIs.")
              + octo("To brush up: AWS (2-3 weeks).", ["▶ freeCodeCamp (free)", "🎓 Coursera: AWS (audit for free)", "AWS Skill Builder (free courses)"])
              + chips("Write my why-us answer", "What does this company do?")),
    "happy": ("57% match", me("Backend Developer Intern\nRequirements\nPython, SQL, REST APIs, Git\nDocker and AWS for deployment\nUnit testing")
              + octo("Apply, and brush up Docker, AWS. You have 57% of the required skills.")
              + octo("To brush up: Docker (a weekend to 1 week).", ["▶ freeCodeCamp full course (free)", "▶ TechWorld with Nana"])
              + chips("How do I show Docker on my resume?")),
    "concerned": ("needs a Master's", me("Machine Learning Research Scientist\nRequirements\nM.Tech, MS or PhD in Computer Science or ML\n"
                                         "3+ years of research experience\nStrong PyTorch and Python")
                  + octo("Skip: this role asks for a Master's degree (M.Tech, MS or PhD). Your skills match it (Python, PyTorch, "
                         "deep learning, LLMs), so it's the degree, not you.")
                  + chips("Show me jobs that fit better")),
}

base = PANEL.as_uri() + "/"
page = (PANEL / "octo.html").read_text(encoding="utf8")
page = page.replace("<head>", f'<head>\n  <base href="{base}">', 1)
page = "\n".join(l for l in page.splitlines() if "<script" not in l)  # no extension code: a still picture
TMP.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
for theme in ("light", "dark"):
    for mood, (status, chat) in SHOTS.items():
        html = page.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">', 1)
        html = html.replace('class="idle"', f'class="{mood}"', 1)
        html = html.replace('<span id="status">your job-fit buddy</span>', f'<span id="status">{escape(status)}</span>', 1)
        html = html.replace('<main id="chat" aria-live="polite"></main>', f'<main id="chat" aria-live="polite">{chat}</main>', 1)
        html = html.replace('id="theme" type="button" title="Day / night sea">🌙', f'id="theme" type="button">{"🌙" if theme == "light" else "☀️"}', 1)
        f = TMP / f"octo-{mood}-{theme}.html"
        f.write_text(html, encoding="utf8")
        png = OUT / f"octo-{mood}-{theme}.png"
        # 1.8 s into the animations: the cheer is mid-jump with pom-poms up, "thinking" shows its dots.
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        "--window-size=520,700", "--virtual-time-budget=1800", f"--screenshot={png}", f.as_uri()],
                       check=True, capture_output=True)
        print(png.name)
