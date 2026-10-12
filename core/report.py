"""Privacy-conscious Markdown and plain-text readiness reports."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date as Date
from typing import Any

from core.eligibility import load_rules
from core.i18n import t

REPORT_TITLE = "Niyora AI Application Readiness Report"
DISCLAIMER = (
    "Sample rules only, not official municipal requirements. "
    "This report is not an approval or a legal decision."
)


def _report_sections(
    permit_type: str,
    result: Mapping[str, Any],
    generated_on: Date,
    lang: str,
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
        translated_status = t(f"report.status.{status}", lang)
        criteria_lines.append(f"{rule_id} | {translated_status} | {reason}")

    missing_lines: list[str] = []
    for document in missing_documents:
        if not isinstance(document, Mapping):
            raise ValueError("each missing document must be an object")
        document_id = document.get("id")
        document_label = document.get(
            "label",
            document_id if isinstance(document_id, str) else "Unspecified document",
        )
        if isinstance(document_id, str):
            document_label = t(f"document.{document_id}", lang)
        missing_lines.append(str(document_label))

    breakdown = readiness.get("breakdown", [])
    if not isinstance(breakdown, list):
        raise ValueError("readiness breakdown must be a list")
    breakdown_lines: list[str] = []
    for item in breakdown:
        if not isinstance(item, Mapping):
            raise ValueError("each readiness breakdown item must be an object")
        item_name = item.get("item", "Unknown item")
        translated_item = t(f"document.{item_name}", lang)
        if translated_item == f"document.{item_name}":
            translated_item = str(item_name)
        breakdown_lines.append(
            t(
                "report.breakdown_item",
                lang,
            ).format(
                item=translated_item,
                earned=item.get("earned", 0),
                weight=item.get("weight", 0),
            )
        )

    next_step_lines: list[str] = []
    for step in next_steps:
        if not isinstance(step, Mapping):
            raise ValueError("each next step must be an object")
        next_step_lines.append(
            t("report.step", lang).format(
                priority=step.get("priority", "?"),
                action=step.get("action", "No action provided."),
                impact=step.get("impact_points", 0),
            )
        )

    return [
        ("report.title", [t("report.title", lang)]),
        (
            "report.section.application",
            [t("report.permit_type", lang).format(permit_type=permit_type)],
        ),
        (
            "report.section.status",
            [
                t(
                    f"report.status.{result.get('status', 'unknown')}",
                    lang,
                )
            ],
        ),
        ("report.section.disclaimer", [t("report.disclaimer", lang)]),
        ("report.section.criteria", criteria_lines or [t("value.none", lang)]),
        (
            "report.section.missing_documents",
            missing_lines or [t("value.none", lang)],
        ),
        (
            "report.section.readiness",
            [
                t("report.score", lang).format(
                    score=readiness.get("score", t("value.unavailable", lang))
                )
            ]
            + (breakdown_lines or [t("report.breakdown", lang)]),
        ),
        (
            "report.section.next_steps",
            next_step_lines or [t("value.none", lang)],
        ),
        (
            "report.section.reference",
            [
                t("report.fingerprint", lang).format(
                    fingerprint=result.get("fingerprint", t("value.unavailable", lang))
                ),
                t("report.rules_version", lang).format(version=rules_version),
                t("report.generated_on", lang).format(date=generated_on.isoformat()),
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
    report_date = generated_on if generated_on is not None else Date.today()
    if not isinstance(report_date, Date):
        raise TypeError("date must be a datetime.date instance")

    sections = _report_sections(permit_type, result, report_date, lang)
    if markdown:
        rendered = [f"# {sections[0][1][0]}"]
        for heading, lines in sections[1:]:
            rendered.extend(["", f"## {t(heading, lang)}"])
            rendered.extend(f"- {line}" for line in lines)
        return "\n".join(rendered)

    rendered = [sections[0][1][0]]
    for heading, lines in sections[1:]:
        rendered.extend(["", t(heading, lang).upper()])
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
