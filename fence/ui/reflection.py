"""Persisted manual and automatic reflection; claims prevent duplicate workers."""
import json
import sqlite3

import streamlit as st

from core.reflection import ReflectionJobs
from ui.components import html
from ui.outcomes import get_queue
from ui.review import get_review_service


def run_job(jobs, job_id, retry=False):
    claim = jobs.claim(job_id, retry)
    if claim is None:
        return
    token, outcomes = claim
    try:
        with st.spinner('Reflecting on confirmed outcomes and historical evidence…'):
            result = get_review_service().reflect(outcomes)
        if jobs.finish(job_id, token, result=result):
            st.success('Reflection completed. Supported findings are shown below.')
    except Exception:
        jobs.finish(job_id, token, error='Reflection could not be verified or completed. Check provider configuration and retry explicitly. Your outcomes and previous reflection are preserved.')
        st.error('Reflection failed. Outcomes remain saved; retry is available below.')


def reflection_section():
    html('<span class="fence-anchor" id="patterns" tabindex="-1"></span>')
    st.subheader('What does our history say?')
    st.caption('Reflection uses confirmed outcomes and verified historical sources. Pending decisions and relevance votes do not advance the three-outcome trigger.')
    try:
        queue = get_queue()
        jobs = ReflectionJobs(queue.path, queue.workspace)
        count = jobs.sync()
        st.caption(f'{count} qualifying outcome records · automatic milestones: 3, 6, 9, … · next milestone: {(count//3+1)*3}')
        manual = st.button('What does our history say?', key='manual_reflection')
        if manual:
            run_job(jobs, jobs.manual())
        else:
            pending = next((job for job in jobs.jobs() if job['status']=='pending' and job['job_id'].startswith('auto-')), None)
            if pending:
                run_job(jobs, pending['job_id'])
        for job in jobs.jobs():
            if job['status'] == 'failed':
                st.warning(f"{job['job_id']}: {job['error']}")
                if st.button('Retry reflection', key='retry-reflection-'+job['job_id']):
                    run_job(jobs, job['job_id'], retry=True)
            elif job['status'] == 'running':
                st.caption(f"{job['job_id']}: running. An interrupted worker becomes explicitly retryable after three minutes.")
            elif job['status'] == 'pending':
                st.caption(f"{job['job_id']}: queued; no duplicate request has been sent.")
                if job['job_id'].startswith('manual-') and st.button('Resume requested reflection', key='resume-'+job['job_id']):
                    run_job(jobs, job['job_id'])
        successful = [job for job in jobs.jobs() if job['status']=='succeeded']
        if not successful:
            st.caption('No completed reflection yet. You can request one without recording an outcome.')
            return
        latest = max(successful, key=lambda job: job['started'])
        result = json.loads(latest['result'])
        st.caption(f"Saved reflection: {latest['job_id']} · based on {result['source_count']} verified sources. Later failures do not replace this result.")
        if not result['patterns']:
            st.info('No recurring pattern is supported by the available evidence.')
        for pattern in result['patterns']:
            st.markdown('#### ' + pattern['theme'].replace('_',' ').capitalize())
            st.text('Observed: ' + pattern['observation'])
            st.text('Suggested lesson (not a proven causal conclusion): ' + pattern['lesson'])
            for source in pattern['sources']:
                with st.expander(f"{source['title']} · {source['date']}"):
                    st.text(source['kind'] + ' · Source ID: ' + source['id'])
                    st.text(source['text'])
        st.caption(result['limitation'])
    except (OSError, sqlite3.Error, ValueError):
        st.error('Reflection state is unavailable. Check the durable queue path; no outcomes have been changed.')
