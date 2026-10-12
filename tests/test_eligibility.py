import hashlib
import json

import pytest

from core.eligibility import evaluate_eligibility, load_rules


def test_ready_trade_licence_is_eligible() -> None:
    result = evaluate_eligibility(
        {
            "business_name": "Example Shop",
            "owner_count": 1,
            "tax_clearance": True,
            "submitted_documents": [
                "business_registration",
                "tax_clearance_certificate",
                "identity_document",
            ],
        },
        "Trade Licence",
    )

    assert result["status"] == "eligible"
    assert all(criterion["status"] == "pass" for criterion in result["criteria"])
    assert result["missing_documents"] == []


def test_failed_rule_makes_applicant_not_eligible() -> None:
    result = evaluate_eligibility(
        {
            "business_name": "Example Shop",
            "owner_count": 0,
            "tax_clearance": True,
        },
        "Trade Licence",
    )

    assert result["status"] == "not_eligible"
    assert next(c for c in result["criteria"] if c["rule_id"] == "TL-02")["status"] == "fail"


def test_missing_input_is_unknown_not_failure() -> None:
    result = evaluate_eligibility({"business_name": "Example Shop"}, "Trade Licence")

    assert result["status"] == "needs_info"
    assert [c["status"] for c in result["criteria"]] == ["pass", "unknown", "unknown"]


@pytest.mark.parametrize(
    ("applicant", "permit_type", "error"),
    [
        ([], "Trade Licence", TypeError),
        ({}, "", ValueError),
        ({}, "Unrecognized Permit", ValueError),
        ({"owner_count": object()}, "Trade Licence", ValueError),
        (
            {
                "business_name": "Example Shop",
                "owner_count": 1,
                "tax_clearance": True,
                "submitted_documents": "business_registration",
            },
            "Trade Licence",
            TypeError,
        ),
    ],
)
def test_invalid_inputs_raise_clear_errors(
    applicant: object,
    permit_type: str,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        evaluate_eligibility(applicant, permit_type)  # type: ignore[arg-type]


def test_missing_documents_are_reported_separately() -> None:
    result = evaluate_eligibility(
        {
            "business_name": "Example Shop",
            "owner_count": 1,
            "tax_clearance": True,
        },
        "Trade Licence",
    )

    assert result["status"] == "eligible"
    assert {document["id"] for document in result["missing_documents"]} == {
        "business_registration",
        "tax_clearance_certificate",
        "identity_document",
    }
    assert all(document["weight"] > 0 for document in result["missing_documents"])


def test_fingerprint_is_deterministic_and_matches_documented_payload() -> None:
    applicant = {
        "business_name": "Example Shop",
        "owner_count": 1,
        "tax_clearance": True,
    }
    first = evaluate_eligibility(applicant, "Trade Licence")
    second = evaluate_eligibility(
        {
            "tax_clearance": True,
            "owner_count": 1,
            "business_name": "Example Shop",
        },
        "Trade Licence",
    )
    expected_payload = {
        "inputs": applicant,
        "permit_type": "Trade Licence",
        "rules_version": load_rules()["rules_version"],
    }
    expected = hashlib.sha256(
        json.dumps(expected_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    assert first["fingerprint"] == second["fingerprint"] == expected
