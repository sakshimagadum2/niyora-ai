"""Streamlit interface for the synthetic Niyora AI permit checker."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st

from core.assistant import answer_question
from core.eligibility import load_rules
from core.i18n import t
from core.report import build_report_markdown, build_report_text
from core.scoring import evaluate_full, what_if

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


def run_hypothetical(
    permit_type: str,
    inputs: dict[str, Any],
    documents: list[str],
    change: dict[str, Any],
) -> dict[str, Any]:
    """UI helper: delegate hypothetical evaluation without editing live state."""
    return what_if(permit_type, inputs, documents, change)


def evaluate_batch(permit_type: str, lang: str = "en") -> dict[str, Any]:
    """Evaluate the selected synthetic batch and aggregate its most common blockers."""
    with DEMOS_PATH.open(encoding="utf-8") as demo_file:
        batch = json.load(demo_file).get("batch_applicants", {})
    applicants = batch.get(permit_type, [])
    rows: list[dict[str, Any]] = []
    status_counts = Counter(
        {"eligible": 0, "not_eligible": 0, "needs_info": 0}
    )
    blocker_counts: Counter[str] = Counter()

    for applicant in applicants:
        inputs = {
            key: value
            for key, value in applicant.items()
            if key not in {"label", "submitted_documents"}
        }
        documents = applicant.get("submitted_documents", [])
        result = evaluate_full(permit_type, inputs, documents)
        status_counts[result["status"]] += 1
        for criterion in result["criteria"]:
            if criterion["status"] in {"fail", "unknown"}:
                blocker_counts[criterion["label"]] += 1
        for document in result["missing_documents"]:
            blocker_counts[document["label"]] += 1
        top_blocker = (
            result["next_steps"][0]["action"]
            if result["next_steps"]
            else "None"
        )
        rows.append(
            {
                t("table.applicant", lang): applicant["label"],
                t("table.status", lang): t(
                    f"status.{result['status']}",
                    lang,
                ),
                t("table.readiness", lang): result["readiness"]["score"],
                t("table.top_blocker", lang): top_blocker,
            }
        )

    return {
        "rows": rows,
        "status_counts": dict(status_counts),
        "blocker_counts": dict(blocker_counts.most_common(8)),
    }


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
    lang = st.session_state.get("language", "en")
    scenario = _read_demos()[permit_type][scenario_name]
    submitted = set(scenario.get("submitted_documents", []))
    permit_rules = load_rules()["permits"][permit_type]

    for field in permit_rules["fields"]:
        widget_key = _field_widget_key(permit_type, field["field"])
        field_value = scenario.get(field["field"])
        if field["type"] == "boolean":
            field_value = (
                t("value.not_provided", lang)
                if field_value is None
                else t("value.yes", lang)
                if field_value is True
                else t("value.no", lang)
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


def _field_value(field: dict[str, Any], permit_type: str, lang: str) -> Any:
    key = _field_widget_key(permit_type, field["field"])
    label = t(f"field.{field['field']}", lang)
    if label == f"field.{field['field']}":
        label = field["label"]
    field_type = field["type"]

    if field_type == "text":
        value = st.text_input(label, key=key)
        return value.strip() or None
    if field_type == "boolean":
        options = [
            t(
                {
                    "Not provided": "value.not_provided",
                    "Yes": "value.yes",
                    "No": "value.no",
                }.get(option, option),
                lang,
            )
            for option in field.get("options", [])
        ]
        if not options:
            raise ValueError(f"{label} has no configured options")
        answer = st.selectbox(label, options, key=key)
        return {
            t("value.not_provided", lang): None,
            t("value.yes", lang): True,
            t("value.no", lang): False,
        }[answer]
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
            st.warning(t("validation.number", lang).format(label=label.lower()))
            return None
        minimum = field.get("min")
        maximum = field.get("max")
        if minimum is not None and value < minimum:
            st.warning(t("validation.minimum", lang).format(label=label, value=minimum))
        if maximum is not None and value > maximum:
            st.warning(t("validation.maximum", lang).format(label=label, value=maximum))
        return int(value) if value.is_integer() else value
    raise ValueError(f"Unsupported field type: {field_type}")


def _status_badge(status: str, lang: str = "en") -> None:
    messages = {
        "eligible": ("✅", t("status.eligible", lang)),
        "not_eligible": ("⛔", t("status.not_eligible", lang)),
        "needs_info": ("ℹ️", t("status.needs_info", lang)),
    }
    icon, label = messages.get(status, ("ℹ️", t("status.unavailable", lang)))
    st.markdown(f"### {icon} {label}")


def _show_results(
    permit_type: str,
    result: dict[str, Any],
    rules: dict[str, Any],
    lang: str = "en",
) -> None:
    _status_badge(result["status"], lang)
    st.subheader(t("criteria.heading", lang))
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
            translated_criterion_status = t(
                f"criterion.{criterion['status']}",
                lang,
            )
            st.caption(
                f"{translated_criterion_status} — "
                f"{criterion['reason']}"
            )
            with st.expander(t("rule.show", lang)):
                st.json(rules_by_id[criterion["rule_id"]])

    readiness = result["readiness"]
    st.subheader(t("readiness.heading", lang))
    st.progress(
        readiness["score"],
        text=t("readiness.score", lang).format(score=readiness["score"]),
    )
    for item in readiness["breakdown"]:
        st.write(f"**{item['item']}** — {item['earned']} / {item['weight']} points")

    st.subheader(t("next_steps.heading", lang))
    if result["next_steps"]:
        for step in result["next_steps"]:
            st.write(
                f"**{step['priority']}.** {step['action']} "
                f"_({t('next_steps.impact', lang).format(points=step['impact_points'])})_"
            )
    else:
        st.write(t("next_steps.none", lang))

    st.subheader(t("documents.heading", lang))
    if result["missing_documents"]:
        for document in result["missing_documents"]:
            document_label = t(f"document.{document['id']}", lang)
            if document_label == f"document.{document['id']}":
                document_label = document["label"]
            st.write(f"• {document_label}")
    else:
        st.write(t("documents.none", lang))
    st.caption(t("reference", lang).format(fingerprint=result["fingerprint"]))


def main() -> None:
    st.set_page_config(page_title="Niyora AI", page_icon="🏛️", layout="wide")
    lang = st.session_state.get("language", "en")
    st.title(t("app_title", lang))
    st.subheader(t("tagline", lang))
    st.info(t("banner", lang), icon="ℹ️")

    all_rules = load_rules()
    permits = all_rules["permits"]
    permit_names = list(permits)
    st.session_state.setdefault(PERMIT_KEY, permit_names[0])

    with st.sidebar:
        st.header(t("sidebar.heading", lang))
        st.selectbox(
            t("language", lang),
            ["en", "hi"],
            format_func=lambda code: t(f"language.{code}", lang),
            key="language",
        )
        selected_permit = st.selectbox(
            t("sidebar.permit_type", lang),
            permit_names,
            key=PERMIT_KEY,
            on_change=_on_permit_change,
        )
        st.caption(t("sidebar.try_demo", lang))
        st.button(
            t("button.ready", lang),
            on_click=_load_scenario,
            args=("ready",),
            use_container_width=True,
        )
        st.button(
            t("button.incomplete", lang),
            on_click=_load_scenario,
            args=("incomplete",),
            use_container_width=True,
        )
        st.button(
            t("button.rule_failure", lang),
            on_click=_load_scenario,
            args=("rule_failure",),
            use_container_width=True,
        )
        if st.session_state.get("loaded_scenario"):
            st.caption(
                t("sidebar.loaded", lang).format(
                    scenario=st.session_state["loaded_scenario"].replace("_", " ")
                )
            )

    selected_rules = permits[selected_permit]
    applicant_tab, result_tab, assistant_tab, report_tab, what_if_tab, staff_tab = st.tabs(
        [
            t("tab.applicant", lang),
            t("tab.result", lang),
            t("tab.assistant", lang),
            t("tab.report", lang),
            t("tab.what_if", lang),
            t("tab.staff", lang),
        ]
    )

    with applicant_tab:
        st.header(t("applicant.heading", lang))
        st.caption(t("applicant.help", lang))
        inputs: dict[str, Any] = {}
        for field in selected_rules.get("fields", []):
            inputs[field["field"]] = _field_value(field, selected_permit, lang)

        st.subheader(t("documents.required", lang))
        submitted_documents: list[str] = []
        for document in selected_rules["required_documents"]:
            key = _document_widget_key(selected_permit, document["id"])
            document_label = t(f"document.{document['id']}", lang)
            if document_label == f"document.{document['id']}":
                document_label = document["label"]
            if st.checkbox(document_label, key=key):
                submitted_documents.append(document["id"])

    try:
        result = evaluate_full(selected_permit, inputs, submitted_documents)
    except Exception:
        result = None
        st.error(t("evaluation.error", lang))

    with result_tab:
        st.header(t("result.heading", lang))
        if result is not None:
            _show_results(selected_permit, result, selected_rules, lang)

    with assistant_tab:
        st.header(t("assistant.heading", lang))
        if result is None:
            st.info(t("assistant.need_result", lang))
        else:
            prompts = [
                t("question.why_status", lang),
                t("question.missing", lang),
                t("question.first_step", lang),
                t("question.rules", lang),
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

            question = st.chat_input(t("chat.placeholder", lang))
            question = question or st.session_state.pop("pending_question", None)
            if question:
                st.session_state.setdefault(CHAT_KEY, []).append(
                    {"role": "user", "content": question}
                )
                try:
                    response = answer_question(question, result, selected_rules)
                    label = t(
                        "assistant.ai" if response["source"] == "llm" else "assistant.offline",
                        lang,
                    )
                except Exception:
                    response = {
                        "answer": t("assistant.error", lang),
                        "source": "fallback",
                    }
                    label = t("assistant.offline", lang)
                st.session_state[CHAT_KEY].append(
                    {
                        "role": "assistant",
                        "content": response["answer"],
                        "source": label,
                    }
                )
                st.rerun()

    with report_tab:
        st.header(t("report.heading", lang))
        if result is None:
            st.info(t("report.need_result", lang))
        else:
            try:
                markdown_report = build_report_markdown(selected_permit, result, lang)
                text_report = build_report_text(selected_permit, result, lang)
                st.download_button(
                    t("report.download_markdown", lang),
                    data=markdown_report,
                    file_name="niyora-readiness-report.md",
                    mime="text/markdown",
                )
                st.download_button(
                    t("report.download_text", lang),
                    data=text_report,
                    file_name="niyora-readiness-report.txt",
                    mime="text/plain",
                )
                with st.expander(t("report.preview", lang), expanded=True):
                    st.markdown(markdown_report)
            except Exception:
                st.error(t("report.error", lang))

    with what_if_tab:
        st.header(t("what_if.heading", lang))
        st.caption(t("what_if.caption", lang))
        field_mode = t("what_if.field_value", lang)
        document_mode = t("what_if.document", lang)
        change_kind = st.radio(
            t("what_if.change_kind", lang),
            [field_mode, document_mode],
            horizontal=True,
        )
        change: dict[str, Any] | None = None
        if change_kind == field_mode:
            field_options = selected_rules.get("fields", [])
            selected_field = st.selectbox(
                t("what_if.select_field", lang),
                field_options,
                format_func=lambda field: t(
                    f"field.{field['field']}",
                    lang,
                )
                if t(f"field.{field['field']}", lang) != f"field.{field['field']}"
                else field["label"],
                key=f"whatif_field_{selected_permit}",
            )
            if selected_field["type"] == "boolean":
                new_value_label = st.selectbox(
                    t("what_if.value", lang),
                    [
                        t("value.not_provided", lang),
                        t("value.yes", lang),
                        t("value.no", lang),
                    ],
                    key=f"whatif_value_{selected_permit}_{selected_field['field']}",
                )
                new_value = {
                    t("value.not_provided", lang): None,
                    t("value.yes", lang): True,
                    t("value.no", lang): False,
                }[new_value_label]
            elif selected_field["type"] == "select":
                options = selected_field.get("options", [])
                new_value = st.selectbox(
                    t("what_if.value", lang),
                    options,
                    key=f"whatif_value_{selected_permit}_{selected_field['field']}",
                )
            else:
                raw_value = st.text_input(
                    t("what_if.value", lang),
                    key=f"whatif_value_{selected_permit}_{selected_field['field']}",
                )
                if selected_field["type"] == "number":
                    try:
                        new_value = float(raw_value) if raw_value.strip() else None
                        if isinstance(new_value, float) and new_value.is_integer():
                            new_value = int(new_value)
                    except ValueError:
                        new_value = None
                        st.warning(t("what_if.number_error", lang))
                else:
                    new_value = raw_value.strip() or None
            change = {"field": selected_field["field"], "value": new_value}
        else:
            document = st.selectbox(
                t("what_if.select_document", lang),
                selected_rules["required_documents"],
                format_func=lambda item: t(f"document.{item['id']}", lang),
                key=f"whatif_document_{selected_permit}",
            )
            provided = st.checkbox(
                t("what_if.mark_provided", lang),
                key=f"whatif_provided_{selected_permit}_{document['id']}",
            )
            change = {"document": document["id"], "provided": provided}

        if st.button(t("what_if.run", lang), key=f"run_whatif_{selected_permit}"):
            try:
                st.session_state["what_if_result"] = run_hypothetical(
                    selected_permit,
                    inputs,
                    submitted_documents,
                    change or {},
                )
            except Exception:
                st.error(t("what_if.error", lang))

        hypothetical = st.session_state.get("what_if_result")
        if hypothetical:
            before, after = st.columns(2)
            with before:
                st.subheader(t("what_if.before", lang))
                _status_badge(hypothetical["before"]["status"], lang)
                st.metric(
                    t("readiness.heading", lang),
                    t("readiness.score", lang).format(
                        score=hypothetical["before"]["readiness"]["score"]
                    ),
                )
            with after:
                st.subheader(t("what_if.after", lang))
                _status_badge(hypothetical["after"]["status"], lang)
                delta = hypothetical["delta_score"]
                st.metric(
                    t("readiness.heading", lang),
                    t("readiness.score", lang).format(
                        score=hypothetical["after"]["readiness"]["score"]
                    ),
                    delta=t("what_if.delta", lang).format(points=delta),
                )
            st.write(
                t("what_if.status_changed", lang)
                if hypothetical["status_changed"]
                else t("what_if.status_unchanged", lang)
            )
            before_criteria = {
                criterion["rule_id"]: criterion
                for criterion in hypothetical["before"]["criteria"]
            }
            changed_criteria = [
                criterion
                for criterion in hypothetical["after"]["criteria"]
                if before_criteria.get(criterion["rule_id"], {}).get("status")
                != criterion["status"]
            ]
            st.subheader(t("what_if.criteria_changed", lang))
            if changed_criteria:
                for criterion in changed_criteria:
                    old_status = before_criteria[criterion["rule_id"]]["status"]
                    st.write(
                        f"{criterion['rule_id']}: {old_status} → {criterion['status']}"
                    )
            else:
                st.write(t("what_if.criteria_none", lang))

    with staff_tab:
        st.header(t("staff.heading", lang))
        st.caption(t("staff.caption", lang))
        try:
            batch_summary = evaluate_batch(selected_permit, lang)
            st.dataframe(batch_summary["rows"], hide_index=True, use_container_width=True)
            count_columns = st.columns(3)
            for column, status, label in zip(
                count_columns,
                ("eligible", "not_eligible", "needs_info"),
                ("staff.eligible", "staff.not_eligible", "staff.needs_info"),
            ):
                column.metric(
                    t(label, lang),
                    batch_summary["status_counts"].get(status, 0),
                )
            st.subheader(t("staff.blockers", lang))
            if batch_summary["blocker_counts"]:
                st.bar_chart(batch_summary["blocker_counts"])
            else:
                st.write(t("staff.none", lang))
        except Exception:
            st.error(t("staff.error", lang))


if __name__ == "__main__":
    main()
