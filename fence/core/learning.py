"""Confirmed event aggregation. No inferred accuracy or synthetic learning metrics."""
from collections import defaultdict
from datetime import datetime, timezone

from core.outcomes import OutcomeQueue, digest, report_reference
from core.schemas import Feedback


class FeedbackQueue(OutcomeQueue):
    table = 'feedback'
    model = Feedback
    kind = 'feedback'

    def prepare(self, result, memory_id, relevance):
        evidence = {item.memory.memory_id: item for item in result.evidence if item.eligible and not item.provenance_conflict}
        if memory_id not in evidence or memory_id not in result.citation_ids:
            raise ValueError('Only verified cited evidence can receive a relevance vote.')
        proposal = 'proposal-' + digest(result.proposal.original_input)
        item = evidence[memory_id]
        # One direction per proposal/evidence pair, even if the report is regenerated.
        identity = dict(proposal=proposal, memory_id=memory_id, relevance=relevance)
        event = Feedback(proposal_reference=proposal, proposal_or_report_reference=report_reference(result),
            lesson=item.what_happened, memory_ids=[memory_id], relevance=relevance,
            event_id='vote-' + digest(identity), timestamp=datetime.now(timezone.utc))
        return self.enqueue(event)


def unique_votes(events):
    by_id = defaultdict(list)
    for event in events:
        by_id[event.event_id].append(event)
    # Inconsistent copies of an immutable event are excluded, independent of read order.
    return sorted((copies[0] for copies in by_id.values()
                   if all(copy == copies[0] for copy in copies)), key=lambda e: (e.timestamp, e.event_id))


def vote_signals(events):
    values = defaultdict(list)
    for event in unique_votes(events):
        for mid in set(event.memory_ids):
            values[mid].append(1 if event.relevance == 'relevant' else -1)
    return {mid: sum(votes)/len(votes) for mid, votes in sorted(values.items())}


def learning_points(events):
    relevant = 0
    points = []
    for count, event in enumerate(unique_votes(events), 1):
        relevant += event.relevance == 'relevant'
        points.append(dict(votes=count, relevant_share=100*relevant/count, timestamp=event.timestamp.isoformat()))
    return points
