"""Reusable shell components. Escape archive values before rendering HTML."""

import re
from html import escape

import streamlit as st

from core.schemas import Decision

LIVE_REVIEW_VERSION = 1

LOTUS_ID = "kp-2023-project-lotus"
SAMPLE_PROPOSAL = "Remove the free tier for small merchants and move them to a Rs 299/month plan next quarter."
OUTCOMES = {"success": "Success", "partial": "Partial", "failed": "Failed", "rolled_back": "Rolled back"}
OUTCOME_MARKDOWN = {"success": "green", "partial": "orange", "failed": "red", "rolled_back": "red"}
FILTERS = {"outcome": "All outcomes", "team": "All teams", "year": "All years", "tag": "All tags"}

_LOGO = """<svg aria-hidden="true" width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 23V8l2.5-3L10 8v15m0-11h8m-8 6h8m0 5V8l2.5-3L23 8v15"/></svg>"""


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def navigation() -> None:
    links = [("Check", "check"), ("Archive", "archive"), ("Learning", "learning"),
             ("Patterns", "patterns"), ("Problem", "problem"), ("How it works", "how-it-works")]
    html('<header class="fence-nav"><div class="fence-nav-inner">'
         f'<a class="fence-brand" href="#check" aria-label="Fence, go to proposal">{_LOGO}Fence<span>.</span></a>'
         '<nav aria-label="Main navigation">'
         + "".join(f'<a href="#{target}">{label}</a>' for label, target in links)
         + '</nav></div></header>')


def _use_sample() -> None:
    st.session_state["proposal"] = SAMPLE_PROPOSAL


def _lotus_metric(lotus: Decision) -> str:
    metric = re.search(r"\b\d+(?:\.\d+)?%", lotus.impact)
    return metric[0] if metric else ""


def _archive_preview(lotus: Decision) -> None:
    html(f'''<figure class="fence-preview" aria-label="Illustrative archive excerpt">
<figcaption><h2>{escape(lotus.title)}</h2><p class="fence-meta">Illustrative archive excerpt from Kaveri Pay, {lotus.date:%b %Y}</p></figcaption>
<p class="fence-preview-outcome">{escape(_lotus_metric(lotus))} <span>churn in six weeks</span></p>
<p class="fence-preview-reason">{escape(lotus.reasons[0])}</p>
<a href="#archive">Explore the archive</a>
</figure>''')


def hero(lotus: Decision | None):
    with st.container(key="fence-hero"):
        html('''<div class="fence-hero-copy"><span class="fence-anchor" id="check" tabindex="-1"></span>
<h1>Check a proposal</h1>
<p class="fence-intro">Compare independent advice with a review grounded in past decisions.</p></div>''')
        copy, preview = st.columns([2, 1], gap="medium") if lotus else (st.container(), None)
        with copy:
            with st.container(key="fence-proposal-panel"):
                proposal = st.text_area("What are you about to decide?", key="proposal", height=108,
                                        placeholder="Describe a launch, pricing change, vendor switch, or process change…")
                with st.container(horizontal=True, gap="small", key="fence-proposal-actions"):
                    submitted = st.button("Check this proposal", type="primary", key="check_proposal")
                    st.button("Use a sample proposal", on_click=_use_sample, key="sample_proposal")
                st.caption("Live review sends your proposal to Groq and searches the configured Hindsight archive only when you check.")
                status = st.container(key="fence-proposal-status")
        if lotus:
            with preview:
                _archive_preview(lotus)

    return proposal.strip() if submitted else None, status


def problem(lotus: Decision | None) -> None:
    with st.container(key="fence-problem"):
        copy, stat = st.columns([1.3, 1], gap="large", vertical_alignment="center")
        with copy:
            html('''<section aria-labelledby="why-decisions-repeat"><span class="fence-anchor" id="problem" tabindex="-1"></span>
<h2 class="fence-section-title" id="why-decisions-repeat">Why decisions repeat</h2>
<p class="fence-section-lede">The proposal is new. The risk may be familiar.</p>
<div class="fence-beats"><p><strong>The context scatters.</strong> A decision gets made. The reasoning stays in a thread or a handover note.</p>
<p><strong>The people move on.</strong> A new team inherits the change without the story behind it.</p>
<p><strong>The lesson gets paid for twice.</strong> Fence brings earlier outcomes into view before the next commitment.</p></div></section>''')
        if lotus:
            with stat:
                html(f'''<figure class="fence-stat"><span class="fence-meta">A decision worth remembering</span>
<strong>{escape(_lotus_metric(lotus))}</strong><p>{escape(lotus.impact)}</p>
<figcaption>{escape(lotus.title)}, Q{(lotus.date.month - 1) // 3 + 1} {lotus.date.year} · Fictional case study</figcaption></figure>''')


def decision_details(decision: Decision) -> str:
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in decision.reasons)
    tags = "".join(f'<li class="fence-chip">{escape(tag)}</li>' for tag in decision.tags)
    return f'''<div class="fence-decision-detail"><dl><dt>Recorded impact</dt><dd>{escape(decision.impact)}</dd>
<dt>What shaped the outcome</dt><dd><ul>{reasons}</ul></dd><dt>Proposal</dt><dd>{escape(decision.proposal)}</dd>
<dt>Owner and team</dt><dd>{escape(decision.owner)}, {escape(decision.team)}</dd></dl>
<ul class="fence-chips" aria-label="Tags">{tags}</ul></div>'''


def _reset_filters() -> None:
    for key in FILTERS:
        st.session_state[f"archive_{key}"] = None


@st.fragment
def archive_timeline(decisions: list[Decision]) -> None:
    options = {"outcome": list(OUTCOMES), "team": sorted({item.team for item in decisions}),
               "year": sorted({item.date.year for item in decisions}, reverse=True),
               "tag": sorted({tag for item in decisions for tag in item.tags})}
    filters = {}
    with st.container(key="fence-archive-filters"):
        for (key, placeholder), column in zip(FILTERS.items(), st.columns(4, gap="small")):
            filters[key] = column.selectbox(key.capitalize(), options[key], index=None, placeholder=placeholder,
                                            format_func=lambda value: OUTCOMES.get(value, str(value)),
                                            key=f"archive_{key}")
    visible = [item for item in decisions if
               (filters["outcome"] is None or item.outcome == filters["outcome"])
               and (filters["team"] is None or item.team == filters["team"])
               and (filters["year"] is None or item.date.year == filters["year"])
               and (filters["tag"] is None or filters["tag"] in item.tags)]
    html(f'<p class="fence-count" role="status">Showing {len(visible)} of {len(decisions)} illustrative decisions</p>')
    if any(value is not None for value in filters.values()):
        st.button("Clear archive filters", on_click=_reset_filters, key="reset_archive")
    if not visible:
        st.info("No decisions match those filters. Clear a filter to see more of the archive.")
        return
    with st.container(key="fence-timeline"):
        for item in sorted(visible, key=lambda item: (item.id != LOTUS_ID, -item.date.toordinal())):
            title = re.sub(r"([\\`*_\[\]<>])", r"\\\1", item.title)
            label = f"**{title}** {item.date:%b %d, %Y} / :{OUTCOME_MARKDOWN[item.outcome]}[{OUTCOMES[item.outcome]}]"
            with st.container(key=f"archive-{item.outcome}-{item.id}"):
                with st.expander(label):
                    html(decision_details(item))


def archive(decisions: list[Decision] | None) -> None:
    with st.container(key="fence-archive"):
        html('''<span class="fence-anchor" id="archive" tabindex="-1"></span><h2 class="fence-section-title">Decision archive</h2>
<p class="fence-section-lede">Explore the decisions that shaped Kaveri Pay.</p>
<p class="fence-meta">Illustrative archive. Kaveri Pay and its outcomes are fictional.</p>''')
        if decisions is None:
            st.error("The local decision archive could not be loaded. Check seed/seed_data.json and reload the page.")
        else:
            archive_timeline(decisions)


def how_it_works() -> None:
    html('''<section class="fence-how" aria-labelledby="how-it-works">
<h2 class="fence-section-title" id="how-it-works">How it works</h2>
<p class="fence-section-lede">A proposal becomes a chance to use what the team already knows.</p>
<ol class="fence-steps"><li><strong>Retain</strong><p>Record a decision, the context, and what happened.</p></li>
<li><strong>Recall</strong><p>Find comparable choices and verify the sources.</p></li>
<li><strong>Reflect</strong><p>Look across outcomes for lessons worth keeping.</p></li></ol>
<div class="fence-planned"><section><h3>Feedback and learning</h3><p><a href="#learning">Review confirmed votes and outcome activity.</a></p></section>
<section><h3>Reflection and patterns</h3><p><a href="#patterns">Explore grounded reflection and its sources.</a></p></section></div>
<footer class="fence-footer"><span>Fence · Hack with Bengaluru</span><a href="#check">Back to proposal ↑</a></footer></section>''')
