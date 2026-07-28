"""Page 3 — Forecast Viewer: today/tomorrow price + generation forecast, plus
model performance. Five independent API calls, each with its own try/except —
a 503 on one (e.g. wind generation) must not blank the rest of the page. This
is the page most likely to hit "model/forecast not ready" states."""

import logging
from datetime import date, timedelta

import streamlit as st

from dashboard import api_client
from dashboard.charts import forecast_band_chart

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Forecast Viewer", layout="wide")
st.title("Forecast Viewer")

horizon = st.radio("Forecast day", ["Today", "Tomorrow"], horizontal=True)
target_date = date.today() if horizon == "Today" else date.today() + timedelta(days=1)


def _render_api_error(context: str, e: Exception) -> None:
    if isinstance(e, api_client.ServiceUnavailableError):
        st.warning(f"{context}: temporarily unavailable — {e}")
    elif isinstance(e, api_client.InvalidRequestError):
        st.error(f"{context}: invalid request — {e}")
    elif isinstance(e, api_client.APIConnectionError):
        st.error(f"{context}: could not reach the API.")
    elif isinstance(e, api_client.APIClientError):
        st.error(f"{context}: {e}")
    else:
        logger.exception(f"{context}: unexpected error", exc_info=e)
        st.error(f"{context}: unexpected error.")


# --- price forecast (2 independent calls: model performance, then the forecast) ---
st.subheader("Day-ahead price forecast")

price_mae = None
try:
    price_mae = api_client.get_model_performance(api_client.ModelType.PRICE)["holdout"]["mae"]
except Exception as e:
    _render_api_error("Price model performance", e)

try:
    price_forecast = api_client.predict_price(target_date)
    hours = [p["hour"] for p in price_forecast["prices"]]
    values = [p["value"] for p in price_forecast["prices"]]
    st.plotly_chart(forecast_band_chart(hours, values, price_mae or 0.0, "EUR/MWh"),
                    width='stretch', theme=None)
    if price_mae is None:
        st.caption("Model performance unavailable — showing point forecast without an MAE band.")
except Exception as e:
    _render_api_error("Price forecast", e)

# --- generation forecast (3 independent calls: solar MAE, wind MAE, forecast) ---
st.subheader("Renewable generation forecast")

solar_mae = None
try:
    solar_mae = api_client.get_model_performance(api_client.ModelType.SOLAR)["holdout"]["mae"]
except Exception as e:
    _render_api_error("Solar model performance", e)

wind_mae = None
try:
    wind_mae = api_client.get_model_performance(api_client.ModelType.WIND)["holdout"]["mae"]
except Exception as e:
    _render_api_error("Wind model performance", e)

try:
    generation_forecast = api_client.predict_generation(target_date)
    solar = generation_forecast["solar_generations"]["generations"]
    wind = generation_forecast["wind_generations"]["generations"]

    gen_col1, gen_col2 = st.columns(2)
    with gen_col1:
        st.markdown("**Solar**")
        st.plotly_chart(
            forecast_band_chart([p["hour"] for p in solar], [p["value"] for p in solar],
                                solar_mae or 0.0, "MW"),
            width='stretch', theme=None,
        )
        if solar_mae is None:
            st.caption("Model performance unavailable — showing point forecast without an MAE band.")
    with gen_col2:
        st.markdown("**Wind**")
        st.plotly_chart(
            forecast_band_chart([p["hour"] for p in wind], [p["value"] for p in wind],
                                wind_mae or 0.0, "MW"),
            width='stretch', theme=None,
        )
        if wind_mae is None:
            st.caption("Model performance unavailable — showing point forecast without an MAE band.")
except Exception as e:
    _render_api_error("Generation forecast", e)
