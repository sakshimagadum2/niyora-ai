import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app import evaluate_batch, run_hypothetical

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
DEMO_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_applicants.json"


def _load_scenario_into_state(app: AppTest, scenario_name: str) -> None:
    with DEMO_PATH.open(encoding="utf-8") as demo_file:
        scenarios = json.load(demo_file)["scenarios"]
    selected_permit = app.session_state["permit_type"]
    scenario = scenarios[selected_permit][scenario_name]
    rules = json.loads(
        (APP_PATH.parent / "data" / "permit_rules.json").read_text(encoding="utf-8")
    )["permits"][selected_permit]

    for field in rules["fields"]:
        key = f"applicant_{selected_permit}_{field['field']}"
        value = scenario.get(field["field"])
        if field["type"] == "boolean":
            value = "Not provided" if value is None else "Yes" if value else "No"
        elif field["type"] == "number":
            value = "" if value is None else str(value)
        else:
            value = "" if value is None else str(value)
        app.session_state[key] = value
    submitted = set(scenario.get("submitted_documents", []))
    for document in rules["required_documents"]:
        app.session_state[
            f"document_{selected_permit}_{document['id']}"
        ] = document["id"] in submitted


def test_app_first_run_has_no_exception_and_shows_banner() -> None:
    app = AppTest.from_file(str(APP_PATH)).run(timeout=15)

    assert not app.exception
    assert any("Sample rules only" in element.value for element in app.info)


def test_each_demo_scenario_loads_and_shows_expected_status(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    expected = {
        "ready": "Eligible under demo rules",
        "incomplete": "Needs more information",
        "rule_failure": "Not eligible under demo rules",
    }

    for scenario, status_text in expected.items():
        app = AppTest.from_file(str(APP_PATH)).run(timeout=15)
        _load_scenario_into_state(app, scenario)
        app.run(timeout=15)

        assert not app.exception
        assert any(status_text in element.value for element in app.markdown)
        visible_headers = {element.value for element in app.header}
        assert {
            "Applicant details",
            "Eligibility result",
            "Ask about this result",
            "Readiness report",
            "What-if",
            "Staff view",
        }.issubset(visible_headers)


def test_what_if_ui_helper_applies_failing_field_hypothetically() -> None:
    inputs = {
        "business_name": "Sample Shop",
        "owner_count": 0,
        "tax_clearance": True,
    }
    original_inputs = inputs.copy()

    result = run_hypothetical(
        "Trade Licence",
        inputs,
        [],
        {"field": "owner_count", "value": 1},
    )

    assert result["before"]["status"] == "not_eligible"
    assert result["after"]["status"] == "eligible"
    assert inputs == original_inputs


def test_batch_evaluation_is_deterministic_and_has_all_statuses() -> None:
    for permit_type in ("Trade Licence", "Building Permit"):
        first = evaluate_batch(permit_type)
        second = evaluate_batch(permit_type)

        assert first == second
        assert len(first["rows"]) == 12
        assert first["status_counts"]["eligible"] > 0
        assert first["status_counts"]["not_eligible"] > 0
        assert first["status_counts"]["needs_info"] > 0


def test_app_runs_without_openai_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    app = AppTest.from_file(str(APP_PATH)).run(timeout=15)

    assert not app.exception
    assert any("Sample rules only" in element.value for element in app.info)


def test_app_renders_in_hindi_without_exception() -> None:
    app = AppTest.from_file(str(APP_PATH))
    app.session_state["language"] = "hi"
    app.run(timeout=15)

    assert not app.exception
    assert any("केवल नमूना नियम" in element.value for element in app.info)
    assert any(element.value == "आवेदक का विवरण" for element in app.header)
