"""Page 1 — Historical Overview: free date-range exploration of generation mix
and day-ahead prices. Long-TTL, cache-friendly — this page can be read-heavy."""

from datetime import date, timedelta

import streamlit as st

from dashboard import api_client
from dashboard.charts import RENEWABLE_SOURCES, generation_mix_area_chart, price_timeseries_chart

st.set_page_config(page_title="Historical Overview", layout="wide")
st.title("Historical Overview")

# --- filters: one row, above the charts, scoping everything below ---
default_end = date.today()
default_start = default_end - timedelta(days=90)

filter_col1, filter_col2 = st.columns(2)
start_date = filter_col1.date_input("From", value=default_start, max_value=default_end)
end_date = filter_col2.date_input("To", value=default_end, max_value=default_end)

if start_date > end_date:
    st.error("Start date must be before end date.")
    st.stop()

# --- fetch: each call independent, so one failure doesn't blank the page ---
generation_df = None
try:
    generation_df = api_client.get_generation(start_date, end_date)
except api_client.APIConnectionError:
    st.error("Could not reach the API — generation data unavailable.")
except api_client.APIClientError as e:
    st.error(f"Generation data unavailable: {e}")

prices_df = None
try:
    prices_df = api_client.get_prices(start_date, end_date)
except api_client.APIConnectionError:
    st.error("Could not reach the API — price data unavailable.")
except api_client.APIClientError as e:
    st.error(f"Price data unavailable: {e}")

# --- KPIs for the selected range, computed client-side from the same
# DataFrames already fetched above — no extra API call. ---
kpi_col1, kpi_col2 = st.columns(2)

if prices_df is not None and not prices_df.empty:
    kpi_col1.metric("Avg. day-ahead price", f"{prices_df['price'].mean():.1f} EUR/MWh")
else:
    kpi_col1.metric("Avg. day-ahead price", "no data")

if generation_df is not None and not generation_df.empty:
    totals_by_source = generation_df.groupby("source")["value"].sum()
    total = totals_by_source.sum()
    renewable_total = totals_by_source[totals_by_source.index.isin(RENEWABLE_SOURCES)].sum()
    renewable_share = (renewable_total / total * 100) if total else None
    kpi_col2.metric("Renewable share", f"{renewable_share:.1f}%" if renewable_share is not None else "no data")
else:
    kpi_col2.metric("Renewable share", "no data")

# --- charts ---
st.subheader("Generation mix")
if generation_df is not None:
    st.plotly_chart(generation_mix_area_chart(generation_df), width='stretch', theme=None)

st.subheader("Day-ahead price")
if prices_df is not None:
    st.plotly_chart(price_timeseries_chart(prices_df), width='stretch', theme=None)
