"""Session-held live comparison; rendering never invokes a provider."""

from hashlib import sha256
from html import escape

import streamlit as st

from core.config import ConfigurationError, load_settings
from core.llm import LLMServiceError
from core.memory import MemoryServiceError
from core.review_service import ReviewRun, ReviewService
from ui.components import html


@st.cache_resource(show_spinner=False, scope="session", on_release=lambda service: service.close())
def get_review_service() -> ReviewService:
    return ReviewService(load_settings())


def _text(value: str) -> None:
    html(f'<p>{escape(value)}</p>')


def _anchor(memory_id: str) -> str:
    return 'evidence-' + sha256(memory_id.encode()).hexdigest()[:20]


def _checks(checks: list[str]) -> None:
    html('<h4>Before proceeding</h4><ol>' + ''.join(f'<li>{escape(check)}</li>' for check in checks) + '</ol>')


def _baseline(run: ReviewRun) -> None:
    with st.container(key="fence-baseline"):
        st.subheader("Without memory")
        st.caption("Independent answer · Receives only your proposal")
        if run.result.baseline:
            _text(run.result.baseline.summary)
            _checks(run.result.baseline.checks_before_proceeding)
        else:
            st.error("The independent answer is unavailable. Review the error below and retry when ready.")


def verified_citations(run: ReviewRun) -> bool:
    result = run.result
    eligible = {item.memory.memory_id for item in result.evidence if item.eligible and not item.provenance_conflict}
    cited = [mid for decision in result.report.similar_decisions for mid in decision.memory_ids]
    return set(cited) == set(result.citation_ids) and set(cited) <= eligible


def _grounded(run: ReviewRun) -> None:
    result, report = run.result, run.result.report
    with st.container(key="fence-grounded"):
        st.subheader("With memory")
        st.caption(f"Archive search: {result.retrieval_status.replace('_', ' ')}")
        if not verified_citations(run):
            st.error("This report contains unsupported citations and cannot be displayed. Retry the check.")
            return
        if result.report_status != "grounded":
            (st.info if result.report_status == "no_relevant_history" else st.warning)(report.summary)
            st.caption("No grounded risk assessment is available. These are general checks.")
        else:
            html(f'<span class="fence-risk fence-risk-{report.risk_level}">{report.risk_level.capitalize()} risk</span>')
            _text(report.summary)
            st.caption(f"Evidence confidence: {report.confidence:.0%} · Heuristic, not a probability of success")
            if report.mixed_evidence:
                st.warning("Past decisions had conflicting outcomes. Compare their rollout conditions.")
            for decision in report.similar_decisions:
                html(f'<h4>{escape(decision.decision_title)}</h4>')
                st.caption(str(decision.decision_date or "Date unavailable"))
                _text(decision.similarity_reason)
                _text(decision.what_happened)
                _text(decision.why_it_matters)
                for mid in decision.memory_ids:
                    html(f'<a class="fence-citation" href="#{_anchor(mid)}">Cited evidence: {escape(mid)}</a>')
        _checks(report.checks_before_proceeding)


def memory_panel(run: ReviewRun) -> None:
    result = run.result
    st.subheader("Memory activity")
    docs = {item.document_id for item in run.documents or []}
    recalled_docs = {item.memory.document_id for item in result.evidence if item.memory.document_id}
    if run.documents is None:
        st.warning(run.snapshot_error or "Retained archive count unavailable.")
    else:
        st.caption(f"Recalled {len(recalled_docs & docs)} of {len(docs)} retained decision documents in the post-check snapshot.")
        if recalled_docs - docs:
            st.warning("Some recalled source documents were absent from the later archive snapshot; counts may have changed.")
        with st.expander("Retained decision documents"):
            if not run.documents:
                st.info("The configured bank contains no retained decisions. Run the seed command before the demo.")
            for document in run.documents:
                _text(f"{document.document_id} · {document.memory_unit_count} extracted facts")
    st.caption(f"{len(result.evidence)} distinct recalled facts · No new decisions retained by this check")
    if not result.evidence:
        st.info("No evidence returned." if result.retrieval_status == "complete" else "Retrieval did not return usable evidence; this does not confirm an empty archive.")
    cited = set(result.citation_ids) if verified_citations(run) else set()
    for item in result.evidence:
        memory = item.memory
        css = 'fence-evidence cited' if memory.memory_id in cited else 'fence-evidence'
        html(f'<div id="{_anchor(memory.memory_id)}" class="fence-anchor" tabindex="-1"></div>')
        with st.container(border=True):
            html(f'<div class="{css}"><strong>{escape(memory.title)}</strong>'
                 f'<span>{"Cited" if memory.memory_id in cited else "Recalled"} · {memory.date or "Date unavailable"}</span></div>')
            _text(f"Evidence ID: {memory.memory_id}")
            _text(f"Source: {memory.document_id or 'Unresolved'}")
            st.progress(item.ranking_signal, text=f"Relative ranking signal · {item.ranking_signal:.0%}")
            if not item.eligible:
                st.caption("Excluded from recommendation candidates: relevance or provenance requirements were not met.")
            _text(memory.evidence_text)
            if memory.source_text:
                with st.expander("Source excerpt" + (" · truncated" if memory.source_truncated else "")):
                    _text(memory.source_text)
    with st.expander("Request activity and search queries"):
        for query in result.recall_queries:
            _text(query)
        for event in run.activity:
            st.text(f"{event.operation} / {event.action} · {event.status} · attempt {event.attempt} · {event.elapsed_seconds:.2f}s")


def comparison(run: ReviewRun) -> None:
    html('<span class="fence-anchor" id="fence-report" tabindex="-1"></span>')
    st.subheader("Fence Report", anchor="fence-report-heading")
    _text("Reviewed proposal: " + run.result.proposal.original_input)
    if run.result.proposal.input_truncated:
        st.warning("Only the first 3,000 characters were reviewed in both answers.")
    st.caption(f"Pipeline completed in {run.result.elapsed_seconds:.2f}s · Results stay fixed until you explicitly run another check.")
    view = st.radio("Comparison view", ["Side by side", "With memory", "Without memory"], horizontal=True, key="comparison_view")
    if view == "Side by side":
        left, right = st.columns(2, gap="medium")
        with left:
            _baseline(run)
        with right:
            _grounded(run)
    elif view == "With memory":
        _grounded(run)
    else:
        _baseline(run)
    for issue in run.result.issues:
        st.warning(f"{issue.stage.capitalize()}: {issue.error.message} {issue.error.next_step}")
    memory_panel(run)


def review_workspace(request: str | None, status=None) -> None:
    previous = st.session_state.get("review_run")
    retry = False
    if (st.session_state.get("review_attempt") or request) and st.button("Retry last check", key="retry_review"):
        request = st.session_state["review_attempt"]
        retry = True
    if request is not None:
        if not retry and request == st.session_state.get("review_attempt") and previous and not previous.result.issues and not previous.snapshot_error and request == st.session_state.get("completed_request"):
            st.info("Showing the saved check. Use Retry last check to explicitly request a fresh answer.")
        else:
            _execute(request, status)
    if st.session_state.get("review_error"):
        st.error(st.session_state["review_error"])
    run = st.session_state.get("review_run")
    if status is not None:
        if st.session_state.get("review_error"):
            status.error(st.session_state["review_error"])
        elif run and st.session_state.get("proposal", "").strip() == st.session_state.get("completed_request"):
            if run.result.issues or run.result.report_status != "grounded":
                status.warning("Check finished with limitations. [View the report and errors](#fence-report).")
            else:
                status.success("Review complete. [View your comparison and citations](#fence-report).")
    if run:
        if st.session_state.get("proposal", "").strip() != st.session_state.get("completed_request", run.result.proposal.original_input):
            st.info("The editor differs from this report. Check the edited proposal to update both answers.")
        if st.session_state.get("review_error"):
            st.caption("Showing the previous completed check below.")
        comparison(run)


def _execute(request: str, status=None) -> None:
    st.session_state["review_attempt"] = request
    st.session_state.pop("review_error", None)
    loading = status if status is not None else st.empty()
    loading.markdown('<div class="fence-loading" role="status" aria-live="polite">Analyzing your proposal and searching the live decision archive…<div></div><div></div></div>', unsafe_allow_html=True)
    try:
        with st.spinner("Preparing independent and memory-backed answers…"):
            run = get_review_service().review(request)
        st.session_state["review_run"] = run
        st.session_state["completed_request"] = request
    except ConfigurationError as exc:
        st.session_state["review_error"] = str(exc)
    except (LLMServiceError, MemoryServiceError) as exc:
        st.session_state["review_error"] = f"{exc.error.message} {exc.error.next_step}"
    except Exception:
        # Provider exception bodies can contain credentials; never render or log them.
        st.session_state["review_error"] = "The check could not finish. Check the service configuration and retry. Your previous report is preserved."
    finally:
        loading.empty()
