"""Pure chart-building functions: DataFrame in, plotly.graph_objects.Figure out.

No API calls, no Streamlit calls in here — keeps this testable in isolation and
reusable across pages, mirroring the "one layer, one job" rule applied to
api_client.py for external HTTP calls.
"""

import pandas as pd
import plotly.graph_objects as go

# Reference palette (dataviz skill, references/palette.md) — light chart surface.
_SURFACE = "#fcfcfb"
_GRIDLINE = "#e1e0d9"
_AXIS = "#c3c2b7"
_TEXT_SECONDARY = "#52514e"
_TEXT_MUTED = "#898781"

_CATEGORICAL = [
    "#2a78d6",  # 1 blue
    "#1baf7a",  # 2 aqua
    "#eda100",  # 3 yellow
    "#008300",  # 4 green
    "#4a3aa7",  # 5 violet
    "#e34948",  # 6 red
    "#e87ba4",  # 7 magenta
    "#eb6834",  # 8 orange — reserved for "Other"
]

# Fixed identity mapping: a source always renders in the same hue wherever it's
# shown. German generation has ~11 source columns (ml.energy_sources) — well past
# the CVD-safe 8-hue ceiling, so the 7 most analytically distinct sources get their
# own slot and the rest fold into "Other" (choosing-a-form.md's series-count ladder).
_PRIMARY_SOURCES = [
    "solar_mw", "wind_onshore_mw", "wind_offshore_mw", "biomass_mw",
    "natural_gas_mw", "hard_coal_mw", "brown_coal_mw",
]
_OTHER = "other"
_SOURCE_COLORS = dict(zip(_PRIMARY_SOURCES, _CATEGORICAL)) | {_OTHER: _CATEGORICAL[7]}
_SOURCE_LABELS = {
    "solar_mw": "Solar",
    "wind_onshore_mw": "Wind (onshore)",
    "wind_offshore_mw": "Wind (offshore)",
    "biomass_mw": "Biomass",
    "natural_gas_mw": "Natural gas",
    "hard_coal_mw": "Hard coal",
    "brown_coal_mw": "Brown coal",
    _OTHER: "Other",
}


def _with_opacity(hex_color: str, opacity: float) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{opacity})"


def _apply_layout(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        plot_bgcolor=_SURFACE,
        paper_bgcolor=_SURFACE,
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=_TEXT_SECONDARY),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=40, r=20, t=40, b=40),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=_AXIS, linewidth=1)
    fig.update_yaxes(showgrid=True, gridcolor=_GRIDLINE, gridwidth=1, zeroline=False,
                     tickfont=dict(color=_TEXT_MUTED))
    return fig


def _empty_figure(message: str = "No data") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(annotations=[dict(text=message, showarrow=False,
                                        font=dict(color=_TEXT_MUTED))])
    return _apply_layout(fig)


# Beyond this many hourly points (~2 weeks), a multi-band stacked area over-plots:
# thin, similarly-hued top bands (Other/Hard coal/Brown coal) visually blend into
# what looks like one dominant mass even though the underlying values are small.
# Daily-mean downsampling keeps the shape readable at any selected range width.
_HOURLY_POINT_THRESHOLD = 24 * 14


def _fold_minor_sources(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["source"] = df["source"].where(df["source"].isin(_PRIMARY_SOURCES), _OTHER)
    return df.groupby(["timestamp", "source"], as_index=False)["value"].sum()


def _downsample_daily(df: pd.DataFrame, value_col: str, group_cols: list[str]) -> tuple[pd.DataFrame, bool]:
    if df["timestamp"].nunique() <= _HOURLY_POINT_THRESHOLD:
        return df, False
    df = df.copy()
    df["timestamp"] = df["timestamp"].dt.floor("D")
    return df.groupby([*group_cols, "timestamp"], as_index=False)[value_col].mean(), True


def generation_mix_area_chart(df: pd.DataFrame) -> go.Figure:
    """Stacked area of generation by source over time.

    `df` needs timestamp/source/value columns, e.g. from api_client.get_generation.
    Downsamples to daily means for wide ranges — see _HOURLY_POINT_THRESHOLD.
    """
    if df.empty:
        return _empty_figure()

    folded = _fold_minor_sources(df)
    folded, downsampled = _downsample_daily(folded, "value", ["source"])
    fig = go.Figure()

    for source in [*_PRIMARY_SOURCES, _OTHER]:
        series = folded[folded["source"] == source]
        if series.empty:
            continue
        color = _SOURCE_COLORS[source]
        fig.add_trace(go.Scatter(
            x=series["timestamp"], y=series["value"],
            name=_SOURCE_LABELS[source],
            mode="lines",
            line=dict(width=2, color=color),
            stackgroup="generation",
            fillcolor=_with_opacity(color, 0.10),
        ))

    fig.update_layout(yaxis_title="MW, daily average" if downsampled else "MW")
    return _apply_layout(fig)


def price_timeseries_chart(df: pd.DataFrame) -> go.Figure:
    """Day-ahead price line chart.

    `df` needs timestamp/price columns, e.g. from api_client.get_prices. Plain
    line (no area fill) since day-ahead prices go negative and a fill-to-zero
    would visually invert at each crossing.
    """
    if df.empty:
        return _empty_figure()

    df, downsampled = _downsample_daily(df, "price", [])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["price"],
        mode="lines",
        line=dict(width=2, color=_CATEGORICAL[0]),
        showlegend=False,
    ))

    fig.update_layout(yaxis_title="EUR/MWh, daily average" if downsampled else "EUR/MWh")
    return _apply_layout(fig)


def price_spread_bar_chart(df: pd.DataFrame) -> go.Figure:
    """Horizontal diverging bar of mean DE/LU price spread per neighbour over
    the given window. `df` needs source/spread columns, e.g. from
    api_client.get_price_spreads. Sign convention confirmed against the API
    (spread = DE price - neighbour price): positive means DE is more
    expensive than the neighbour that hour; negative means DE is cheaper.
    """
    if df.empty:
        return _empty_figure()

    means = df.groupby("source")["spread"].mean().dropna().sort_values()
    if means.empty:
        return _empty_figure()

    # diverging pair (palette.md): red = DE pricier, blue = DE cheaper
    colors = [_CATEGORICAL[5] if v >= 0 else _CATEGORICAL[0] for v in means]
    labels = [s.replace("_", " ").title() for s in means.index]

    fig = go.Figure(go.Bar(
        x=means.values, y=labels, orientation="h",
        marker=dict(color=colors),
        showlegend=False,
    ))
    fig.add_vline(x=0, line=dict(color=_AXIS, width=1))
    fig.update_layout(xaxis_title="EUR/MWh, DE minus neighbour (positive = DE pricier)")
    return _apply_layout(fig)


def forecast_band_chart(hours: list[int], values: list[float], mae: float, y_axis_title: str) -> go.Figure:
    """Point forecast with a naive +/- MAE band.

    This is NOT a calibrated prediction interval — it's the model's historical
    holdout MAE applied as a flat band around the point forecast, a rough
    uncertainty proxy. Labeled explicitly in the legend so it isn't mistaken
    for a true confidence interval.
    """
    if not hours:
        return _empty_figure()

    color = _CATEGORICAL[0]
    upper = [v + mae for v in values]
    lower = [v - mae for v in values]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[*hours, *hours[::-1]], y=[*upper, *lower[::-1]],
        fill="toself", fillcolor=_with_opacity(color, 0.10),
        line=dict(width=0), hoverinfo="skip",
        name=f"± historical MAE ({mae:.1f})",
    ))
    fig.add_trace(go.Scatter(
        x=hours, y=values, mode="lines+markers",
        line=dict(width=2, color=color), marker=dict(size=6, color=color),
        name="Forecast",
    ))
    fig.update_layout(xaxis_title="Hour of day", yaxis_title=y_axis_title)
    return _apply_layout(fig)
