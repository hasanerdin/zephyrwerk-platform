"""Zephyrwerk dashboard — landing page. Individual pages live under dashboard/pages/."""

import streamlit as st

st.set_page_config(page_title="Zephyrwerk Energy Platform", layout="wide")

st.title("Zephyrwerk Energy Platform")
st.markdown(
    "Renewable generation and day-ahead price monitoring for the German "
    "electricity market, backed by the Zephyrwerk FastAPI service.\n\n"
    "Use the sidebar to navigate:\n"
    "- **Historical Overview** — generation mix and prices over a custom date range\n"
    "- **Market Monitor** — today's snapshot and neighbour price spreads\n"
    "- **Forecast Viewer** — tomorrow's price/generation forecast and model performance"
)
