"""Rule-based eligibility checks for synthetic municipal permit examples."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from numbers import Real
from pathlib import Path
from typing import Any


RuleEvaluator = Callable[[Any, Any], bool]
_RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "permit_rules.json"


def _minimum(actual: Any, expected: Any) -> bool:
    if (
        isinstance(actual, bool)
        or not isinstance(actual, Real)
        or isinstance(expected, bool)
        or not isinstance(expected, Real)
    ):
        raise TypeError("minimum rules require numeric values")
    return actual >= expected


def _required(actual: Any, _expected: Any) -> bool:
    return bool(actual)


def _equals(actual: Any, expected: Any) -> bool:
    return actual == expected


_RULE_EVALUATORS: dict[str, RuleEvaluator] = {
    "minimum": _minimum,
    "required": _required,
    "equals": _equals,
}


def load_rules() -> dict[str, Any]:
    """Load the sample permit rules from the project's JSON data file."""
    with _RULES_PATH.open(encoding="utf-8") as rules_file:
        rules = json.load(rules_file)
    if not isinstance(rules, dict):
        raise ValueError("permit rules must be a JSON object")
    return rules


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _validate_inputs(applicant: Any, permit_type: Any) -> None:
    if not isinstance(applicant, Mapping):
        raise TypeError("applicant must be a mapping")
    if not all(isinstance(field, str) for field in applicant):
        raise TypeError("applicant field names must be strings")
    if not isinstance(permit_type, str) or not permit_type.strip():
        raise ValueError("permit_type must be a non-empty string")
    try:
        json.dumps(applicant, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError("applicant inputs must be JSON-serializable") from error


def _validate_rule(rule: Any) -> None:
    if not isinstance(rule, Mapping):
        raise ValueError("each rule must be an object")
    required_fields = {
        "id",
        "type",
        "field",
        "value",
        "label",
        "fail_message",
        "unknown_message",
    }
    if not required_fields.issubset(rule):
        raise ValueError("rule is missing one or more required properties")
    if rule["type"] not in _RULE_EVALUATORS:
        raise ValueError(f"unsupported rule type: {rule['type']!r}")
    if not all(
        isinstance(rule[field], str)
        for field in ("id", "field", "label", "fail_message", "unknown_message")
    ):
        raise ValueError("rule identifiers, fields, labels, and messages must be strings")


def evaluate_eligibility(
    applicant: Mapping[str, Any],
    permit_type: str,
) -> dict[str, Any]:
    """Evaluate supplied applicant inputs against the selected synthetic rules.

    Missing criteria are reported as unknown and never as failures. Documents
    are reported independently and do not alter the eligibility status.
    """
    _validate_inputs(applicant, permit_type)
    rules_data = load_rules()
    permits = rules_data.get("permits")
    rules_version = rules_data.get("rules_version")
    if not isinstance(permits, Mapping) or not isinstance(rules_version, str):
        raise ValueError("permit rules must define permits and a rules_version")
    if permit_type not in permits:
        raise ValueError(f"unknown permit type: {permit_type}")

    permit_rules = permits[permit_type]
    if not isinstance(permit_rules, Mapping):
        raise ValueError(f"rules for {permit_type!r} must be an object")
    criteria_rules = permit_rules.get("rules")
    required_documents = permit_rules.get("required_documents")
    if not isinstance(criteria_rules, list) or not isinstance(required_documents, list):
        raise ValueError("permit rules must contain rules and required_documents lists")

    criteria: list[dict[str, str]] = []
    for rule in criteria_rules:
        _validate_rule(rule)
        field = rule["field"]
        value = applicant.get(field)
        if field not in applicant or _is_missing(value):
            status = "unknown"
            reason = rule["unknown_message"]
        elif _RULE_EVALUATORS[rule["type"]](value, rule["value"]):
            status = "pass"
            reason = f"Meets requirement: {rule['label']}."
        else:
            status = "fail"
            reason = rule["fail_message"]
        criteria.append(
            {
                "rule_id": rule["id"],
                "label": rule["label"],
                "status": status,
                "reason": reason,
            }
        )

    statuses = {item["status"] for item in criteria}
    if "unknown" in statuses:
        status = "needs_info"
    elif "fail" in statuses:
        status = "not_eligible"
    else:
        status = "eligible"

    submitted_documents = applicant.get("submitted_documents", [])
    if _is_missing(submitted_documents):
        submitted_documents = []
    if not isinstance(submitted_documents, list) or not all(
        isinstance(document, str) for document in submitted_documents
    ):
        raise TypeError("submitted_documents must be a list of document identifiers")

    missing_documents: list[dict[str, Any]] = []
    for document in required_documents:
        if not isinstance(document, Mapping) or not {
            "id",
            "label",
            "weight",
        }.issubset(document):
            raise ValueError("each required document must define id, label, and weight")
        if document["id"] not in submitted_documents:
            missing_documents.append(
                {
                    "id": document["id"],
                    "label": document["label"],
                    "weight": document["weight"],
                }
            )

    fingerprint_payload = {
        "inputs": dict(applicant),
        "permit_type": permit_type,
        "rules_version": rules_version,
    }
    fingerprint_json = json.dumps(fingerprint_payload, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_json.encode("utf-8")).hexdigest()

    return {
        "status": status,
        "criteria": criteria,
        "missing_documents": missing_documents,
        "fingerprint": fingerprint,
    }
