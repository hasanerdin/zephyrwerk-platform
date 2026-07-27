"""Page 2 — Market Monitor: today's snapshot + a fixed 30-day neighbour price
spread window. Short-TTL page — data is cached (see dashboard.config ttls),
hence the refresh-cadence caption below rather than a "last updated" clock:
the underlying data can be stale by up to a cache TTL regardless of when the
page last rendered."""

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
    f"Price forecast refreshes every {_settings.ttl_forecast // 60} min · "
    f"neighbour price spreads refresh every {_settings.ttl_historical // 3600}h"
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
    st.plotly_chart(price_spread_bar_chart(spreads_df), use_container_width=True, theme=None)
except api_client.ServiceUnavailableError:
    st.warning("Neighbour price data is temporarily unavailable.")
except api_client.APIConnectionError:
    st.error("Could not reach the API — neighbour price spreads unavailable.")
except api_client.APIClientError as e:
    st.error(f"Neighbour price spreads unavailable: {e}")
except Exception:
    logger.exception("Unexpected error fetching neighbour price spreads")
    st.error("Neighbour price spreads unavailable — unexpected error.")
