"""Live proposal comparison and illustrative decision archive."""

import streamlit as st

from seed.seed import load_decisions
from ui.components import LOTUS_ID, archive, hero, how_it_works, html, navigation, problem
from ui import components
from ui.styles import STYLES
from ui.review import review_workspace
from ui.outcomes import outcome_section
from ui.learning import learning_section
from ui.reflection import reflection_section


@st.cache_data(show_spinner="Loading the local decision archive…")
def read_archive():
    return load_decisions()


def main() -> None:
    st.set_page_config(page_title="Fence · Decision review workspace", layout="wide", initial_sidebar_state="collapsed")
    if getattr(components, "LIVE_REVIEW_VERSION", None) != 1:
        st.error("Fence is serving an older UI module. Stop the Streamlit server with Ctrl+C, "
                 "restart it from fence/ using .venv/bin/python -m streamlit run app.py, "
                 "then refresh this page. Your draft has not been submitted.")
        st.stop()
    html(STYLES)
    navigation()
    try:
        decisions = read_archive()
    except (OSError, ValueError):
        decisions = None

    lotus = next((item for item in decisions or [] if item.id == LOTUS_ID), None)
    request, status = hero(lotus)
    review_workspace(request, status)
    outcome_section()
    learning_section()
    reflection_section()
    problem(lotus)
    archive(decisions)
    how_it_works()


if __name__ == "__main__":
    main()
