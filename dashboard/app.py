from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import ALERT_COLORS, ALERT_LABELS, CITIES
from climate_pipeline import (
    ALERTS_FILE,
    FEATURE_IMPORTANCE_FILE,
    FORECAST_RESULTS_FILE,
    HISTORICAL_RISK_FILE,
    METRICS_FILE,
    classify_risk,
)

st.set_page_config(
    page_title="Climate Intelligence | Heatwave Early Warning",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
      html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
      .stApp { background: linear-gradient(180deg, #f8fafc 0%, #eef4f8 100%); }
      h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.025em; }
      .hero { padding: 1.35rem 1.55rem; border-radius: 20px; background: linear-gradient(115deg, #102a43 0%, #155e75 58%, #0f766e 100%); color: white; margin-bottom: 1.2rem; }
      .hero-kicker { text-transform: uppercase; letter-spacing: .16em; font-size: .72rem; font-weight: 700; color: #a7f3d0; }
      .hero-title { font-family: 'Space Grotesk', sans-serif; font-size: 2.05rem; line-height: 1.12; font-weight: 700; margin: .38rem 0 .55rem 0; }
      .hero-subtitle { font-size: .98rem; color: #dbeafe; max-width: 850px; }
      .small-label { color: #64748b; text-transform: uppercase; letter-spacing: .11em; font-weight: 700; font-size: .68rem; }
      .alert-card { padding: 1rem 1.1rem; border: 1px solid #e2e8f0; border-left: 6px solid var(--accent); border-radius: 14px; background: #ffffff; box-shadow: 0 4px 16px rgba(15, 23, 42, .045); margin-bottom: .65rem; }
      .alert-title { font-size: 1.02rem; font-weight: 700; color: #0f172a; margin-bottom: .2rem; }
      .alert-meta { color: #475569; font-size: .84rem; }
      .data-note { background: #fff7ed; border: 1px solid #fed7aa; padding: .8rem 1rem; border-radius: 12px; color: #9a3412; font-size: .88rem; }
      .green-note { background: #ecfdf5; border: 1px solid #a7f3d0; padding: .8rem 1rem; border-radius: 12px; color: #065f46; font-size: .88rem; }
      div[data-testid="stMetric"] { background: white; border: 1px solid #e2e8f0; padding: 14px 16px; border-radius: 14px; box-shadow: 0 4px 14px rgba(15, 23, 42, .035); }
      div[data-testid="stMetricLabel"] { color: #64748b; font-weight: 600; }
      .block-container { padding-top: 1.4rem; padding-bottom: 2.6rem; }
      [data-testid="stSidebar"] { background: #f1f5f9; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    return {
        "historical": _read_csv(HISTORICAL_RISK_FILE),
        "forecast": _read_csv(FORECAST_RESULTS_FILE),
        "alerts": _read_csv(ALERTS_FILE),
        "metrics": _read_csv(METRICS_FILE),
        "importance": _read_csv(FEATURE_IMPORTANCE_FILE),
    }


def fmt_temp(value, unit: str = "°C") -> str:
    if pd.isna(value):
        return "N/A"
    value = float(value)
    if unit == "°F":
        value = value * 9 / 5 + 32
    return f"{value:.1f}{unit}"


def convert_temp_column(frame: pd.DataFrame, columns: list[str], unit: str) -> pd.DataFrame:
    out = frame.copy()
    if unit == "°F":
        for col in columns:
            if col in out.columns:
                out[col] = out[col] * 9 / 5 + 32
    return out


def alert_card(city: str, date_value, level: str, tmax, departure, reason: str, unit: str) -> None:
    color = ALERT_COLORS.get(level, "#64748b")
    day_text = pd.Timestamp(date_value).strftime("%a, %d %b %Y") if pd.notna(date_value) else "Date unavailable"
    st.markdown(
        f"""
        <div class="alert-card" style="--accent:{color}">
          <div class="alert-title">{level} · {city} · {day_text}</div>
          <div class="alert-meta"><b>Forecast maximum:</b> {fmt_temp(tmax, unit)} &nbsp; · &nbsp; <b>Departure from normal:</b> {departure:+.1f}°C</div>
          <div style="margin-top:.42rem;color:#334155;font-size:.88rem">{reason}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def add_heat_thresholds(fig, unit: str = "°C"):
    if unit == "°F":
        levels = [(37, 98.6, "Coastal watch reference", "#eab308"), (40, 104, "40°C reference", "#f97316"), (45, 113, "45°C reference", "#dc2626")]
        for _, y, name, color in levels:
            fig.add_hline(y=y, line_dash="dot", line_color=color, annotation_text=name, annotation_position="top left")
    else:
        for y, name, color in [(37, "37°C coastal reference", "#eab308"), (40, "40°C reference", "#f97316"), (45, "45°C reference", "#dc2626")]:
            fig.add_hline(y=y, line_dash="dot", line_color=color, annotation_text=name, annotation_position="top left")
    return fig


data = load_data()
historical = data["historical"]
forecast = data["forecast"]
alerts = data["alerts"]
metrics = data["metrics"]
importance = data["importance"]

if historical.empty or forecast.empty:
    st.error("Dashboard data is missing. From the project root, run `python src/run_pipeline.py` first.")
    st.stop()

historical["date"] = pd.to_datetime(historical["date"])
forecast["date"] = pd.to_datetime(forecast["date"])
alerts["date"] = pd.to_datetime(alerts["date"], errors="coerce") if not alerts.empty else pd.Series(dtype="datetime64[ns]")

source_values = set(historical.get("data_source", pd.Series(dtype=str)).astype(str).unique())
is_synthetic = any("synthetic" in x.lower() for x in source_values)
source_badge = "DEMO DATA" if is_synthetic else "HISTORICAL WEATHER DATA"

st.markdown(
    f"""
    <div class="hero">
      <div class="hero-kicker">Climate intelligence · Monitoring / Prediction / Early Warning</div>
      <div class="hero-title">Heatwave Monitoring & Early Warning</div>
      <div class="hero-subtitle">Analyse historical temperature patterns, compare machine-learning forecasts with available weather forecasts, and surface transparent heat-risk signals across Indian cities.</div>
      <div style="margin-top:1rem;display:flex;gap:.6rem;flex-wrap:wrap;align-items:center">
        <span style="background:rgba(255,255,255,.14);padding:.35rem .65rem;border-radius:999px;font-size:.76rem;font-weight:700">{source_badge}</span>
        <span style="color:#dbeafe;font-size:.78rem">5 cities · Daily data · 7-day outlook · Temperature ML</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if is_synthetic:
    st.markdown(
        '<div class="data-note"><b>Transparent demo mode:</b> the bundled historical observations are synthetic data for testing the workflow. They are not real observations and must not be used as evidence of actual heat conditions. Choose <code>python src/run_pipeline.py --refresh</code> to fetch Open-Meteo historical and forecast data when internet is available.</div>',
        unsafe_allow_html=True,
    )

with st.sidebar:
    st.markdown("### Monitoring controls")
    city_options = list(CITIES.keys())
    selected_city = st.selectbox("Location", city_options, index=0)
    unit = st.radio("Temperature unit", ["°C", "°F"], horizontal=True, index=0)
    period_label = st.select_slider("Historical window", options=["30 days", "90 days", "1 year", "All data"], value="90 days")
    scenario_uplift = st.slider("What-if Tmax uplift", min_value=0.0, max_value=15.0, value=0.0, step=1.0, help="Stress-test the alert logic by adding a hypothetical temperature increase to the selected city's forecast. This is a simulation, not a live forecast.")
    show_green = st.checkbox("Include normal/green forecast days", value=False)
    st.divider()
    st.caption("Model pipeline")
    st.code("python src/run_pipeline.py\n# Live data refresh\npython src/run_pipeline.py --refresh", language="powershell")
    st.caption("The dashboard updates after the pipeline writes new CSV outputs. Use the refresh icon above to reload files.")

city_hist = historical[historical["city"] == selected_city].sort_values("date").copy()
city_forecast = forecast[forecast["city"] == selected_city].sort_values("date").copy()
city_metrics = metrics[metrics["City"] == selected_city].copy() if not metrics.empty else pd.DataFrame()
if scenario_uplift > 0:
    city_forecast["forecast_tmax_c"] = city_forecast["forecast_tmax_c"].astype(float) + scenario_uplift
    city_forecast["departure_c"] = city_forecast["forecast_tmax_c"] - city_forecast["normal_tmax_c"]
    scenario_levels, scenario_reasons, scenario_scores = [], [], []
    for row in city_forecast.itertuples(index=False):
        level, reason, score = classify_risk(
            row.forecast_tmax_c, row.departure_c, row.humidity_mean_pct, row.region_type
        )
        scenario_levels.append(level)
        scenario_reasons.append(reason)
        scenario_scores.append(score)
    city_forecast["risk_level"] = scenario_levels
    city_forecast["risk_label"] = city_forecast["risk_level"].map(ALERT_LABELS)
    city_forecast["risk_reason"] = scenario_reasons
    city_forecast["risk_score"] = scenario_scores
city_alerts = city_forecast.copy() if show_green else city_forecast[city_forecast["risk_level"].isin(["YELLOW", "ORANGE", "RED"])].copy()

if period_label == "30 days":
    cutoff = city_hist["date"].max() - pd.Timedelta(days=29)
elif period_label == "90 days":
    cutoff = city_hist["date"].max() - pd.Timedelta(days=89)
elif period_label == "1 year":
    cutoff = city_hist["date"].max() - pd.Timedelta(days=364)
else:
    cutoff = city_hist["date"].min()
hist_window = city_hist[city_hist["date"] >= cutoff].copy()

latest = city_hist.sort_values("date").iloc[-1]
forecast_peak = city_forecast.loc[city_forecast["forecast_tmax_c"].idxmax()] if not city_forecast.empty else None
forecast_alert_count = int(city_forecast["risk_level"].isin(["YELLOW", "ORANGE", "RED"]).sum())
red_orange_count = int(city_forecast["risk_level"].isin(["ORANGE", "RED"]).sum())
if city_metrics.empty:
    tmax_mae = np.nan
else:
    max_metric = city_metrics[city_metrics["Target"] == "Maximum temperature (°C)"]
    tmax_mae = float(max_metric.iloc[0]["MAE (°C)"]) if not max_metric.empty else np.nan

metric_cols = st.columns(4)
metric_cols[0].metric("Latest observed max", fmt_temp(latest.get("tmax_c"), unit), f"{pd.Timestamp(latest['date']).strftime('%d %b %Y')}")
metric_cols[1].metric("Peak forecast max", fmt_temp(forecast_peak.get("forecast_tmax_c") if forecast_peak is not None else np.nan, unit), f"{pd.Timestamp(forecast_peak['date']).strftime('%d %b') if forecast_peak is not None else 'No forecast'}")
metric_cols[2].metric("Heat-watch days · next 7 days", forecast_alert_count, f"{red_orange_count} high/extreme")
mae_display = (f"{tmax_mae * 9 / 5:.1f}°F" if unit == "°F" and np.isfinite(tmax_mae) else fmt_temp(tmax_mae, "°C"))
metric_cols[3].metric("Tmax model MAE", mae_display, "chronological holdout")

if scenario_uplift > 0:
    st.markdown(
        f'<div class="data-note"><b>What-if scenario active:</b> +{scenario_uplift:.0f}°C has been added to {selected_city} forecast maximum temperatures. Displayed warnings in this selected-city view are simulated stress-test results, not official or live warnings.</div>',
        unsafe_allow_html=True,
    )

st.markdown("## Command center")
left, right = st.columns([1.45, 1])
with left:
    st.markdown(f"#### {selected_city}: observed temperature trend")
    plot_hist = convert_temp_column(hist_window, ["tmax_c", "tmin_c", "normal_tmax_c"], unit)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plot_hist["date"], y=plot_hist["tmax_c"], name="Observed Tmax", mode="lines", line=dict(color="#ea580c", width=2.4)))
    fig.add_trace(go.Scatter(x=plot_hist["date"], y=plot_hist["tmin_c"], name="Observed Tmin", mode="lines", line=dict(color="#0284c7", width=1.8)))
    fig.add_trace(go.Scatter(x=plot_hist["date"], y=plot_hist["normal_tmax_c"], name="Climatology normal", mode="lines", line=dict(color="#64748b", width=1.5, dash="dash")))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.12), xaxis_title=None, yaxis_title=f"Temperature ({unit})", hovermode="x unified", plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
    add_heat_thresholds(fig, unit)
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.markdown("#### Forecast risk outlook")
    st.caption("Risk levels are calculated from forecast maximum temperature and departure from a historical day-of-year normal.")
    if city_alerts.empty:
        st.markdown('<div class="green-note"><b>No modelled heat-watch days in this forecast window.</b><br/>Continue monitoring as forecasts update.</div>', unsafe_allow_html=True)
    else:
        ordered = city_alerts.copy()
        ordered["level_rank"] = ordered["risk_level"].map({"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3})
        ordered = ordered.sort_values(["level_rank", "risk_score"], ascending=[False, False]).head(5)
        for row in ordered.itertuples(index=False):
            alert_card(selected_city, row.date, row.risk_level, row.forecast_tmax_c, row.departure_c, row.risk_reason, unit)

st.markdown("## Forecast & early warnings")
fc_left, fc_right = st.columns([1.45, 1])
with fc_left:
    st.markdown("#### ML prediction vs forecast reference")
    plot_fc = convert_temp_column(city_forecast, ["forecast_tmax_c", "ml_pred_tmax_c", "forecast_tmin_c", "normal_tmax_c"], unit)
    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(x=plot_fc["date"], y=plot_fc["forecast_tmax_c"], name="Forecast used for risk", mode="lines+markers", line=dict(color="#ea580c", width=2.5)))
    if plot_fc["ml_pred_tmax_c"].notna().any():
        fig_fc.add_trace(go.Scatter(x=plot_fc["date"], y=plot_fc["ml_pred_tmax_c"], name="Random Forest Tmax", mode="lines+markers", line=dict(color="#2563eb", width=2, dash="dash")))
    fig_fc.add_trace(go.Scatter(x=plot_fc["date"], y=plot_fc["normal_tmax_c"], name="Climatology normal", mode="lines", line=dict(color="#64748b", dash="dot")))
    fig_fc.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.12), xaxis_title=None, yaxis_title=f"Maximum temperature ({unit})", hovermode="x unified", plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
    add_heat_thresholds(fig_fc, unit)
    st.plotly_chart(fig_fc, use_container_width=True)
with fc_right:
    st.markdown("#### Daily outlook")
    display_cols = ["date", "forecast_tmax_c", "forecast_tmin_c", "normal_tmax_c", "departure_c", "risk_level", "risk_score", "forecast_source"]
    table = city_forecast[display_cols].copy()
    table["date"] = table["date"].dt.strftime("%d %b")
    table = convert_temp_column(table, ["forecast_tmax_c", "forecast_tmin_c", "normal_tmax_c"], unit)
    table = table.rename(columns={
        "date": "Date", "forecast_tmax_c": f"Max ({unit})", "forecast_tmin_c": f"Min ({unit})",
        "normal_tmax_c": f"Normal ({unit})", "departure_c": "Anomaly (°C)", "risk_level": "Risk",
        "risk_score": "Score / 100", "forecast_source": "Forecast source",
    })
    st.dataframe(table, hide_index=True, use_container_width=True, height=300)
    st.download_button("Download forecast CSV", city_forecast.to_csv(index=False).encode("utf-8"), file_name=f"{selected_city.lower()}_heatwave_forecast.csv", mime="text/csv")

st.markdown("## Historical climate intelligence")
hc1, hc2 = st.columns(2)
with hc1:
    monthly = city_hist.copy()
    monthly["Month"] = monthly["date"].dt.month
    monthly = monthly.groupby("Month", as_index=False).agg(
        Mean_Tmax=("tmax_c", "mean"),
        P95_Tmax=("tmax_c", lambda x: x.quantile(0.95)),
        HeatWatchDays=("risk_level", lambda x: int(x.isin(["YELLOW", "ORANGE", "RED"]).sum())),
    )
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly["MonthName"] = monthly["Month"].map(lambda m: month_names[int(m) - 1])
    monthly_plot = convert_temp_column(monthly, ["Mean_Tmax", "P95_Tmax"], unit)
    fig_m = go.Figure()
    fig_m.add_trace(go.Bar(x=monthly_plot["MonthName"], y=monthly_plot["Mean_Tmax"], name="Mean daily Tmax", marker_color="#0e7490"))
    fig_m.add_trace(go.Scatter(x=monthly_plot["MonthName"], y=monthly_plot["P95_Tmax"], name="95th percentile", mode="lines+markers", line=dict(color="#ea580c", width=2.4)))
    fig_m.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), yaxis_title=f"Temperature ({unit})", xaxis_title=None, legend=dict(orientation="h", y=1.12), plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
    st.markdown("#### Seasonal temperature profile")
    st.plotly_chart(fig_m, use_container_width=True)
with hc2:
    st.markdown("#### Risk-day distribution")
    risk_counts = city_hist["risk_level"].value_counts().reindex(["GREEN", "YELLOW", "ORANGE", "RED"], fill_value=0).reset_index()
    risk_counts.columns = ["Risk level", "Days"]
    fig_r = px.bar(risk_counts, x="Risk level", y="Days", color="Risk level", color_discrete_map=ALERT_COLORS, category_orders={"Risk level": ["GREEN", "YELLOW", "ORANGE", "RED"]})
    fig_r.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), showlegend=False, xaxis_title=None, yaxis_title="Historical days", plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_r, use_container_width=True)

st.markdown("#### City comparison: forecast peak temperature")
peaks = forecast.loc[forecast.groupby("city")["forecast_tmax_c"].idxmax()].copy()
peaks = convert_temp_column(peaks, ["forecast_tmax_c"], unit)
fig_city = px.bar(peaks.sort_values("forecast_tmax_c", ascending=False), x="city", y="forecast_tmax_c", color="risk_level", color_discrete_map=ALERT_COLORS, hover_data=["date", "departure_c", "risk_score"])
fig_city.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), xaxis_title=None, yaxis_title=f"Peak forecast Tmax ({unit})", plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig_city, use_container_width=True)

st.markdown("## Model evaluation")
if not metrics.empty:
    met_display = metrics.copy()
    for col in ["MAE (°C)", "RMSE (°C)"]:
        if unit == "°F":
            met_display[col] = met_display[col] * 9 / 5
            met_display = met_display.rename(columns={col: col.replace("°C", "°F")})
    st.dataframe(met_display, hide_index=True, use_container_width=True)
    st.caption("The holdout is chronological: later dates are held out from model fitting. These metrics apply to the bundled data source shown in the banner; synthetic-demo metrics validate the pipeline, not real-world forecast accuracy.")
else:
    st.info("Model metrics are not available yet. Run `python src/run_pipeline.py`.")

if not importance.empty:
    st.markdown("#### What the model uses")
    target_choice = st.selectbox("Target", ["tmax", "tmin"], format_func=lambda x: "Maximum temperature" if x == "tmax" else "Minimum temperature")
    imp = importance[(importance["City"] == selected_city) & (importance["Target"] == target_choice)].nlargest(12, "Importance").sort_values("Importance")
    fig_imp = px.bar(imp, x="Importance", y="Feature", orientation="h", color="Importance", color_continuous_scale="Teal")
    fig_imp.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), coloraxis_showscale=False, xaxis_title="Random Forest feature importance", yaxis_title=None, plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_imp, use_container_width=True)

st.markdown("## Method and responsible use")
with st.expander("How does the warning logic work?", expanded=False):
    st.markdown(
        """
        **Temperature prediction:** Random Forest regression models estimate daily maximum and minimum temperatures from lagged values, recent rolling averages, and annual/seasonal calendar features. All temperature lag features use only earlier dates. A chronological holdout is used to report MAE, RMSE, and R².

        **Historical normal:** A smoothed day-of-year normal is computed from the available historical record. The anomaly is forecast maximum temperature minus that normal.

        **Risk levels:** The project's transparent heuristic uses absolute temperature, departure from normal, region type, and humidity. The composite 0–100 score is a project-specific monitoring score, not a medical heat index.

        **Important limitation:** The dashboard displays *modelled heat-risk signals*, not official IMD warnings. Official declarations involve station-specific procedures, persistence, regional coverage, and operational review. Always defer to official IMD bulletins and local authorities for real-world decisions.
        """
    )
with st.expander("Data sources and provenance", expanded=False):
    st.markdown(
        """
        - **Historical Weather API:** Open-Meteo historical archive using reanalysis data. [Documentation](https://open-meteo.com/en/docs/historical-weather-api)
        - **Forecast API:** Open-Meteo daily forecast and hourly relative humidity. [Documentation](https://open-meteo.com/en/docs)
        - **Heatwave criteria reference:** India Meteorological Department. [IMD heat-wave definition and criteria](https://mausam.imd.gov.in/pdfs/heatcolduser/morning_heat_bulletin.pdf)
        - If bundled sample records are in use, the source is marked `synthetic_demo`. Refresh with `python src/run_pipeline.py --refresh` to attempt a live data download.
        """
    )

st.caption("Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning · Educational prototype · Not an official warning service.")
