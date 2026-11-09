from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from surveycto_module_library.config import (
    load_settings,
    normalize_server,
    save_selected_server,
)
from surveycto_module_library.credentials import (
    Credentials,
    load_credentials,
    save_credentials,
)
from surveycto_module_library.database import connect, initialize
from surveycto_module_library.exporting import export_workbook
from surveycto_module_library.pipeline import run_update
from surveycto_module_library.retrieval import SurveyCTOApiRetriever
from surveycto_module_library.search import SearchFilters, filter_options, search_questions

st.set_page_config(page_title="SurveyCTO Module Library", page_icon="🔎", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; max-width: 1500px;}
    [data-testid="stSidebar"] {background: #f6f7f5; border-right: 1px solid #dfe3df;}
    h1, h2, h3 {letter-spacing: 0 !important;}
    .source-meta {color:#5f6863; font-size:.86rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

settings = load_settings()
initialize(settings.database_path)


@st.cache_data(show_spinner=False, ttl=30)
def options():
    return filter_options(settings.database_path)


@st.cache_data(show_spinner=False, ttl=30)
def results(filters: SearchFilters):
    return search_questions(settings.database_path, filters)


st.title("SurveyCTO Module Library")
if settings.server_configured:
    st.caption(f"Reusable questions and modules from deployed forms on `{settings.server}`")
else:
    st.caption("Connect your SurveyCTO server to build a local module library")

setup_tab, library_tab, updates_tab, about_tab = st.tabs(
    ["Setup & update", "Library", "Update history", "About the data"]
)

with setup_tab:
    st.subheader("SurveyCTO connection")
    if settings.server_configured:
        st.success(f"Current server: {settings.server}.surveycto.com")
    else:
        st.info("Connect a SurveyCTO server before downloading its deployed form definitions.")

    saved_credentials = load_credentials(settings.server) if settings.server_configured else None
    with st.form("connection_form"):
        server_value = st.text_input(
            "Server name or URL",
            value=settings.server if settings.server_configured else "",
            placeholder="example or https://example.surveycto.com",
        )
        username = st.text_input(
            "Username",
            value=saved_credentials.username if saved_credentials else "",
        )
        password = st.text_input("Password", type="password")
        connect_submitted = st.form_submit_button("Verify and save connection", type="primary")

    if connect_submitted:
        try:
            server = normalize_server(server_value)
            if not username.strip() or not password:
                raise ValueError("Enter both your SurveyCTO username and password.")
            candidate = Credentials(username.strip(), password)
            with st.spinner(f"Checking access to {server}.surveycto.com..."):
                form_count = len(SurveyCTOApiRetriever(server, candidate).list_form_ids())
            save_selected_server(settings.storage_root, server)
            save_credentials(server, candidate.username, candidate.password)
        except Exception as exc:  # noqa: BLE001 - show connection errors without saving secrets
            st.error(f"The connection could not be verified: {exc}")
        else:
            st.success(f"Connection verified. {form_count:,} deployed forms are accessible.")
            st.rerun()

    current_credentials = load_credentials(settings.server) if settings.server_configured else None
    st.divider()
    st.subheader("Update the local library")
    if not settings.server_configured or current_credentials is None:
        st.warning("Verify and save a server connection before running an update.")
    elif st.button("Download new forms and update the library", type="primary"):
        progress = st.progress(0.0, text="Preparing update...")

        def show_progress(completed, total, downloaded, reused, failed, form_id):
            fraction = completed / total if total else 1.0
            progress.progress(
                fraction,
                text=(
                    f"{completed:,}/{total:,} forms · {downloaded:,} downloaded · "
                    f"{reused:,} reused · {failed:,} warnings · {form_id}"
                ),
            )

        try:
            summary = run_update(
                settings,
                current_credentials,
                progress_callback=show_progress,
            )
        except Exception as exc:  # noqa: BLE001 - fatal update failure is shown in the UI
            progress.empty()
            st.error(f"The update could not finish: {exc}")
        else:
            progress.progress(1.0, text="Update complete")
            options.clear()
            results.clear()
            if summary.failures:
                st.warning(
                    "The library was updated, with warnings for forms that SurveyCTO did not "
                    "return. Details are listed below and saved in the run metadata."
                )
            else:
                st.success("The library was updated successfully.")
            metrics = st.columns(6)
            metrics[0].metric("Found", summary.forms_found)
            metrics[1].metric("Downloaded", summary.forms_downloaded)
            metrics[2].metric("Reused", summary.forms_reused)
            metrics[3].metric("Parsed", summary.parsed_forms)
            metrics[4].metric("Unchanged", summary.unchanged_forms)
            metrics[5].metric("Warnings", len(summary.failures or []))
            st.caption(
                f"{summary.total_questions:,} questions · "
                f"{summary.inferred_modules:,} reusable modules · "
                f"{summary.duration_seconds:,.1f} seconds · Run `{summary.run_id}`"
            )
            if summary.failures:
                st.dataframe(summary.failures, hide_index=True, width="stretch")

with library_tab:
    available = options()
    with st.sidebar:
        st.header("Find modules")
        with st.form("library_filters"):
            query = st.text_input("Search", placeholder="e.g. mental health, school attendance")
            selected_topics = st.multiselect("Topic", available["topics"])
            selected_subtopics = st.multiselect("Subtopic", available["subtopics"])
            selected_forms = st.multiselect("Survey", available["forms"])
            selected_modules = st.multiselect("Module", available["modules"])
            selected_languages = st.multiselect("Language", available["languages"])
            selected_types = st.multiselect("Question type", available["question_types"])
            include_noise = st.toggle("Include administrative sections", value=False)
            display_limit = st.select_slider(
                "Questions shown", options=[50, 100, 200, 500], value=100
            )
            st.form_submit_button("Apply filters", type="primary", width="stretch")

    filters = SearchFilters(
        text=query,
        topics=selected_topics,
        subtopics=selected_subtopics,
        forms=selected_forms,
        modules=selected_modules,
        languages=selected_languages,
        question_types=selected_types,
        include_noise=include_noise,
    )
    frame = results(filters)
    if frame.empty:
        st.info(
            "No questions match these filters. If the library is empty, use the launcher and "
            "choose Update library from SurveyCTO."
        )
    else:
        metric1, metric2, metric3 = st.columns(3)
        metric1.metric("Questions", len(frame))
        metric2.metric("Surveys", frame["form_id"].nunique())
        metric3.metric("Modules", frame["module"].nunique())

        survey_summary = (
            frame.groupby(["form_id", "survey"], sort=False)
            .size()
            .reset_index(name="Matching questions")
        )
        survey_labels = {
            f"{survey} ({form_id}) — {count:,} questions": form_id
            for form_id, survey, count in survey_summary.itertuples(index=False, name=None)
        }
        selected_result_survey = st.selectbox(
            "Browse matching survey",
            ["All matching surveys (preview)", *survey_labels],
        )
        with st.expander(f"Matching surveys ({len(survey_summary):,})", expanded=False):
            st.dataframe(
                survey_summary.rename(columns={"survey": "Survey", "form_id": "Form ID"}),
                hide_index=True,
                width="stretch",
            )
        filter_signature = repr(filters)
        if st.session_state.get("export_filter_signature") != filter_signature:
            st.session_state.pop("export_payload", None)
            st.session_state["export_filter_signature"] = filter_signature
        if st.button("Export filtered results", type="primary"):
            with st.spinner("Preparing the Excel workbook..."):
                st.session_state["export_payload"] = export_workbook(frame)
        if payload := st.session_state.get("export_payload"):
            st.download_button(
                "Download Excel file",
                payload,
                file_name=(
                    f"surveycto_module_library_{datetime.now(timezone.utc):%Y%m%d_%H%M}.xlsx"
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        if selected_result_survey == "All matching surveys (preview)":
            display_source = frame
        else:
            display_source = frame[frame["form_id"] == survey_labels[selected_result_survey]]
        display_frame = display_source.head(display_limit)
        if len(display_frame) < len(frame):
            st.caption(
                f"Showing {len(display_frame):,} of {len(display_source):,} questions in this "
                f"view ({len(frame):,} matches overall). The export includes every match."
            )
        for (form_id, survey), survey_frame in display_frame.groupby(
            ["form_id", "survey"], sort=False
        ):
            with st.expander(f"{survey} · {len(survey_frame)} questions", expanded=False):
                st.markdown(
                    f'<div class="source-meta">Form ID: <code>{form_id}</code></div>',
                    unsafe_allow_html=True,
                )
                for module_name, module_frame in survey_frame.groupby("module", sort=False):
                    st.subheader(module_name)
                    topics = sorted({value for value in module_frame["topic"].dropna() if value})
                    if topics:
                        st.caption(" · ".join(topics))
                    for row in module_frame.itertuples():
                        label = row.question_text or row.field_name
                        with st.expander(label, expanded=False):
                            left, right = st.columns([2, 1])
                            with left:
                                if isinstance(row.labels, dict) and len(row.labels) > 1:
                                    for language, translated_label in row.labels.items():
                                        st.markdown(f"**{language}:** {translated_label}")
                                st.markdown(
                                    f"**Field:** `{row.field_name}` &nbsp; "
                                    f"**Type:** `{row.field_type}`"
                                )
                                if row.relevance:
                                    st.markdown(f"**Relevance:** `{row.relevance}`")
                                if row.constraint_text:
                                    st.markdown(f"**Constraint:** `{row.constraint_text}`")
                                if row.calculation:
                                    st.markdown(f"**Calculation:** `{row.calculation}`")
                                if row.choices:
                                    st.markdown("**Choices**")
                                    choice_rows = [
                                        {"Value": choice["value"], **choice["labels"]}
                                        for choice in row.choices
                                    ]
                                    st.dataframe(choice_rows, hide_index=True, width="stretch")
                            with right:
                                st.markdown(f"**Survey:** {row.survey}")
                                st.markdown(f"**Module:** {row.module}")
                                st.markdown(f"**Source row:** {row.excel_row}")
                                if row.topic:
                                    st.markdown(f"**Category:** {row.topic} / {row.subtopic}")
                                if row.dependencies:
                                    st.markdown(
                                        "**Dependencies:** "
                                        + ", ".join(
                                            f"{item['type']}: {item['target']}"
                                            for item in row.dependencies
                                        )
                                    )
                                st.link_button("Open source survey", row.source_url)

with updates_tab:
    with connect(settings.database_path) as connection:
        runs = connection.execute(
            "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 30"
        ).fetchall()
    if not runs:
        st.info("No update has run yet.")
    else:
        run_rows = [dict(row) for row in runs]
        st.dataframe(run_rows, hide_index=True, width="stretch")

with about_tab:
    st.markdown(
        """
        This library contains survey **definitions**, not respondent submissions. Question text,
        choices, SurveyCTO logic, source groups, and source locations come from retrieved definitions.

        Module boundaries and topic labels are inferred locally by deterministic Python rules. The
        original source is preserved separately, and inferred categories never overwrite it. Obvious
        administrative sections are hidden by default but can be restored with the sidebar toggle.
        """
    )
