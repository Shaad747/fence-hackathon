"""Explicit outcome writes; the durable queue survives reruns and process restarts."""

import sqlite3

import streamlit as st
from pydantic import ValidationError

from core.config import ConfigurationError, load_settings
from core.memory import MemoryServiceError
from core.outcomes import OutcomeQueue, digest, report_reference
from ui.review import get_review_service


STATUSES = ['accepted', 'rejected', 'modified', 'pending', 'approved', 'shipped', 'failed']


def get_queue():
    settings = load_settings()
    return OutcomeQueue(settings.outcome_queue_path,
                        digest([settings.hindsight_base_url, settings.hindsight_bank_id]))


def save(queue, event):
    if queue.confirmed(event):
        st.success('This outcome was already saved. No duplicate was submitted.')
        return True
    try:
        with st.spinner('Saving this outcome to Hindsight…'):
            receipt = get_review_service().save_outcome(event)
            queue.confirm(event, receipt)
        st.success('Outcome saved to Hindsight.' if receipt.status == 'retained'
                   else 'Outcome already exists in Hindsight; confirmation recovered.')
        return True
    except MemoryServiceError as exc:
        st.error(f'{exc.error.message} {exc.error.next_step} The original submission is preserved below for retry.')
    except Exception:
        st.error('Save could not be confirmed. The original submission is preserved below. Retry it to check or finish saving.')


def outcome_section():
    st.subheader('Outcome feedback')
    if st.session_state.pop('outcome_saved_notice', False):
        st.success('Outcome confirmed in Hindsight.')
    st.caption('Record what you decided. Notes are saved as a new record; previous outcomes and archive decisions stay unchanged.')
    try:
        queue = get_queue()
        run = st.session_state.get('review_run')
        if run:
            ref = report_reference(run.result)
            st.text('For proposal: ' + run.result.proposal.original_input)
            with st.form('outcome-' + ref):
                status = st.selectbox('Decision outcome', STATUSES, format_func=str.capitalize, key='outcome-status-' + ref)
                notes = st.text_area('Reason or supporting notes', max_chars=2000, key='outcome-notes-' + ref)
                submitted = st.form_submit_button('Save outcome')
            if submitted:
                try:
                    event = queue.prepare(run.result, status, notes)
                except (ValidationError, ValueError):
                    st.error('Select a valid outcome and add a reason (1–2,000 characters). The report must have valid evidence references.')
                else:
                    save(queue, event)
        else:
            st.caption('Review a proposal to record its outcome. Previous submissions remain available below.')
        records = queue.records()
        if not records:
            st.caption('No outcome submissions in this workspace yet.')
        for event, confirmed in records:
            with st.expander(f'{event.status.capitalize()} · {event.timestamp:%Y-%m-%d %H:%M UTC} · {"Saved" if confirmed else "Unconfirmed — retry available"}'):
                st.text(event.proposal_text or event.proposal_reference)
                st.text(event.reason)
                st.caption(f'Event: {event.event_id}')
                st.caption(f'Proposal: {event.proposal_reference} · Report: {event.report_reference}')
                st.text('Retrieved evidence: ' + ', '.join(event.memory_ids))
                st.text('Cited evidence: ' + ', '.join(event.citation_ids))
                if not confirmed and st.button('Retry saving this outcome', key='retry-' + event.event_id):
                    if save(queue, event):
                        st.session_state['outcome_saved_notice'] = True
                        st.rerun()
    except (OSError, sqlite3.Error, ConfigurationError, ValidationError):
        st.error('Outcome history is unavailable. Check the configured queue path and its write permissions. No new outcome was saved.')
