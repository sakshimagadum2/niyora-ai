from copy import deepcopy
from typing import Any

from core.eligibility import load_rules
from core.scoring import compute_readiness, evaluate_full, what_if


def _trade_rules() -> dict[str, Any]:
    return load_rules()["permits"]["Trade Licence"]


def _ready_applicant() -> tuple[dict[str, Any], list[str]]:
    return (
        {
            "business_name": "Example Shop",
            "owner_count": 2,
            "tax_clearance": True,
        },
        [
            "business_registration",
            "tax_clearance_certificate",
            "identity_document",
        ],
    )


def test_ready_applicant_receives_full_readiness_score() -> None:
    inputs, documents = _ready_applicant()
    result = evaluate_full("Trade Licence", inputs, documents)

    assert result["readiness"]["score"] == 100
    assert set(result) == {
        "status",
        "criteria",
        "missing_documents",
        "fingerprint",
        "readiness",
        "next_steps",
        "disclaimer",
    }


def test_missing_document_reduces_readiness_score() -> None:
    inputs, documents = _ready_applicant()
    documents.remove("business_registration")
    result = evaluate_full("Trade Licence", inputs, documents)

    assert result["readiness"]["score"] < 100


def test_next_steps_are_sorted_and_failed_action_uses_rule_message() -> None:
    result = evaluate_full(
        "Trade Licence",
        {
            "business_name": "Example Shop",
            "owner_count": 0,
            "tax_clearance": False,
        },
        [],
    )

    steps = result["next_steps"]
    assert [step["priority"] for step in steps] == list(range(1, len(steps) + 1))
    assert [step["impact_points"] for step in steps] == sorted(
        (step["impact_points"] for step in steps),
        reverse=True,
    )
    assert "List at least one business owner." in {
        step["action"] for step in steps
    }
    assert "Confirm tax clearance for this sample check." in {
        step["action"] for step in steps
    }


def test_what_if_does_not_mutate_original_inputs_or_documents() -> None:
    inputs = {
        "business_name": "Example Shop",
        "owner_count": 0,
        "tax_clearance": True,
        "nested": {"preserved": True},
    }
    documents = ["business_registration"]
    original_inputs = deepcopy(inputs)
    original_documents = documents.copy()

    what_if(
        "Trade Licence",
        inputs,
        documents,
        {"document": "identity_document", "provided": True},
    )

    assert inputs == original_inputs
    assert documents == original_documents


def test_what_if_field_change_flips_status() -> None:
    result = what_if(
        "Trade Licence",
        {
            "business_name": "Example Shop",
            "owner_count": 0,
            "tax_clearance": True,
        },
        [],
        {"field": "owner_count", "value": 1},
    )

    assert result["before"]["status"] == "not_eligible"
    assert result["after"]["status"] == "eligible"
    assert result["status_changed"] is True


def test_evaluation_is_deterministic() -> None:
    inputs, documents = _ready_applicant()

    first = evaluate_full("Trade Licence", inputs, documents)
    second = evaluate_full("Trade Licence", inputs, documents)

    assert first == second


def test_scores_are_always_clamped_to_zero_through_one_hundred() -> None:
    result = {
        "criteria": [
            {"rule_id": "TL-01", "status": "fail"},
            {"rule_id": "TL-02", "status": "unknown"},
            {"rule_id": "TL-03", "status": "fail"},
        ],
        "missing_documents": [
            {"id": document["id"], "label": document["label"]}
            for document in _trade_rules()["required_documents"]
        ],
    }

    readiness = compute_readiness(result, _trade_rules())

    assert readiness["score"] == 0
    assert 0 <= readiness["score"] <= 100
