"""Readiness scoring and next-step guidance for the sample permit engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from core.eligibility import evaluate_eligibility, load_rules

DISCLAIMER = "Sample rules only, not official municipal requirements"
_DOCUMENT_POINTS = 50
_CRITERIA_POINTS = 50


def _allocate_points(weights: list[int], points: int) -> list[int]:
    if not weights:
        return []
    weight_total = sum(weights)
    if weight_total <= 0:
        return [0] * len(weights)

    floors = [(weight * points) // weight_total for weight in weights]
    remainders = [(weight * points) % weight_total for weight in weights]
    unallocated = points - sum(floors)
    order = sorted(range(len(weights)), key=lambda index: (-remainders[index], index))
    for index in order[:unallocated]:
        floors[index] += 1
    return floors


def compute_readiness(
    result: Mapping[str, Any],
    rules_for_permit: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate a deterministic 0–100 score from documents and criteria."""
    if not isinstance(result, Mapping) or not isinstance(rules_for_permit, Mapping):
        raise TypeError("result and rules_for_permit must be mappings")

    required_documents = rules_for_permit.get("required_documents")
    rules = rules_for_permit.get("rules")
    missing_documents = result.get("missing_documents")
    criteria = result.get("criteria")
    if not isinstance(required_documents, list) or not isinstance(rules, list):
        raise ValueError("permit rules must contain rules and required_documents lists")
    if not isinstance(missing_documents, list) or not isinstance(criteria, list):
        raise ValueError("result must contain missing_documents and criteria lists")

    missing_ids: set[str] = set()
    for document in missing_documents:
        if not isinstance(document, Mapping) or not isinstance(document.get("id"), str):
            raise ValueError("each missing document must have a string id")
        missing_ids.add(document["id"])

    document_ids: list[str] = []
    document_weights: list[int] = []
    for document in required_documents:
        if not isinstance(document, Mapping):
            raise ValueError("each required document must be an object")
        document_id = document.get("id")
        weight = document.get("weight")
        if not isinstance(document_id, str):
            raise ValueError("each required document must have a string id")
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise ValueError("document weights must be non-negative integers")
        document_ids.append(document_id)
        document_weights.append(weight)

    criterion_ids: list[str] = []
    criterion_statuses: list[str] = []
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            raise ValueError("each criterion must be an object")
        rule_id = criterion.get("rule_id")
        status = criterion.get("status")
        if not isinstance(rule_id, str):
            raise ValueError("each criterion must have a string rule_id")
        if status not in {"pass", "unknown", "fail"}:
            raise ValueError(f"invalid criterion status: {status!r}")
        criterion_ids.append(rule_id)
        criterion_statuses.append(status)

    document_points = _allocate_points(document_weights, _DOCUMENT_POINTS)
    criterion_points = _allocate_points(
        [1] * len(criterion_ids),
        _CRITERIA_POINTS,
    )
    breakdown: list[dict[str, Any]] = []
    for item, weight in zip(document_ids, document_points):
        breakdown.append(
            {
                "item": item,
                "weight": weight,
                "earned": 0 if item in missing_ids else weight,
            }
        )
    for item, status, weight in zip(criterion_ids, criterion_statuses, criterion_points):
        breakdown.append(
            {
                "item": item,
                "weight": weight,
                "earned": weight if status == "pass" else 0,
            }
        )

    score = sum(item["earned"] for item in breakdown)
    return {"score": max(0, min(100, score)), "breakdown": breakdown}


def build_next_steps(
    result: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Prioritize each missing document and unresolved criterion by score impact."""
    if not isinstance(result, Mapping) or not isinstance(readiness, Mapping):
        raise TypeError("result and readiness must be mappings")
    missing_documents = result.get("missing_documents")
    criteria = result.get("criteria")
    if not isinstance(missing_documents, list) or not isinstance(criteria, list):
        raise ValueError("result must contain missing_documents and criteria lists")

    impacts: dict[str, int] = {}
    breakdown = readiness.get("breakdown")
    if not isinstance(breakdown, list):
        raise ValueError("readiness must contain a breakdown list")
    for item in breakdown:
        if not isinstance(item, Mapping) or not isinstance(item.get("item"), str):
            raise ValueError("each breakdown item must have a string item")
        points = item.get("weight")
        if isinstance(points, bool) or not isinstance(points, int) or points < 0:
            raise ValueError("breakdown weights must be non-negative integers")
        impacts[item["item"]] = points

    actions: list[dict[str, Any]] = []
    for document in missing_documents:
        if not isinstance(document, Mapping):
            raise ValueError("each missing document must be an object")
        document_id = document.get("id")
        label = document.get("label")
        if not isinstance(document_id, str) or not isinstance(label, str):
            raise ValueError("missing documents must have string id and label fields")
        actions.append(
            {
                "impact_points": impacts.get(document_id, 0),
                "action": f"Provide the {label}.",
            }
        )

    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            raise ValueError("each criterion must be an object")
        status = criterion.get("status")
        if status not in {"unknown", "fail"}:
            continue
        rule_id = criterion.get("rule_id")
        if not isinstance(rule_id, str):
            raise ValueError("each criterion must have a string rule_id")
        if status == "fail":
            # The eligibility engine copies a failed rule's fail_message to reason.
            action = criterion.get("reason")
        else:
            action = criterion.get("reason")
        if not isinstance(action, str):
            raise ValueError(f"rule {rule_id!r} has no usable action message")
        actions.append(
            {
                "impact_points": impacts.get(rule_id, 0),
                "action": action,
            }
        )

    actions.sort(key=lambda action: action["impact_points"], reverse=True)
    return [
        {
            "priority": priority,
            "action": action["action"],
            "impact_points": action["impact_points"],
        }
        for priority, action in enumerate(actions, start=1)
    ]


def evaluate_full(
    permit_type: str,
    inputs: Mapping[str, Any],
    documents: Sequence[str],
) -> dict[str, Any]:
    """Return eligibility together with readiness and actionable guidance."""
    if not isinstance(inputs, Mapping):
        raise TypeError("inputs must be a mapping")
    if isinstance(documents, (str, bytes)) or not isinstance(documents, Sequence):
        raise TypeError("documents must be a sequence of document identifiers")
    if not all(isinstance(document, str) for document in documents):
        raise TypeError("documents must contain only string identifiers")

    applicant = deepcopy(dict(inputs))
    applicant["submitted_documents"] = list(documents)
    result = evaluate_eligibility(applicant, permit_type)
    rules_data = load_rules()
    permits = rules_data.get("permits")
    if not isinstance(permits, Mapping):
        raise ValueError("permit rules must define a permits mapping")
    rules_for_permit = permits.get(permit_type)
    if not isinstance(rules_for_permit, Mapping):
        raise ValueError(f"rules for {permit_type!r} must be an object")

    readiness = compute_readiness(result, rules_for_permit)
    next_steps = build_next_steps(result, readiness)
    result["readiness"] = readiness
    result["next_steps"] = next_steps
    result["disclaimer"] = DISCLAIMER
    return result


def what_if(
    permit_type: str,
    inputs: Mapping[str, Any],
    documents: Sequence[str],
    change: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare eligibility and readiness before and after a copied input change."""
    if not isinstance(inputs, Mapping):
        raise TypeError("inputs must be a mapping")
    if isinstance(documents, (str, bytes)) or not isinstance(documents, Sequence):
        raise TypeError("documents must be a sequence of document identifiers")
    if not all(isinstance(document, str) for document in documents):
        raise TypeError("documents must contain only string identifiers")
    if not isinstance(change, Mapping):
        raise TypeError("change must be a mapping")

    before_inputs = deepcopy(dict(inputs))
    after_inputs = deepcopy(dict(inputs))
    before_documents = list(documents)
    after_documents = list(documents)
    if "field" in change:
        if set(change) != {"field", "value"} or not isinstance(change["field"], str):
            raise ValueError("field changes must contain a string field and value")
        after_inputs[change["field"]] = deepcopy(change["value"])
    elif "document" in change:
        if (
            set(change) != {"document", "provided"}
            or not isinstance(change["document"], str)
            or not isinstance(change["provided"], bool)
        ):
            raise ValueError("document changes require a string id and boolean provided")
        document_id = change["document"]
        if change["provided"] and document_id not in after_documents:
            after_documents.append(document_id)
        elif not change["provided"]:
            after_documents = [item for item in after_documents if item != document_id]
    else:
        raise ValueError("change must describe a field or document")

    before = evaluate_full(permit_type, before_inputs, before_documents)
    after = evaluate_full(permit_type, after_inputs, after_documents)
    return {
        "before": before,
        "after": after,
        "delta_score": after["readiness"]["score"] - before["readiness"]["score"],
        "status_changed": before["status"] != after["status"],
    }
