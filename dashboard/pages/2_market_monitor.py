"""Page 2 — Market Monitor: today's snapshot + a fixed 30-day neighbour price
spread window. The underlying data only changes once a day, when the
ingestion pipeline runs (orchestration/run_pipeline.py's daily mode) — models
are retrained weekly, so repeated calls the same day return identical
numbers. The cache TTLs below just bound how far *this page* can lag behind
that last pipeline run, not how often new numbers actually appear, hence the
caption below rather than a "last updated" clock."""

import logging
from datetime import date, timedelta

import streamlit as st

from dashboard import api_client
from dashboard.charts import price_spread_bar_chart
from dashboard.config import get_settings

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Market Monitor", layout="wide")
st.title("Market Monitor")

_settings = get_settings()
st.caption(
    "Figures reflect the most recent daily pipeline run, not real-time data. "
    f"This page's own cache can lag that run by up to {_settings.ttl_forecast // 60} min "
    f"(forecast) / {_settings.ttl_historical // 3600}h (spreads)."
)

today = date.today()
SPREAD_WINDOW_DAYS = 30
window_start = today - timedelta(days=SPREAD_WINDOW_DAYS)

# --- today's snapshot: sourced from the price forecast, not /energy/summary.
# Actuals can't exist for hours that haven't happened yet, and the daily
# ingestion pipeline only backfills completed days — so "today" has to come
# from predict_price, the same endpoint Page 3 uses (target_date is
# constrained server-side to {today, tomorrow} for exactly this reason). ---
avg_price = None
try:
    price_forecast = api_client.predict_price(today)
    values = [p["value"] for p in price_forecast["prices"]]
    avg_price = sum(values) / len(values) if values else None
except api_client.ServiceUnavailableError:
    st.warning("Today's price forecast is temporarily unavailable.")
except api_client.APIConnectionError:
    st.error("Could not reach the API — today's price forecast unavailable.")
except api_client.APIClientError as e:
    st.error(f"Today's price forecast unavailable: {e}")
except Exception:
    logger.exception("Unexpected error fetching today's price forecast")
    st.error("Today's price forecast unavailable — unexpected error.")

st.metric("Today's avg. day-ahead price (forecast)",
         f"{avg_price:.1f} EUR/MWh" if avg_price is not None else "no data yet")

# --- neighbour price spreads, fixed rolling window (no user-facing picker —
# this page is a snapshot, not a historical-exploration surface; see Page 1
# for a free date range) ---
st.subheader(f"Neighbour price spreads (last {SPREAD_WINDOW_DAYS} days)")
try:
    spreads_df = api_client.get_price_spreads(window_start, today)
    st.plotly_chart(price_spread_bar_chart(spreads_df), width='stretch', theme=None)
except api_client.ServiceUnavailableError:
    st.warning("Neighbour price data is temporarily unavailable.")
except api_client.APIConnectionError:
    st.error("Could not reach the API — neighbour price spreads unavailable.")
except api_client.APIClientError as e:
    st.error(f"Neighbour price spreads unavailable: {e}")
except Exception:
    logger.exception("Unexpected error fetching neighbour price spreads")
    st.error("Neighbour price spreads unavailable — unexpected error.")
