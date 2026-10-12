"""Privacy-conscious Markdown and plain-text readiness reports."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date as Date
from typing import Any

from core.eligibility import load_rules

REPORT_TITLE = "Niyora AI Application Readiness Report"
DISCLAIMER = (
    "Sample rules only, not official municipal requirements. "
    "This report is not an approval or a legal decision."
)


def _report_sections(
    permit_type: str,
    result: Mapping[str, Any],
    generated_on: Date,
) -> list[tuple[str, list[str]]]:
    rules_version = result.get("rules_version")
    if not isinstance(rules_version, str):
        rules_version = load_rules().get("rules_version", "unknown")

    criteria = result.get("criteria", [])
    missing_documents = result.get("missing_documents", [])
    readiness = result.get("readiness", {})
    next_steps = result.get("next_steps", [])
    if not isinstance(criteria, list):
        raise ValueError("result criteria must be a list")
    if not isinstance(missing_documents, list):
        raise ValueError("result missing_documents must be a list")
    if not isinstance(readiness, Mapping):
        raise ValueError("result readiness must be an object")
    if not isinstance(next_steps, list):
        raise ValueError("result next_steps must be a list")

    criteria_lines: list[str] = []
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            raise ValueError("each criterion must be an object")
        rule_id = criterion.get("rule_id", "Unknown rule")
        status = criterion.get("status", "unknown")
        reason = criterion.get("reason", "No explanation provided.")
        criteria_lines.append(f"{rule_id} | {status} | {reason}")

    missing_lines: list[str] = []
    for document in missing_documents:
        if not isinstance(document, Mapping):
            raise ValueError("each missing document must be an object")
        missing_lines.append(
            str(document.get("label", document.get("id", "Unspecified document")))
        )

    breakdown = readiness.get("breakdown", [])
    if not isinstance(breakdown, list):
        raise ValueError("readiness breakdown must be a list")
    breakdown_lines: list[str] = []
    for item in breakdown:
        if not isinstance(item, Mapping):
            raise ValueError("each readiness breakdown item must be an object")
        breakdown_lines.append(
            f"{item.get('item', 'Unknown item')}: "
            f"{item.get('earned', 0)}/{item.get('weight', 0)} points"
        )

    next_step_lines: list[str] = []
    for step in next_steps:
        if not isinstance(step, Mapping):
            raise ValueError("each next step must be an object")
        next_step_lines.append(
            f"{step.get('priority', '?')}. {step.get('action', 'No action provided.')} "
            f"(impact: {step.get('impact_points', 0)} points)"
        )

    return [
        ("Report", [REPORT_TITLE]),
        ("Application", [f"Permit type: {permit_type}"]),
        ("Overall status", [str(result.get("status", "unknown"))]),
        ("Disclaimer", [DISCLAIMER]),
        ("Criteria", criteria_lines or ["None"]),
        ("Missing documents", missing_lines or ["None"]),
        (
            "Readiness",
            [f"Score: {readiness.get('score', 'Not available')}/100"]
            + (breakdown_lines or ["Breakdown: None"]),
        ),
        ("Prioritised next steps", next_step_lines or ["None"]),
        (
            "Reference",
            [
                f"Fingerprint: {result.get('fingerprint', 'Not available')}",
                f"Rules version: {rules_version}",
                f"Generated on: {generated_on.isoformat()}",
            ],
        ),
    ]


def _render_report(
    permit_type: str,
    result: Mapping[str, Any],
    lang: str,
    generated_on: Date | None,
    markdown: bool,
) -> str:
    if not isinstance(permit_type, str) or not permit_type.strip():
        raise ValueError("permit_type must be a non-empty string")
    if not isinstance(result, Mapping):
        raise TypeError("result must be a mapping")
    if lang != "en":
        raise ValueError(f"unsupported report language: {lang!r}")
    report_date = generated_on if generated_on is not None else Date.today()
    if not isinstance(report_date, Date):
        raise TypeError("date must be a datetime.date instance")

    sections = _report_sections(permit_type, result, report_date)
    if markdown:
        rendered = [f"# {REPORT_TITLE}"]
        for heading, lines in sections[1:]:
            rendered.extend(["", f"## {heading}"])
            rendered.extend(f"- {line}" for line in lines)
        return "\n".join(rendered)

    rendered = [REPORT_TITLE]
    for heading, lines in sections[1:]:
        rendered.extend(["", heading.upper()])
        rendered.extend(lines)
    return "\n".join(rendered)


def build_report_markdown(
    permit_type: str,
    result: Mapping[str, Any],
    lang: str = "en",
    date: Date | None = None,
) -> str:
    """Build a Markdown report without including raw applicant inputs."""
    return _render_report(permit_type, result, lang, date, markdown=True)


def build_report_text(
    permit_type: str,
    result: Mapping[str, Any],
    lang: str = "en",
    date: Date | None = None,
) -> str:
    """Build a plain-text report without including raw applicant inputs."""
    return _render_report(permit_type, result, lang, date, markdown=False)
