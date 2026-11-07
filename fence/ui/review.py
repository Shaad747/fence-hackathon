"""Session-held live comparison; rendering never invokes a provider."""

from hashlib import sha256
from html import escape

import streamlit as st

from core.config import ConfigurationError, load_settings
from core.llm import LLMServiceError
from core.memory import MemoryServiceError
from core.review_service import ReviewRun, ReviewService
from ui.components import OUTCOMES, html


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
        st.caption("Independent answer based only on your proposal.")
        if run.result.baseline:
            html('<h4>Recommendation</h4>')
            _text(run.result.baseline.summary)
            html('<p class="fence-risk-line">Risk: No assessment in the independent answer.</p>')
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
        html('<h4>Recommendation</h4>')
        if result.report_status != "grounded":
            (st.info if result.report_status == "no_relevant_history" else st.warning)(report.summary)
            st.caption("No grounded risk assessment is available. These are general checks.")
        else:
            _text(report.summary)
            html(f'<p class="fence-risk-line"><span class="fence-risk fence-risk-{report.risk_level}">'
                 f'{report.risk_level.capitalize()} risk</span> '
                 f'<span>Evidence confidence: {report.confidence:.0%}. Heuristic, not a probability of success.</span></p>')
            if report.mixed_evidence:
                st.warning("Past decisions had conflicting outcomes. Compare their rollout conditions.")
        _checks(report.checks_before_proceeding)
        if result.report_status == "grounded" and report.similar_decisions:
            html('<h4>Historical evidence</h4>')
            for decision in report.similar_decisions:
                title = escape(decision.decision_title)
                links = []
                for index, mid in enumerate(decision.memory_ids, 1):
                    label = f"{title} ({index})" if len(decision.memory_ids) > 1 else title
                    links.append(f'<li><a class="fence-citation" href="#{_anchor(mid)}">Cited evidence: {label}</a></li>')
                html(f'''<div class="fence-precedent">
<ul>{''.join(links)}</ul>
<p class="fence-meta">{escape(str(decision.decision_date or "Date unavailable"))}</p>
<p>{escape(decision.what_happened)}</p>
<p>{escape(decision.similarity_reason)} {escape(decision.why_it_matters)}</p>
</div>''')


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
    st.caption(f"{len(result.evidence)} distinct recalled facts. This check retained no new decisions.")
    if not result.evidence:
        st.info("No evidence returned." if result.retrieval_status == "complete" else "Retrieval did not return usable evidence; this does not confirm an empty archive.")
    cited = set(result.citation_ids) if verified_citations(run) else set()
    if result.evidence:
        html('<h3 class="fence-case-heading">Evidence case files</h3>')
    for item in result.evidence:
        memory = item.memory
        anchor = _anchor(memory.memory_id)
        outcome = None if item.provenance_conflict else item.outcome
        outcome_label = "Recorded outcome: " + OUTCOMES[outcome] if outcome else "Recorded outcome unavailable"
        status = "Cited" if memory.memory_id in cited else "Recalled, not cited"
        with st.container(key=f"fence-case-{anchor}"):
            html(f'''<article id="{anchor}" class="fence-case" tabindex="-1">
<h4>{escape(memory.title)}</h4>
<p class="fence-case-meta"><span>{escape(str(memory.date or "Date unavailable"))}</span>
<span>{outcome_label}</span>
<span class="fence-case-status">{status}</span></p>
<p>{escape(item.what_happened)}</p>
</article>''')
            if not item.eligible:
                st.caption("Excluded from recommendation candidates: relevance or provenance requirements were not met.")
            with st.expander(f"Source details for {memory.title}"):
                _text(f"Evidence ID: {memory.memory_id}")
                _text(f"Source: {memory.document_id or 'Unresolved'}")
                st.progress(item.ranking_signal, text=f"Relative ranking signal: {item.ranking_signal:.0%}")
                html('<p><strong>Recalled fact</strong></p>')
                _text(memory.evidence_text)
                if memory.source_text:
                    html(f'<p><strong>{"Source excerpt (truncated)" if memory.source_truncated else "Source excerpt"}</strong></p>'
                         f'<p class="fence-source-excerpt">{escape(memory.source_text)}</p>')
    with st.expander("Request activity and search queries"):
        for query in result.recall_queries:
            _text(query)
        for event in run.activity:
            st.text(f"{event.operation} / {event.action} · {event.status} · attempt {event.attempt} · {event.elapsed_seconds:.2f}s")


def comparison(run: ReviewRun) -> None:
    html('<span class="fence-anchor" id="fence-report" tabindex="-1"></span>')
    with st.container(key="fence-report-summary"):
        st.subheader("Fence Report", anchor="fence-report-heading")
        html(f'<p class="fence-reviewed-proposal"><strong>Reviewed proposal</strong> {escape(run.result.proposal.original_input)}</p>')
        st.caption(f"Pipeline completed in {run.result.elapsed_seconds:.2f}s. Results stay fixed until you explicitly run another check.")
    if run.result.proposal.input_truncated:
        st.warning("Only the first 3,000 characters were reviewed in both answers.")
    with st.container(key="fence-readings"):
        view = st.radio("Comparison view", ["Side by side", "With memory", "Without memory"], horizontal=True, key="comparison_view")
        if view == "Side by side":
            left, right = st.columns([2, 3], gap="medium")
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


def review_workspace(request: str | None, status) -> None:
    previous = st.session_state.get("review_run")
    notice = status.empty()
    invalid_draft = request is not None and len(request) < 20
    if invalid_draft:
        request = None
    retry = False
    if (st.session_state.get("review_attempt") or request) and status.button("Retry last check", key="retry_review"):
        request = st.session_state["review_attempt"]
        retry = True
    reused = False
    if request is not None:
        if not retry and request == st.session_state.get("review_attempt") and previous and not previous.result.issues and not previous.snapshot_error and request == st.session_state.get("completed_request"):
            reused = True
        else:
            _execute(request, notice)
    run = st.session_state.get("review_run")
    if invalid_draft:
        notice.error("Describe the decision in at least 20 characters, or try the sample proposal.")
    elif st.session_state.get("review_error"):
        notice.error(st.session_state["review_error"])
    elif reused:
        notice.info("Showing the saved check. [View your comparison and citations](#fence-report).")
    elif run and st.session_state.get("proposal", "").strip() == st.session_state.get("completed_request"):
        if run.result.issues or run.result.report_status != "grounded":
            notice.warning("Check finished with limitations. [View the report and errors](#fence-report).")
        else:
            notice.success("Review complete. [View your comparison and citations](#fence-report).")
    if run:
        if st.session_state.get("proposal", "").strip() != st.session_state.get("completed_request", run.result.proposal.original_input):
            st.info("The editor differs from this report. Check the edited proposal to update both answers.")
        if st.session_state.get("review_error"):
            st.caption("Showing the previous completed check below.")
        comparison(run)


def _execute(request: str, notice) -> None:
    st.session_state["review_attempt"] = request
    st.session_state.pop("review_error", None)
    notice.markdown('<p class="fence-loading" role="status">Analyzing your proposal and searching the decision archive…</p>', unsafe_allow_html=True)
    try:
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
        notice.empty()
