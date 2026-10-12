import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from core.report import (
    DISCLAIMER,
    REPORT_TITLE,
    build_report_markdown,
    build_report_text,
)
from core.scoring import evaluate_full


@pytest.fixture
def demo_scenarios() -> dict[str, Any]:
    demo_path = Path(__file__).resolve().parents[1] / "data" / "demo_applicants.json"
    with demo_path.open(encoding="utf-8") as demo_file:
        return json.load(demo_file)["scenarios"]


def _evaluate_scenario(permit_type: str, scenario: dict[str, Any]) -> dict[str, Any]:
    inputs = dict(scenario)
    documents = inputs.pop("submitted_documents", [])
    return evaluate_full(permit_type, inputs, documents)


@pytest.fixture
def sample_result(demo_scenarios: dict[str, Any]) -> dict[str, Any]:
    return _evaluate_scenario(
        "Trade Licence",
        demo_scenarios["Trade Licence"]["incomplete"],
    )


@pytest.fixture
def ready_result(demo_scenarios: dict[str, Any]) -> dict[str, Any]:
    return _evaluate_scenario(
        "Trade Licence",
        demo_scenarios["Trade Licence"]["ready"],
    )


def test_report_contains_disclaimer_all_rule_ids_and_fingerprint(
    sample_result: dict[str, Any],
) -> None:
    report = build_report_markdown(
        "Trade Licence",
        sample_result,
        date=date(2026, 10, 12),
    )

    assert REPORT_TITLE in report
    assert DISCLAIMER in report
    for criterion in sample_result["criteria"]:
        assert criterion["rule_id"] in report
    assert sample_result["fingerprint"] in report
    assert "Rules version: sample-1.0" in report
    assert "Generated on: 2026-10-12" in report


def test_report_shows_none_for_empty_missing_documents_and_criteria(
    ready_result: dict[str, Any],
) -> None:
    report = build_report_text(
        "Trade Licence",
        ready_result,
        date=date(2026, 10, 12),
    )

    assert "MISSING DOCUMENTS\nNone" in report


def test_both_report_formats_are_deterministic_with_fixed_date(
    sample_result: dict[str, Any],
) -> None:
    fixed_date = date(2026, 1, 2)

    assert build_report_markdown("Trade Licence", sample_result, date=fixed_date) == (
        build_report_markdown("Trade Licence", sample_result, date=fixed_date)
    )
    assert build_report_text("Trade Licence", sample_result, date=fixed_date) == (
        build_report_text("Trade Licence", sample_result, date=fixed_date)
    )


def test_report_does_not_include_raw_applicant_personal_data(
    demo_scenarios: dict[str, Any],
) -> None:
    scenario = demo_scenarios["Trade Licence"]["ready"]
    result = _evaluate_scenario("Trade Licence", scenario)

    report = build_report_text("Trade Licence", result, date=date(2026, 1, 2))

    assert scenario["business_name"] not in report


@pytest.mark.parametrize("renderer", [build_report_markdown, build_report_text])
def test_needs_info_status_is_rendered_without_error(
    sample_result: dict[str, Any],
    renderer: Any,
) -> None:
    report = renderer("Trade Licence", sample_result, date=date(2026, 1, 2))

    assert "needs_info" in report


def test_report_renders_each_demo_scenario_without_raw_personal_fields(
    demo_scenarios: dict[str, Any],
) -> None:
    fixed_date = date(2026, 1, 2)

    for permit_type, scenarios in demo_scenarios.items():
        for scenario in scenarios.values():
            result = _evaluate_scenario(permit_type, scenario)

            markdown = build_report_markdown(
                permit_type,
                result,
                date=fixed_date,
            )
            plain_text = build_report_text(
                permit_type,
                result,
                date=fixed_date,
            )

            assert REPORT_TITLE in markdown
            assert DISCLAIMER in markdown
            assert result["fingerprint"] in markdown
            assert result["status"] in markdown
            assert REPORT_TITLE in plain_text
            assert DISCLAIMER in plain_text
            assert result["fingerprint"] in plain_text
            assert result["status"] in plain_text
            for criterion in result["criteria"]:
                assert criterion["rule_id"] in markdown
                assert criterion["rule_id"] in plain_text
            for private_value in (
                scenario.get("business_name"),
                scenario.get("site_address"),
            ):
                if private_value:
                    assert private_value not in markdown
                    assert private_value not in plain_text
