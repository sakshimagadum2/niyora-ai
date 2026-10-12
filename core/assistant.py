"""Grounded question answering for the synthetic permit-checking demo."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import Any

_OUT_OF_SCOPE = (
    re.compile(r"\b(fee|fees|cost|costs|price|pricing|charge|charges)\b", re.IGNORECASE),
    re.compile(r"\b(legal advice|lawyer|attorney|lawsuit|legal opinion)\b", re.IGNORECASE),
    re.compile(
        r"\b(processing time|how long|turnaround|days?|weeks?|timeline)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(guarantee|guaranteed)\b", re.IGNORECASE),
    re.compile(r"\b(will|can)\s+(my\s+)?(application\s+)?be\s+approved\b", re.IGNORECASE),
)
_CURRENCY_AMOUNT = re.compile(
    r"(?:[$€£¥]\s*\d[\d,]*(?:\.\d+)?|"
    r"\b(?:USD|CAD|AUD|EUR|GBP)\s*\d[\d,]*(?:\.\d+)?|"
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:USD|CAD|AUD|EUR|GBP)\b)",
    re.IGNORECASE,
)
_TIME_AMOUNT = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:-\s*)?(?:days?|weeks?)\b",
    re.IGNORECASE,
)
_RESTRICTED_CLAIMS = re.compile(r"\b(guaranteed|approved)\b", re.IGNORECASE)


def _load_environment() -> None:
    from dotenv import load_dotenv

    load_dotenv()


def _criterion_ids(result: Mapping[str, Any]) -> list[str]:
    criteria = result.get("criteria", [])
    if not isinstance(criteria, list):
        return []
    ids: list[str] = []
    for criterion in criteria:
        if isinstance(criterion, Mapping):
            rule_id = criterion.get("rule_id")
            if isinstance(rule_id, str) and rule_id not in ids:
                ids.append(rule_id)
    return ids


def _with_citations(answer: str, rule_ids: list[str]) -> str:
    if not rule_ids:
        return answer
    return f"{answer} (Rules: {', '.join(rule_ids)}.)"


def _cited_rule_ids(answer: str, result: Mapping[str, Any]) -> list[str]:
    return [
        rule_id
        for rule_id in _criterion_ids(result)
        if re.search(rf"\b{re.escape(rule_id)}\b", answer, re.IGNORECASE)
    ]


def _refusal() -> str:
    return (
        "This demo cannot answer that because the information is not in the "
        "supplied permit data. Please contact the municipal office."
    )


def _fallback_answer(
    question: str,
    result: Mapping[str, Any],
) -> str:
    lowered = question.lower()
    ids = _criterion_ids(result)
    criteria = result.get("criteria", [])
    if not isinstance(criteria, list):
        criteria = []
    docs = result.get("missing_documents", [])
    if not isinstance(docs, list):
        docs = []

    if any(pattern.search(question) for pattern in _OUT_OF_SCOPE):
        return _refusal()

    if (
        ("what changes" in lowered and "fix" in lowered)
        or ("if i fix" in lowered)
        or ("if we fix" in lowered)
    ):
        target = lowered.rsplit("fix", 1)[-1].strip(" ?.,:;")
        matching = [
            criterion
            for criterion in criteria
            if isinstance(criterion, Mapping)
            and any(
                target in str(criterion.get(field, "")).lower()
                for field in ("rule_id", "label", "reason")
            )
        ]
        if matching:
            criterion = matching[0]
            readiness = result.get("readiness", {})
            breakdown = readiness.get("breakdown", []) if isinstance(readiness, Mapping) else []
            impact = next(
                (
                    item.get("weight", 0)
                    for item in breakdown
                    if isinstance(item, Mapping)
                    and item.get("item") == criterion.get("rule_id")
                ),
                0,
            ) if isinstance(breakdown, list) else 0
            label = criterion.get("label", criterion.get("rule_id", "this criterion"))
            answer = (
                f"If {label} is resolved as a pass, readiness could gain "
                f"{impact} points. The overall status still depends on all "
                "criteria; this does not guarantee approval."
            )
            return _with_citations(answer, [criterion["rule_id"]] if isinstance(criterion.get("rule_id"), str) else ids)
        return _with_citations(
            "I could not match that change to a criterion in this result. "
            "Review the listed criteria and next steps.",
            ids,
        )

    if ("which rules" in lowered) or ("rules applied" in lowered):
        if not criteria:
            return "No evaluated criteria are included in the supplied result."
        descriptions = [
            f"{item.get('rule_id')}: {item.get('label')} ({item.get('status')})"
            for item in criteria
            if isinstance(item, Mapping)
        ]
        return _with_citations(
            "The evaluated rules and results are: " + "; ".join(descriptions) + ".",
            ids,
        )

    if (
        "what should i do first" in lowered
        or "what do i do first" in lowered
        or "first step" in lowered
        or "first thing" in lowered
        or ("first" in lowered and ("should" in lowered or "do" in lowered))
    ):
        steps = result.get("next_steps", [])
        if not isinstance(steps, list) or not steps:
            return _with_citations(
                "There are no next steps listed in the supplied result.",
                ids,
            )
        first_step = next(
            (
                step
                for step in steps
                if isinstance(step, Mapping) and step.get("priority") == 1
            ),
            steps[0],
        )
        if not isinstance(first_step, Mapping) or not isinstance(
            first_step.get("action"), str
        ):
            return _with_citations(
                "The supplied result does not contain a readable next step.",
                ids,
            )
        return _with_citations(
            f"Start with: {first_step['action']}",
            ids,
        )

    if any(
        phrase in lowered
        for phrase in ("what is missing", "what's missing", "what is still missing")
    ) or any(word in lowered for word in ("missing", "outstanding")):
        parts: list[str] = []
        if docs:
            labels = [
                document.get("label", document.get("id", "unnamed document"))
                for document in docs
                if isinstance(document, Mapping)
            ]
            if labels:
                parts.append("Missing documents: " + ", ".join(str(label) for label in labels) + ".")
        unknown = [
            item
            for item in criteria
            if isinstance(item, Mapping) and item.get("status") == "unknown"
        ]
        if unknown:
            parts.append(
                "Information still needed: "
                + "; ".join(
                    f"{item.get('label', item.get('rule_id'))}: {item.get('reason', 'not provided')}"
                    for item in unknown
                )
                + "."
            )
        if not parts:
            parts.append("The supplied result lists no missing documents or unknown criteria.")
        relevant_ids = [
            item["rule_id"]
            for item in unknown
            if isinstance(item.get("rule_id"), str)
        ] or ids
        return _with_citations(" ".join(parts), relevant_ids)

    if (
        ("why" in lowered and ("status" in lowered or "eligible" in lowered))
        or "why am i" in lowered
    ):
        status = result.get("status", "not provided")
        details = [
            f"{item.get('rule_id')} is {item.get('status')}: {item.get('reason')}"
            for item in criteria
            if isinstance(item, Mapping)
        ]
        explanation = (
            f"The recorded status is {status}."
            if not details
            else f"The recorded status is {status}. " + " ".join(details)
        )
        return _with_citations(explanation, ids)

    return _with_citations(
        "I can answer questions about the recorded status, evaluated rules, "
        "missing information or documents, next steps, and changes to evaluated "
        "criteria. Please ask about one of those items.",
        ids,
    )


def _generate_llm_answer(
    question: str,
    result: Mapping[str, Any],
    rules_for_permit: Mapping[str, Any],
    api_key: str,
) -> str:
    from openai import OpenAI

    system_prompt = (
        "Answer only from the supplied permit rules and computed result. Cite "
        "the supplied rule IDs when relevant. Do not invent or infer laws, "
        "fees, processing times, or other facts. Never promise or imply "
        "approval, and never change, reinterpret, or override the eligibility "
        "status in the computed result. If the data does not answer the "
        "question, say this demo cannot answer and suggest contacting the "
        "municipal office."
    )
    context = json.dumps(
        {"rules": rules_for_permit, "result": result},
        sort_keys=True,
    )
    client = OpenAI(api_key=api_key, timeout=10.0)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        timeout=10.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Permit data:\n{context}\n\nQuestion: {question}"},
        ],
    )
    content = response.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("LLM returned no text answer")
    return content


def _contains_unsupported_claim(
    answer: str,
    result: Mapping[str, Any],
    rules_for_permit: Mapping[str, Any],
) -> bool:
    supplied = {"result": result, "rules": rules_for_permit}
    supplied_data = json.dumps(supplied, sort_keys=True).lower()
    for pattern in (_CURRENCY_AMOUNT, _TIME_AMOUNT):
        for match in pattern.finditer(answer):
            if match.group(0).lower() not in supplied_data:
                return True
    for match in _RESTRICTED_CLAIMS.finditer(answer):
        claim_sentence = next(
            (
                sentence.group().strip()
                for sentence in re.finditer(r"[^.!?]*(?:[.!?]+|$)", answer)
                if sentence.start() <= match.start() < sentence.end()
            ),
            answer.strip(),
        )
        matching_source = any(
            claim_sentence.rstrip(".!?").lower()
            in source.strip().rstrip(".!?").lower()
            for source in _string_values(supplied)
        )
        if match.group(0).lower() not in supplied_data or not matching_source:
            return True

    status = result.get("status")
    if isinstance(status, str):
        expected_status = status.replace("_", " ").lower()
        mentioned_statuses = re.findall(
            r"\bnot[\s_-]+eligible\b|\bneeds[\s_-]+info\b|\beligible\b",
            answer,
            flags=re.IGNORECASE,
        )
        if any(
            mentioned.replace("_", " ").replace("-", " ").lower() != expected_status
            for mentioned in mentioned_statuses
        ):
            return True
    return False


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [
            string
            for nested in value.values()
            for string in _string_values(nested)
        ]
    if isinstance(value, list):
        return [string for nested in value for string in _string_values(nested)]
    return []


def answer_question(
    question: str,
    result: Mapping[str, Any],
    rules_for_permit: Mapping[str, Any],
) -> dict[str, Any]:
    """Answer a permit question using supplied data, with a deterministic fallback."""
    if not isinstance(question, str):
        raise TypeError("question must be a string")
    if not isinstance(result, Mapping) or not isinstance(rules_for_permit, Mapping):
        raise TypeError("result and rules_for_permit must be mappings")

    fallback = _fallback_answer(question, result)
    try:
        _load_environment()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {
                "answer": fallback,
                "source": "fallback",
                "cited_rules": _cited_rule_ids(fallback, result),
            }
        llm_answer = _generate_llm_answer(
            question,
            result,
            rules_for_permit,
            api_key,
        )
        if _contains_unsupported_claim(llm_answer, result, rules_for_permit):
            return {
                "answer": fallback,
                "source": "fallback",
                "cited_rules": _cited_rule_ids(fallback, result),
            }
        return {
            "answer": llm_answer,
            "source": "llm",
            "cited_rules": _cited_rule_ids(llm_answer, result),
        }
    except Exception:
        return {
            "answer": fallback,
            "source": "fallback",
            "cited_rules": _cited_rule_ids(fallback, result),
        }
