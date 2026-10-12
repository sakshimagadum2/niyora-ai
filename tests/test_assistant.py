from copy import deepcopy
from typing import Any

import pytest

from core import assistant
from core.assistant import answer_question
from core.eligibility import load_rules
from core.scoring import evaluate_full


@pytest.fixture
def result() -> dict[str, Any]:
    return {
        "status": "needs_info",
        "criteria": [
            {
                "rule_id": "TL-01",
                "label": "Business name is provided",
                "status": "pass",
                "reason": "Meets requirement: Business name is provided.",
            },
            {
                "rule_id": "TL-02",
                "label": "At least one owner is listed",
                "status": "unknown",
                "reason": "Owner count is missing.",
            },
            {
                "rule_id": "TL-03",
                "label": "Tax clearance is confirmed",
                "status": "fail",
                "reason": "Confirm tax clearance for this sample check.",
            },
        ],
        "missing_documents": [
            {
                "id": "business_registration",
                "label": "Business registration record",
                "weight": 3,
            }
        ],
        "readiness": {
            "score": 50,
            "breakdown": [
                {"item": "business_registration", "weight": 25, "earned": 0},
                {"item": "TL-01", "weight": 17, "earned": 17},
                {"item": "TL-02", "weight": 17, "earned": 0},
                {"item": "TL-03", "weight": 16, "earned": 0},
            ],
        },
        "next_steps": [
            {
                "priority": 1,
                "action": "Provide the Business registration record.",
                "impact_points": 25,
            },
            {
                "priority": 2,
                "action": "Owner count is missing.",
                "impact_points": 17,
            },
            {
                "priority": 3,
                "action": "Confirm tax clearance for this sample check.",
                "impact_points": 16,
            },
        ],
        "fingerprint": "example-fingerprint",
    }


@pytest.fixture
def rules_for_permit() -> dict[str, Any]:
    return {
        "rules": [
            {"id": "TL-01"},
            {"id": "TL-02"},
            {"id": "TL-03"},
        ],
        "required_documents": [
            {"id": "business_registration", "weight": 3},
        ],
    }


@pytest.fixture(autouse=True)
def disable_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(assistant, "_load_environment", lambda: None)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Why is my status needs_info?", "recorded status is needs_info"),
        ("What is missing?", "Missing documents:"),
        ("What should I do first?", "Start with:"),
        ("What changes if I fix TL-02?", "could gain 17 points"),
        ("Which rules applied?", "TL-01: Business name is provided"),
    ],
)
def test_fallback_answers_supported_intents_with_real_rule_citations(
    result: dict[str, Any],
    rules_for_permit: dict[str, Any],
    question: str,
    expected: str,
) -> None:
    response = answer_question(question, result, rules_for_permit)

    assert response["source"] == "fallback"
    assert expected.lower() in response["answer"].lower()
    assert response["cited_rules"]
    assert set(response["cited_rules"]).issubset(
        {criterion["rule_id"] for criterion in result["criteria"]}
    )


def test_out_of_scope_fee_question_is_refused(
    result: dict[str, Any],
    rules_for_permit: dict[str, Any],
) -> None:
    response = answer_question("What is the fee?", result, rules_for_permit)

    assert response["source"] == "fallback"
    assert "cannot answer" in response["answer"]
    assert "contact the municipal office" in response["answer"]


def test_unknown_question_returns_a_helpful_default(
    result: dict[str, Any],
    rules_for_permit: dict[str, Any],
) -> None:
    response = answer_question("Can you explain the weather?", result, rules_for_permit)

    assert response["source"] == "fallback"
    assert "I can answer questions about" in response["answer"]


def test_llm_exception_returns_fallback(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any],
    rules_for_permit: dict[str, Any],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def raise_error(*_args: Any, **_kwargs: Any) -> str:
        raise TimeoutError("simulated LLM timeout")

    monkeypatch.setattr(assistant, "_generate_llm_answer", raise_error)
    response = answer_question("Why is my status needs_info?", result, rules_for_permit)

    assert response["source"] == "fallback"
    assert "recorded status is needs_info" in response["answer"]


def test_llm_answer_with_unsupported_guarantee_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any],
    rules_for_permit: dict[str, Any],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        assistant,
        "_generate_llm_answer",
        lambda *_args, **_kwargs: "Your permit is guaranteed.",
    )

    response = answer_question("Why is my status needs_info?", result, rules_for_permit)

    assert response["source"] == "fallback"
    assert "guaranteed" not in response["answer"].lower()


def test_llm_answer_with_unprovided_approval_claim_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any],
    rules_for_permit: dict[str, Any],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        assistant,
        "_generate_llm_answer",
        lambda *_args, **_kwargs: "Your application is approved.",
    )

    response = answer_question("Why is my status needs_info?", result, rules_for_permit)

    assert response["source"] == "fallback"
    assert "Your application is approved." not in response["answer"]


def test_answer_never_changes_the_result_status(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any],
    rules_for_permit: dict[str, Any],
) -> None:
    original = deepcopy(result)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        assistant,
        "_generate_llm_answer",
        lambda *_args, **_kwargs: "The recorded status is eligible.",
    )

    answer_question("Why is my status needs_info?", result, rules_for_permit)

    assert result["status"] == original["status"]
    assert result == original


def test_real_demo_scenarios_integrate_with_assistant() -> None:
    import json
    from pathlib import Path

    demo_path = Path(__file__).resolve().parents[1] / "data" / "demo_applicants.json"
    with demo_path.open(encoding="utf-8") as demo_file:
        scenarios = json.load(demo_file)["scenarios"]
    all_rules = load_rules()["permits"]

    for permit_type, permit_scenarios in scenarios.items():
        permit_rules = all_rules[permit_type]
        for scenario in permit_scenarios.values():
            inputs = dict(scenario)
            documents = inputs.pop("submitted_documents", [])
            result = evaluate_full(permit_type, inputs, documents)

            response = answer_question("Which rules applied?", result, permit_rules)

            assert response["source"] == "fallback"
            assert result["status"] in {"eligible", "needs_info", "not_eligible"}
            assert set(response["cited_rules"]) == {
                criterion["rule_id"] for criterion in result["criteria"]
            }
