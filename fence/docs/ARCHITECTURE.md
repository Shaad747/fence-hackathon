# Fence architecture

The [README diagram](../README.md#how-hindsight-memory-is-used) shows the live review and storage paths.

## Review and provenance

`app.py` assembles the Streamlit UI. `core/review_service.py` keeps provider clients on a session worker loop. The explicit check runs `core/pipeline.py`. Extraction identifies what is being proposed. The baseline receives the proposal without any retrieved context. Targeted Hindsight recall and confirmed relevance votes inform ranking for the grounded answer. Relevance and provenance gates exclude unsuitable evidence, including conflicting versions of one source. Citations must resolve to eligible recalled IDs. The report displays source text and flags partial retrieval or provider errors. The session keeps the rendered result and its citations stable across ordinary reruns.

`core/llm.py` bounds retries and uses the configured fallback for eligible failures. Structured responses pass local schema validation. `core/memory.py` wraps the Hindsight Python SDK and tracks request activity. The seeded JSON supplies the illustrative archive UI and the CLI retain input. Live review retrieves from the configured bank.

## Learning and reflection

The UI prepares outcome and vote events in the workspace-scoped SQLite queue. Stable IDs let retries converge on the same event. The queue confirms a write after Hindsight confirms its retain. An interrupted write remains available for explicit retry. Confirmed relevance votes can affect eligible evidence on a later review. The chart shows the share of confirmed votes marked Relevant.

Manual reflection uses confirmed local outcomes and verified historical sources. Automatic jobs are scheduled once per three qualifying confirmed outcomes, with durable snapshots and claims. Pending outcomes and votes leave that count unchanged. The reflection engine verifies the selected themes and source IDs before displaying observations and suggested lessons. A new browser session restores confirmed history and the latest successful reflection from SQLite. Drafts and comparison reports are session-scoped.

## Deployment boundary

Use a trusted single-workspace deployment with private durable storage for SQLite. The database holds proposal and outcome content. Cloud and Docker configuration are in the [README](../README.md). Large histories can hit provider deadlines. A reflection interrupted after its remote call may be recomputed on explicit retry. Pattern coverage is bounded by the supported theme catalog and verified source window.
