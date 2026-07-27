from datetime import date
from enum import StrEnum
from http import HTTPStatus
from typing import Any

import pandas as pd
import requests
import streamlit as st

from dashboard.config import get_settings


class ModelType(StrEnum):
    """Mirrors ml.training_utils.ModelType — kept in sync manually since the
    dashboard doesn't depend on the ml package."""
    PRICE = "price"
    WIND = "wind"
    SOLAR = "solar"


class APIClientError(Exception):
    """Base class for all api_client errors."""


class APIConnectionError(APIClientError):
    """The API was unreachable, or the request timed out."""


class ServiceUnavailableError(APIClientError):
    """HTTP 503 — data/model not ready yet (nothing wrong with the request)."""


class InvalidRequestError(APIClientError):
    """HTTP 400/422 — the request itself was malformed."""


def _error_detail(response: requests.Response, default: str) -> str:
    try:
        return response.json().get("detail", default)
    except requests.JSONDecodeError:
        return response.text or default


def _request(method: str, path: str, *,
            params: dict[str, Any] | None = None,
            json: dict[str, Any] | None = None) -> Any:
    settings = get_settings()
    url = f"{settings.ZEPHYRWERK_DASHBOARD_API_URL}{path}"

    try:
        response = requests.request(method, url, params=params, json=json,
                                    timeout=settings.request_timeout)
    except (requests.ConnectionError, requests.Timeout) as e:
        raise APIConnectionError(f"Could not reach the API at {url}: {e}") from e

    if response.status_code == HTTPStatus.SERVICE_UNAVAILABLE:
        raise ServiceUnavailableError(_error_detail(response, "Service temporarily unavailable"))
    if response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNPROCESSABLE_ENTITY):
        raise InvalidRequestError(_error_detail(response, "Invalid request"))

    response.raise_for_status()
    return response.json()


def _date_params(start_date: date | None, end_date: date | None,
                 **extra: str | None) -> dict[str, str]:
    params = {}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()
    for key, value in extra.items():
        if value is not None:
            params[key] = value
    return params


def _to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame.from_records(records)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data(ttl=get_settings().ttl_historical)
def get_generation(start_date: date | None = None, end_date: date | None = None,
                   source: str | None = None) -> pd.DataFrame:
    params = _date_params(start_date, end_date, source=source)
    data = _request("GET", "/energy/generation", params=params)
    return _to_dataframe(data["generated_energy"])


@st.cache_data(ttl=get_settings().ttl_historical)
def get_prices(start_date: date | None = None, end_date: date | None = None) -> pd.DataFrame:
    params = _date_params(start_date, end_date)
    data = _request("GET", "/energy/prices", params=params)
    return _to_dataframe(data["prices"])


@st.cache_data(ttl=get_settings().ttl_historical)
def get_price_spreads(start_date: date | None = None, end_date: date | None = None,
                      source: str | None = None) -> pd.DataFrame:
    params = _date_params(start_date, end_date, source=source)
    data = _request("GET", "/energy/price-spreads", params=params)
    return _to_dataframe(data["neighbour_prices"])


def _fetch_summary(target_date: date) -> dict[str, Any]:
    return _request("GET", "/energy/summary", params={"target_date": target_date.isoformat()})


@st.cache_data(ttl=get_settings().ttl_historical)
def get_summary_historical(target_date: date) -> dict[str, Any]:
    return _fetch_summary(target_date)


@st.cache_data(ttl=get_settings().ttl_today)
def get_today_summary(target_date: date) -> dict[str, Any]:
    return _fetch_summary(target_date)


@st.cache_data(ttl=get_settings().ttl_forecast)
def predict_price(target_date: date, hour: int | None = None) -> dict[str, Any]:
    return _request("POST", "/predict/price", json={"target_date": target_date.isoformat(), "hour": hour})


@st.cache_data(ttl=get_settings().ttl_forecast)
def predict_generation(target_date: date, hour: int | None = None) -> dict[str, Any]:
    return _request("POST", "/predict/generation", json={"target_date": target_date.isoformat(), "hour": hour})


@st.cache_data(ttl=get_settings().ttl_model_metrics)
def get_model_performance(model_type: ModelType) -> dict[str, Any]:
    return _request("GET", "/models/performance", params={"model_type": model_type.value})
