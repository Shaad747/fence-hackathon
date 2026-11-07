"""Explicit relevance voting and measured event history, without reflection."""
import sqlite3

import plotly.graph_objects as go
import streamlit as st

from core.learning import FeedbackQueue, learning_points, vote_signals, unique_votes
from core.memory import MemoryServiceError
from ui.components import html
from ui.outcomes import get_queue
from ui.review import get_review_service


def save_vote(queue, event):
    if queue.confirmed(event):
        st.info('This vote is already confirmed; it will not be counted twice.')
        return
    try:
        with st.spinner('Saving relevance feedback…'):
            receipt = get_review_service().save_feedback(event)
            queue.confirm(event, receipt)
        st.success('Vote confirmed. The chart updates now; run a new check to apply feedback to its evidence ranking.')
    except MemoryServiceError as exc:
        st.error(f'{exc.error.message} {exc.error.next_step} The original vote is available for retry.')
    except Exception:
        st.error('Vote could not be confirmed. Retry the preserved submission below; it is excluded from local learning counts.')


def learning_section():
    html('<span class="fence-anchor" id="learning" tabindex="-1"></span>')
    st.subheader('Learning from feedback')
    st.caption('Relevant share measures user votes, not recommendation accuracy or business improvement. Opposite votes cancel; each immutable event counts once.')
    try:
        outcomes = get_queue()
        queue = FeedbackQueue(outcomes.path, outcomes.workspace)
        run = st.session_state.get('review_run')
        if run:
            eligible = [item for item in run.result.evidence if item.eligible and not item.provenance_conflict
                        and item.memory.memory_id in run.result.citation_ids]
            for item in eligible:
                st.text(item.memory.title + ' · ' + item.memory.memory_id)
                left, right = st.columns(2)
                for column, relevance, label in [(left, 'relevant', 'Relevant'), (right, 'not_relevant', 'Not relevant')]:
                    if column.button(label, key=f'vote-{item.memory.memory_id}-{relevance}'):
                        save_vote(queue, queue.prepare(run.result, item.memory.memory_id, relevance))
        for event, confirmed in queue.records():
            if not confirmed:
                st.warning(f'Unconfirmed vote: {event.relevance.replace("_", " ")} · {event.event_id}')
                if st.button('Retry vote', key='retry-vote-' + event.event_id):
                    save_vote(queue, event)

        # Explicit refresh only: no remote reads or writes on ordinary Streamlit reruns.
        if st.button('Refresh persisted feedback', key='refresh_feedback'):
            try:
                with st.spinner('Reading confirmed Hindsight feedback…'):
                    events = get_review_service().read_feedback()
                st.session_state['remote_feedback'] = (outcomes.workspace, events)
                st.session_state.pop('feedback_read_error', None)
            except Exception:
                st.session_state['feedback_read_error'] = 'Hindsight feedback is unavailable. Showing the last known confirmed events; this view may be stale.'
        if st.session_state.get('feedback_read_error'):
            st.warning(st.session_state['feedback_read_error'])
        cached = st.session_state.get('remote_feedback')
        remote = cached[1] if cached and cached[0] == outcomes.workspace else []
        confirmed = [event for event, saved in queue.records() if saved]
        events = unique_votes([*remote, *confirmed])
        points = learning_points(events)
        outcome_records = outcomes.records()
        votes, saved_outcomes, waiting = st.columns(3)
        votes.metric('Confirmed votes', len(events))
        saved_outcomes.metric('Confirmed outcome records', sum(saved for _, saved in outcome_records))
        waiting.metric('Unconfirmed submissions', sum(not saved for _, saved in outcome_records) + sum(not saved for _, saved in queue.records()))
        st.caption('Outcome records include Pending decisions; they are not successful business outcomes. Counts are unique acknowledged records, not network attempts. Feedback includes locally acknowledged votes and the last explicit Hindsight refresh; outcome counts cover this installation only.')
        if points:
            fig = go.Figure(go.Scatter(x=[p['votes'] for p in points], y=[p['relevant_share'] for p in points],
                                      mode='lines+markers', line_color='#7FD6C2', fill='tozeroy',
                                      hovertemplate='%{x} confirmed votes · %{y:.1f}% relevant<extra></extra>'))
            fig.update_layout(xaxis_title='Confirmed vote events (chronological)', yaxis_title='Relevant votes / all confirmed votes (%)',
                              yaxis_range=[0, 100], paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                              font=dict(color='#E8ECF8', family='Hanken Grotesk'), margin=dict(l=10,r=10,t=20,b=20))
            st.plotly_chart(fig, key='learning_chart', width='stretch')
        else:
            st.caption('No confirmed relevance votes yet. Review a proposal and vote on a cited lesson, or refresh persisted feedback.')
        for mid, signal in vote_signals(events).items():
            st.text(f'{mid}: vote signal {signal:+.2f}; eligible-evidence adjustment {0.1*signal:+.3f} (bounded to ±0.1).')
        if run:
            with st.expander('Ranking and memory activity for the displayed report'):
                st.caption('These are the adjustments actually used for this saved report. New votes apply on the next explicit check; citations and original evidence stay fixed.')
                for item in run.result.evidence:
                    st.text(f'{item.memory.memory_id}: applied feedback {item.feedback_adjustment:+.3f}; final ranking signal {item.ranking_signal:.3f}; eligible: {item.eligible}')
                st.text(f'{len(run.result.evidence)} distinct recalled facts; {len(run.documents) if run.documents is not None else "unknown"} retained decision documents in its snapshot.')
    except (OSError, sqlite3.Error, ValueError):
        st.error('Learning history is unavailable. Check the queue configuration; no learning metrics can be confirmed.')
