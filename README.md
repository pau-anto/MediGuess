# 🩺 MediGuess

> A serious game where you diagnose clinical cases — and learn to reason like the model that's playing alongside you.

**MediGuess** is an educational serious game built for the 4IABD annual project. The player examines a clinical case (symptoms, patient profile, vital signs) and proposes a diagnosis. A machine learning model predicts the disease in parallel, and an **explainability layer (SHAP)** reveals *why* it decided that way. The game lives in the gap between the player's reasoning and the model's.

> ⚠️ **MediGuess is a learning tool, not a medical device.** It must never be used for real self-diagnosis or clinical decisions.

---

## Table of contents

- [Concept](#concept)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Data sources](#data-sources)
- [Code quality](#code-quality)
- [Roadmap](#roadmap)
- [Team](#team)
- [License](#license)

---

## Concept

The pedagogy is the point: instead of guessing an answer, the player learns to weigh evidence the way the model does. After each case, MediGuess shows the **top 3 factors** that drove the model's prediction and contrasts them with the player's own reasoning.

Three pillars guide the project:

- **Pedagogical** — teach clinical reasoning, not trivia.
- **Community** — leaderboards, cooperative mode, community-submitted cases.
- **Honest** — an explicit learning tool, never a diagnostic authority.

## Features

### Core (must-have)
- Play through a clinical case: review information, propose a diagnosis.
- Scoring based on the reasoning process, not just the final answer.
- Template-based pedagogical feedback derived from the model's top 3 factors.
- Community leaderboard.

### Stretch (cancellable if behind schedule)
- Cooperative multiplayer mode (roles: ER physician, radiologist, etc.).
- Community-submitted cases.
- "Real cases" hard mode powered by MIMIC-III.
- Generative feedback via RAG + LLM.
- Severity estimation.
- Infrastructure as Code (Terraform / AWS CDK).

## Architecture

```
Patient case ──▶ ML model ──▶ SHAP ──▶ Top 3 factors ──▶ Feedback
 (symptoms,      (XGBoost/      (local                    (template = core,
  vitals)         Random        explanation)               RAG = stretch)
                  Forest)
```

Deployed on AWS:

| Need                     | AWS service                          |
|--------------------------|--------------------------------------|
| Frontend hosting         | S3 + CloudFront                      |
| API & inference          | API Gateway + Lambda                 |
| Scores / leaderboard     | DynamoDB                             |
| Dataset & model artifacts| S3                                   |
| Deployment (stretch)     | Terraform / AWS CDK (full-serverless)|

## Tech stack

> ⚠️ **To be finalized by the team.** Update this section once decided.

- **ML / backend:** Python (scikit-learn / XGBoost, SHAP) — *proposed*
- **Frontend:** _TBD_
- **Cloud:** AWS
- **CI / quality:** linter + formatter (see [Code quality](#code-quality))

## Repository structure

```
mediguess/
├── README.md
├── LICENSE
├── .gitignore
├── .github/
│   └── workflows/        # CI (lint, tests) — to be added
├── docs/                 # reports, diagrams, design notes
├── data/                 # data exploration scripts (NOT raw data — see .gitignore)
├── ml/                   # model training, evaluation, SHAP
│   ├── notebooks/
│   ├── src/
│   └── tests/
├── backend/              # API, inference, feedback logic
│   └── src/
├── frontend/             # game UI (stack TBD)
└── infra/                # Infrastructure as Code (stretch)
```

> Adjust folders to match the stack once the team has decided. This layout is a starting point, not a constraint.

## Getting started

> These instructions will firm up once the stack is chosen. Baseline for the Python parts:

```bash
# 1. Clone
git clone https://github.com/<org-or-user>/mediguess.git
cd mediguess

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the linter & formatter
black .
pylint ml backend
```

## Data sources

MediGuess uses **simulated / educational datasets**; it is not trained on identifiable patient data in its core mode.

- **Core dataset:** patient-profile dataset (symptoms + vital signs + severity). Free, immediate access.
- **Advanced (stretch):** [MIMIC-III](https://physionet.org/content/mimiciii/1.4/) — real ICU data, hosted on AWS, free but credential-gated (PhysioNet training + DUA). See `docs/` for the access procedure.

⚠️ Raw datasets are **never committed** to the repo (see `.gitignore`). Document where to download them in `data/README.md`.

## Code quality

Per the course requirements, the project enforces:

- **Formatter:** [Black](https://black.readthedocs.io/) (`black .`)
- **Linter:** [Pylint](https://pylint.readthedocs.io/) (`pylint ml backend`)
- Configuration lives in `pyproject.toml` and `.pylintrc`.
- CI runs these checks on every pull request (see `.github/workflows/`).

## Roadmap

| Phase | Focus | Timeline |
|-------|-------|----------|
| 0 | Scoping & data exploration | Month 1 |
| 1 | ML core (training, SHAP) | Month 1–2 |
| 2 | Game loop & template feedback | Month 2–3 |
| 3 | AWS deployment | Month 3–4 |
| 4 | Community & stretch features | Month 4–5 |
| 5 | Report, docs, defense | Month 5–6 |

See the project tracking sheet for the detailed task breakdown.

## Team

| Name | Role | GitHub |
|------|------|--------|
| _TBD_ | _TBD_ | _@_ |
| _TBD_ | _TBD_ | _@_ |
| _TBD_ | _TBD_ | _@_ |
| _TBD_ | _TBD_ | _@_ |

4IABD — Annual project 2026.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
