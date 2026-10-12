"""Streamlit interface for the synthetic Niyora AI permit checker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from core.assistant import answer_question
from core.eligibility import load_rules
from core.report import build_report_markdown, build_report_text
from core.scoring import evaluate_full

BASE_DIR = Path(__file__).resolve().parent
RULES_PATH = BASE_DIR / "data" / "permit_rules.json"
DEMOS_PATH = BASE_DIR / "data" / "demo_applicants.json"
DISCLAIMER = (
    "Sample rules only, not official municipal requirements. "
    "Results are not approvals."
)
PERMIT_KEY = "permit_type"
CHAT_KEY = "assistant_chat"


def _field_widget_key(permit_type: str, field: str) -> str:
    return f"applicant_{permit_type}_{field}"


def _document_widget_key(permit_type: str, document_id: str) -> str:
    return f"document_{permit_type}_{document_id}"


def _read_demos() -> dict[str, Any]:
    with DEMOS_PATH.open(encoding="utf-8") as demo_file:
        return json.load(demo_file)["scenarios"]


def _clear_form_state() -> None:
    permits = load_rules()["permits"]
    for permit_type, permit_rules in permits.items():
        for field in permit_rules.get("fields", []):
            st.session_state.pop(
                _field_widget_key(permit_type, field["field"]),
                None,
            )
        for document in permit_rules.get("required_documents", []):
            st.session_state.pop(
                _document_widget_key(permit_type, document["id"]),
                None,
            )
    st.session_state.pop("loaded_scenario", None)


def _on_permit_change() -> None:
    _clear_form_state()


def _load_scenario(scenario_name: str) -> None:
    permit_type = st.session_state[PERMIT_KEY]
    scenario = _read_demos()[permit_type][scenario_name]
    submitted = set(scenario.get("submitted_documents", []))
    permit_rules = load_rules()["permits"][permit_type]

    for field in permit_rules["fields"]:
        widget_key = _field_widget_key(permit_type, field["field"])
        field_value = scenario.get(field["field"])
        if field["type"] == "boolean":
            field_value = (
                "Not provided"
                if field_value is None
                else "Yes"
                if field_value is True
                else "No"
            )
        elif field["type"] == "number":
            field_value = "" if field_value is None else str(field_value)
        else:
            field_value = "" if field_value is None else str(field_value)
        st.session_state[widget_key] = field_value
    for document in permit_rules["required_documents"]:
        st.session_state[_document_widget_key(permit_type, document["id"])] = (
            document["id"] in submitted
        )
    st.session_state["loaded_scenario"] = scenario_name


def _field_value(field: dict[str, Any], permit_type: str) -> Any:
    key = _field_widget_key(permit_type, field["field"])
    label = field["label"]
    field_type = field["type"]

    if field_type == "text":
        value = st.text_input(label, key=key)
        return value.strip() or None
    if field_type == "boolean":
        options = field.get("options", [])
        if not options:
            raise ValueError(f"{label} has no configured options")
        answer = st.selectbox(label, options, key=key)
        return {"Not provided": None, "Yes": True, "No": False}[answer]
    if field_type == "select":
        options = field.get("options", [])
        return st.selectbox(label, options, key=key) if options else None
    if field_type == "number":
        raw_value = st.text_input(
            label,
            key=key,
            help="Leave blank if this information is not available.",
        )
        if not raw_value.strip():
            return None
        try:
            value = float(raw_value)
        except ValueError:
            st.warning(f"Enter a valid number for {label.lower()}, or leave it blank.")
            return None
        minimum = field.get("min")
        maximum = field.get("max")
        if minimum is not None and value < minimum:
            st.warning(f"{label} must be at least {minimum}; this rule will need review.")
        if maximum is not None and value > maximum:
            st.warning(f"{label} must be no more than {maximum}; this rule will need review.")
        return int(value) if value.is_integer() else value
    raise ValueError(f"Unsupported field type: {field_type}")


def _status_badge(status: str) -> None:
    messages = {
        "eligible": ("✅", "Eligible under demo rules"),
        "not_eligible": ("⛔", "Not eligible under demo rules"),
        "needs_info": ("ℹ️", "Needs more information"),
    }
    icon, label = messages.get(status, ("ℹ️", "Status unavailable"))
    st.markdown(f"### {icon} {label}")


def _show_results(permit_type: str, result: dict[str, Any], rules: dict[str, Any]) -> None:
    _status_badge(result["status"])
    st.subheader("Criteria")
    rules_by_id = {rule["id"]: rule for rule in rules["rules"]}
    for criterion in result["criteria"]:
        status_icon = {
            "pass": "✅",
            "fail": "⛔",
            "unknown": "ℹ️",
        }.get(criterion["status"], "ℹ️")
        with st.container(border=True):
            st.markdown(
                f"**{status_icon} {criterion['rule_id']} · {criterion['label']}**"
            )
            st.caption(f"{criterion['status'].title()} — {criterion['reason']}")
            with st.expander("Show rule"):
                st.json(rules_by_id[criterion["rule_id"]])

    readiness = result["readiness"]
    st.subheader("Readiness")
    st.progress(readiness["score"], text=f"{readiness['score']} / 100")
    for item in readiness["breakdown"]:
        st.write(f"**{item['item']}** — {item['earned']} / {item['weight']} points")

    st.subheader("Prioritised next steps")
    if result["next_steps"]:
        for step in result["next_steps"]:
            st.write(
                f"**{step['priority']}.** {step['action']} "
                f"_(impact: {step['impact_points']} points)_"
            )
    else:
        st.write("No next steps are listed.")

    st.subheader("Documents")
    if result["missing_documents"]:
        for document in result["missing_documents"]:
            st.write(f"• {document['label']}")
    else:
        st.write("No missing documents.")
    st.caption(f"Reference: {result['fingerprint']}")


def main() -> None:
    st.set_page_config(page_title="Niyora AI", page_icon="🏛️", layout="wide")
    st.title("Niyora AI")
    st.subheader("Every Rule. One Clear Path.")
    st.info(DISCLAIMER, icon="ℹ️")

    all_rules = load_rules()
    permits = all_rules["permits"]
    permit_names = list(permits)
    st.session_state.setdefault(PERMIT_KEY, permit_names[0])

    with st.sidebar:
        st.header("Permit checker")
        selected_permit = st.selectbox(
            "Permit type",
            permit_names,
            key=PERMIT_KEY,
            on_change=_on_permit_change,
        )
        st.caption("Try a sample case")
        st.button(
            "Ready applicant",
            on_click=_load_scenario,
            args=("ready",),
            use_container_width=True,
        )
        st.button(
            "Incomplete case",
            on_click=_load_scenario,
            args=("incomplete",),
            use_container_width=True,
        )
        st.button(
            "Rule failure",
            on_click=_load_scenario,
            args=("rule_failure",),
            use_container_width=True,
        )
        if st.session_state.get("loaded_scenario"):
            st.caption(f"Loaded: {st.session_state['loaded_scenario'].replace('_', ' ')}")

    selected_rules = permits[selected_permit]
    applicant_tab, result_tab, assistant_tab, report_tab = st.tabs(
        ["Applicant", "Result", "Assistant", "Report"]
    )

    with applicant_tab:
        st.header("Applicant details")
        st.caption("Leave unknown information blank. Blank answers are not treated as failures.")
        inputs: dict[str, Any] = {}
        for field in selected_rules.get("fields", []):
            inputs[field["field"]] = _field_value(field, selected_permit)

        st.subheader("Required documents")
        submitted_documents: list[str] = []
        for document in selected_rules["required_documents"]:
            key = _document_widget_key(selected_permit, document["id"])
            if st.checkbox(document["label"], key=key):
                submitted_documents.append(document["id"])

    try:
        result = evaluate_full(selected_permit, inputs, submitted_documents)
    except Exception:
        result = None
        st.error("We could not evaluate this sample application. Please review the entries and try again.")

    with result_tab:
        st.header("Eligibility result")
        if result is not None:
            _show_results(selected_permit, result, selected_rules)

    with assistant_tab:
        st.header("Ask about this result")
        if result is None:
            st.info("A result is needed before the assistant can answer.")
        else:
            prompts = [
                "Why this status?",
                "What is missing?",
                "What should I do first?",
                "Which rules applied?",
            ]
            prompt_columns = st.columns(4)
            for column, prompt in zip(prompt_columns, prompts):
                if column.button(prompt, key=f"question_{prompt}"):
                    st.session_state["pending_question"] = prompt

            for message in st.session_state.get(CHAT_KEY, []):
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if message.get("source"):
                        st.caption(message["source"])

            question = st.chat_input("Ask a question about the result")
            question = question or st.session_state.pop("pending_question", None)
            if question:
                st.session_state.setdefault(CHAT_KEY, []).append(
                    {"role": "user", "content": question}
                )
                try:
                    response = answer_question(question, result, selected_rules)
                    label = "AI" if response["source"] == "llm" else "Offline mode"
                except Exception:
                    response = {
                        "answer": "The assistant could not answer just now. Please review the result above.",
                        "source": "fallback",
                    }
                    label = "Offline mode"
                st.session_state[CHAT_KEY].append(
                    {
                        "role": "assistant",
                        "content": response["answer"],
                        "source": label,
                    }
                )
                st.rerun()

    with report_tab:
        st.header("Readiness report")
        if result is None:
            st.info("A result is needed before a report can be created.")
        else:
            try:
                markdown_report = build_report_markdown(selected_permit, result)
                text_report = build_report_text(selected_permit, result)
                st.download_button(
                    "Download Markdown",
                    data=markdown_report,
                    file_name="niyora-readiness-report.md",
                    mime="text/markdown",
                )
                st.download_button(
                    "Download plain text",
                    data=text_report,
                    file_name="niyora-readiness-report.txt",
                    mime="text/plain",
                )
                with st.expander("Preview report", expanded=True):
                    st.markdown(markdown_report)
            except Exception:
                st.error("We could not create the report. Please try again.")


if __name__ == "__main__":
    main()
