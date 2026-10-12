# niyora-ai
AI-powered municipal permit eligibility checker with explainable decisions and smart document guidance.

## Problem

Municipal permit processes can be difficult to understand before an application is submitted. Niyora AI demonstrates how an applicant can receive a transparent, rule-by-rule sample eligibility check, see what information or documents are missing, and understand suggested next steps.

> **Sample rules only, not official municipal requirements.** Results are not approvals, legal decisions, or a substitute for contacting the relevant municipal office.

## Features

- Dynamic Trade Licence and Building Permit forms driven by JSON rule and field metadata.
- Deterministic eligibility results with pass, fail, and unknown criteria.
- Weighted readiness score, prioritized next steps, and document completeness reported separately.
- Traceable rule details, SHA-256 result fingerprint, and downloadable Markdown/plain-text report.
- Deterministic what-if comparisons that do not change applicant inputs.
- Staff analytics over synthetic example batches.
- English and Hindi interface strings with English fallback.
- Grounded assistant fallback works offline; optional OpenAI responses require `OPENAI_API_KEY`.
- Ready applicant, incomplete case, and rule failure demo scenarios.

## What makes it different

- **Deterministic engine:** the same supplied inputs and rules produce the same status and score.
- **Rule traceability:** each criterion links to the JSON rule used in its evaluation.
- **Fingerprint:** a SHA-256 digest helps identify the exact inputs, permit type, and rules version used.
- **What-if:** compare one hypothetical field or document change without mutating the applicant's actual form.
- **Staff analytics:** aggregate outcomes and common blockers from a synthetic batch.
- **Offline fallback:** assistant intents are answered from the computed result without network access. The optional LLM is guarded and its output is checked.

## Architecture

```text
app.py (Streamlit UI)
  ├── data/permit_rules.json ──> core/eligibility.py
  │                              └── core/scoring.py
  ├── data/demo_applicants.json ─> scenario loading + staff batch
  ├── core/assistant.py ─────────> grounded fallback / optional OpenAI
  ├── core/report.py ────────────> Markdown and text report
  └── data/strings.json ─────────> core/i18n.py ──> English / Hindi UI

tests/ ──> pytest and Streamlit AppTest
```

## Setup and run (Windows PowerShell)

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

To run the tests:

```powershell
python -m pytest -q
```

The assistant works in offline mode without an API key. To enable its optional LLM path, create a local `.env` file based on `.env.example` and set `OPENAI_API_KEY` there.

## Demo scenarios

Use the sidebar buttons to load these synthetic cases for the selected permit:

- **Ready applicant:** sample criteria and documents are complete.
- **Incomplete case:** some required information and documents are missing.
- **Rule failure:** one or more supplied values fail a sample rule.

The staff view includes 12 synthetic applicants for each permit type.

## Limitations

- All permit rules, field values, document requirements, and weights are illustrative synthetic examples; they are not official municipal rules.
- This demo does not submit applications, contact municipal systems, verify uploaded documents, or provide real integrations.
- Eligibility results and readiness scores do not indicate or guarantee a real permit decision.
- This project is not legal advice. Contact the relevant municipal office for official requirements and decisions.
- Hindi UI strings are initial translations and need review by a native Hindi speaker.

## Security notes

- Never commit `.env` or an API key. `.env` is excluded by `.gitignore`; only the empty-key `.env.example` template belongs in source control.
- Do not enter real personal, financial, or otherwise sensitive applicant information into this demonstration.
- The report deliberately does not include raw applicant input fields.
