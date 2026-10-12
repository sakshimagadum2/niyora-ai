import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

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
    app = AppTest.from_file(str(APP_PATH)).run()

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
        app = AppTest.from_file(str(APP_PATH)).run()
        _load_scenario_into_state(app, scenario)
        app.run()

        assert not app.exception
        assert any(status_text in element.value for element in app.markdown)


def test_app_runs_without_openai_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    app = AppTest.from_file(str(APP_PATH)).run()

    assert not app.exception
    assert any("Sample rules only" in element.value for element in app.info)
