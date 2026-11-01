# Go For It, Agent 

*Tired of retyping the same details on every job application?*

**GoForIt** is a personal project that uses AI agents to simplify the job and campus-placement application process. It helps autofill application forms, organize LinkedIn and Indeed job alerts, and evaluate how well an opportunity matches your profile.

Meet **Agent Octo 🐙**, your job-fit companion. It analyzes job requirements against your skills, identifies potential skill gaps, and points you towards free courses to help you bridge them.

The idea is simple: spend less time on repetitive applications and more time finding the right opportunities.

> **You're always in control.** GoForIt assists with form filling and job discovery, but never submits an application on your behalf. You review everything and make the final call.

**Note:** GoForIt is a personal project and is not available as a hosted or deployed service. If you'd like to try it, you can clone the repository and run it locally. The current implementation uses Ollama for local LLM inference. You can also adapt the AI integration to your preferred provider, such as Claude or ChatGPT, by modifying the relevant components and configuring your own API access. External provider usage may incur costs.

---

## Objectives

- **Simplify applications:** Reduce repetitive data entry across job and campus-placement application forms.
- **Smarter form detection:** Identify and classify form fields to determine what information they require.
- **Job discovery:** Organize job opportunities received through LinkedIn and Indeed email alerts.
- **Job-fit analysis:** Evaluate opportunities against the user's profile, qualifications, and skills.
- **Skill gap identification:** Highlight missing or relevant skills and recommend free learning resources.
- **User-controlled automation:** Assist with repetitive tasks while keeping application review and submission entirely in the user's hands.

---

## Methodology

GoForIt combines a Chrome extension, a local Python backend, and an agent-based workflow coordinated through LangGraph.

### 1. Profile Management

Users provide their personal, academic, and professional information through the Chrome extension. Profile data is stored locally using `chrome.storage.local`.

### 2. Form Detection and Classification

When the user selects **Fill this page**, the extension identifies available form fields. A fine-tuned field classifier helps determine the purpose and type of each field.

### 3. Agent-Based Form Filling

A LangGraph pipeline coordinates the AI agents involved in processing application forms. A small LLM served through Ollama supports language-based tasks, while the field classifier assists with identifying relevant information.

The system uses the user's stored profile to populate the corresponding fields.

### 4. Job Alert Scanning

GoForIt includes a daily job-alert scanning workflow for LinkedIn and Indeed notifications. Relevant opportunities are organized into an Excel file and can be linked with Google Calendar for tracking.

### 5. Job-Fit Analysis with Agent Octo

Agent Octo evaluates job requirements against the user's profile to estimate how well an opportunity matches their qualifications and skills.

It also identifies potential skill gaps and provides links to relevant free courses to help users improve their suitability for future opportunities.

### 6. Review and Submission

Filled fields receive visual indicators:

- **Green:** Information successfully filled.
- **Yellow:** Information requires review.
- **Red:** Information is missing.

GoForIt never submits applications automatically. Users review the information and submit applications themselves.

---

## Demo

Want to see GoForIt in action?

The demo walks through the application's workflow, including form filling, job-alert scanning, and Agent Octo's job-fit analysis.

**[Watch the GoForIt Demo](https://drive.google.com/file/d/1RGAL4Xed6XN2D8UmwhgOHOc2k5uhEQmH/view?usp=drive_link)**

---

## Output & Results

A look at GoForIt in action.

### 1. Chrome Extension

<!-- Add extension popup screenshot here -->

![GoForIt Extension](<img width="1904" height="987" alt="image" src="https://github.com/user-attachments/assets/890386cb-65fb-4787-b701-c86e8d1259d9" />
)

### 2. Automated Form Filling

<!-- Add form filling screenshot here -->

![Form Filling](screenshots/form-filling.png)

### 3. Field Classification and Review

<!-- Add field status screenshot here -->

![Field Classification](screenshots/field-classification.png)

### 4. Job Alert Scanning

<!-- Add job alerts / Excel output screenshot here -->

![Job Alerts](screenshots/job-alerts.png)

### 5. Job-Fit Analysis — Agent Octo

<!-- Add job-fit analysis screenshot here -->

![Agent Octo](screenshots/agent-octo.png)

### 6. Skill Gap Recommendations

<!-- Add free course recommendation screenshot here -->

![Skill Recommendations](screenshots/skill-recommendations.png)

---

## Getting Started

GoForIt runs locally and requires a Python backend and a Chrome extension.

### Prerequisites

- Python 3.11
- Google Chrome
- Ollama
- Git

### 1. Clone the Repository

```bash
git clone YOUR_REPOSITORY_URL
cd GoForIt
```

### 2. Backend Setup

```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

The backend should be available at:

`http://127.0.0.1:8000`

Check its status by opening:

`http://127.0.0.1:8000/health`

### 3. Configure the Chrome Extension

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the `extension/` directory.
5. Click the GoForIt icon.
6. Select **Edit profile** and enter your information.
7. Open a supported application form and select **Fill this page**.

Your profile information is stored locally using `chrome.storage.local`.

### 4. Try the Demo Portal

Open `demo-site/index.html` to explore the fictional Ostania Tech application portal.

You can also import the sample profile:

`docs/demo/anya-forger-demo.json`

For offline test forms, refer to:

`test-forms/README.md`

---

## Job Alerts

GoForIt also includes a scheduled job-scanning workflow.

- **Automatic scan:** `install-daily-scan.ps1` registers a Windows scheduled task that runs daily at 8:30 AM.
- **Manual scan:** Run `check-jobs.bat` to trigger a scan manually.
- **Logs:** Available at `Documents\GoForIt\inbox-log.txt`.
- **Calendar integration:** Start the backend using `start-backend.bat` for the application tracking links.

The job-alert workflow uses the configured integrations and requires the relevant access and authentication.

---

## Testing

GoForIt includes tests for its Chrome extension, backend, and form-filling workflow.

```bash
# Extension unit tests
node --test "extension/tests/*.test.js"

# Headless Chrome form-filling tests
node extension/tests/run-harness.js

# Backend tests
pytest
```

---

## Architecture

The project combines browser-side form interaction with local AI processing and supporting job-alert workflows.

**Core components:**

| Component | Technology |
|---|---|
| Browser extension | JavaScript, Chrome Extension APIs |
| Backend | Python, FastAPI |
| Agent orchestration | LangGraph |
| Local LLM | Ollama |
| Field classification | Fine-tuned ML classifier |
| Job alert workflow | Python, Excel, Google Calendar integration |

For additional implementation details, refer to the project documentation.

- [Safety Rules](docs/RULES.md)
- [Project Metrics](docs/METRICS.md)

---

## Limitations & Future Improvements

GoForIt is an ongoing personal project. Some components are still being refined.

Areas of continued development include:

- Improving field classification accuracy across different application platforms.
- Fine-tuning the field classification model.
- Improving job-fit assessment and skill-gap identification.
- Expanding support for different application form structures.
- Exploring additional LLM integrations.

---

## Safety & Privacy

GoForIt is designed as an assistant, not an autonomous job-application bot.

- Applications are never submitted automatically.
- CAPTCHA solving is not supported.
- The project does not operate as a job-board bot.
- Profile information is stored locally in the Chrome extension.
- Local LLM inference is used in the current form-filling workflow.

Users are responsible for reviewing the information and deciding what to submit.

---

## Credits & Disclaimer

- **Character:** Anya Forger from *SPY×FAMILY*, created by Tatsuya Endo.
- **Artwork inspiration:** [Pinterest reference](https://www.pinterest.com/pin/614037730490952505/). The illustration used in the demo resume was hand-drawn by the project author, inspired by this reference.
- **Demo data:** The resume uses fictional personal, academic, and professional details created solely for demonstration and testing.

All rights to *SPY×FAMILY*, its characters, and associated original artwork belong to their respective copyright holders. GoForIt is an independent personal project and is not affiliated with, endorsed by, or sponsored by the creators or rights holders of *SPY×FAMILY*.

---

## License

The GoForIt source code is licensed under the [MIT License](LICENSE).

Third-party assets, characters, trademarks, and other materials remain subject to their respective owners' rights and are not included in the software license.
