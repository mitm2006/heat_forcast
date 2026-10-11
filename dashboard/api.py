"""FastAPI backend — Climate Intelligence Heatwave Dashboard.

Serves all data endpoints consumed by the Flask frontend.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import io

from config import ALERT_COLORS, ALERT_LABELS, CITIES
from climate_pipeline import (
    ALERTS_FILE,
    FEATURE_IMPORTANCE_FILE,
    FORECAST_RESULTS_FILE,
    HISTORICAL_RISK_FILE,
    METRICS_FILE,
    classify_risk,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Climate Intelligence API",
    description="Heatwave Monitoring, Prediction & Early Warning — REST API",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/healthz")
def health_check():
    """Health check endpoint for container and Kubernetes probes."""
    return {"status": "healthy", "service": "climate-api"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def _load() -> dict[str, pd.DataFrame]:
    return {
        "historical": _read_csv(HISTORICAL_RISK_FILE),
        "forecast": _read_csv(FORECAST_RESULTS_FILE),
        "alerts": _read_csv(ALERTS_FILE),
        "metrics": _read_csv(METRICS_FILE),
        "importance": _read_csv(FEATURE_IMPORTANCE_FILE),
    }


def _to_unit(value: float, unit: str) -> float:
    if unit == "F":
        return round(value * 9 / 5 + 32, 2) if (value is not None and np.isfinite(value)) else None
    return round(float(value), 2) if (value is not None and np.isfinite(float(value))) else None


def _convert_df_temps(frame: pd.DataFrame, cols: list[str], unit: str) -> pd.DataFrame:
    out = frame.copy()
    if unit == "F":
        for col in cols:
            if col in out.columns:
                out[col] = out[col].apply(lambda v: v * 9 / 5 + 32 if pd.notna(v) else v)
    return out


def _safe(val):
    if val is None:
        return None
    if isinstance(val, float) and not np.isfinite(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    return val

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/cities")
def get_cities():
    return {
        city: {
            "state": cfg["state"],
            "region_type": cfg["region_type"],
            "latitude": cfg["latitude"],
            "longitude": cfg["longitude"],
        }
        for city, cfg in CITIES.items()
    }


@app.get("/api/status")
def get_status():
    data = _load()
    historical = data["historical"]
    forecast = data["forecast"]
    ready = not historical.empty and not forecast.empty

    source_badge = "LIVE DATA"
    if not historical.empty:
        source_values = set(historical.get("data_source", pd.Series(dtype=str)).astype(str).unique())
        if any("synthetic" in x.lower() for x in source_values):
            source_badge = "DEMO DATA"

    return {"ready": ready, "source_badge": source_badge, "cities": list(CITIES.keys())}


@app.get("/api/summary")
def get_summary(city: str = Query(...), unit: str = Query("C")):
    data = _load()
    historical = data["historical"]
    forecast = data["forecast"]
    metrics = data["metrics"]

    if historical.empty or forecast.empty:
        raise HTTPException(status_code=503, detail="Pipeline data not yet generated.")

    historical["date"] = pd.to_datetime(historical["date"])
    forecast["date"] = pd.to_datetime(forecast["date"])

    city_hist = historical[historical["city"] == city].sort_values("date")
    city_forecast = forecast[forecast["city"] == city].sort_values("date")
    city_metrics = metrics[metrics["City"] == city].copy() if not metrics.empty else pd.DataFrame()

    if city_hist.empty:
        raise HTTPException(status_code=404, detail=f"No data for city: {city}")

    latest = city_hist.iloc[-1]
    forecast_peak = city_forecast.loc[city_forecast["forecast_tmax_c"].idxmax()] if not city_forecast.empty else None
    alert_days = int(city_forecast["risk_level"].isin(["YELLOW", "ORANGE", "RED"]).sum())
    high_days = int(city_forecast["risk_level"].isin(["ORANGE", "RED"]).sum())

    tmax_mae = None
    if not city_metrics.empty:
        row = city_metrics[city_metrics["Target"] == "Maximum temperature (°C)"]
        if not row.empty:
            tmax_mae = float(row.iloc[0]["MAE (°C)"])
            if unit == "F":
                tmax_mae = round(tmax_mae * 9 / 5, 2)

    return {
        "latest_tmax": _to_unit(float(latest.get("tmax_c", float("nan"))), unit),
        "latest_date": pd.Timestamp(latest["date"]).strftime("%d %b %Y"),
        "peak_forecast_tmax": _to_unit(float(forecast_peak.get("forecast_tmax_c", float("nan"))) if forecast_peak is not None else float("nan"), unit),
        "peak_forecast_date": pd.Timestamp(forecast_peak["date"]).strftime("%d %b") if forecast_peak is not None else None,
        "alert_days": alert_days,
        "high_days": high_days,
        "tmax_mae": tmax_mae,
        "unit": unit,
    }


@app.get("/api/historical")
def get_historical(city: str = Query(...), unit: str = Query("C"), window: str = Query("90d")):
    data = _load()
    historical = data["historical"]
    if historical.empty:
        raise HTTPException(status_code=503, detail="Pipeline data not yet generated.")

    historical["date"] = pd.to_datetime(historical["date"])
    city_hist = historical[historical["city"] == city].sort_values("date").copy()

    if city_hist.empty:
        raise HTTPException(status_code=404, detail=f"No data for city: {city}")

    max_date = city_hist["date"].max()
    window_map = {"30d": 29, "90d": 89, "1y": 364}
    days_back = window_map.get(window, None)
    if days_back is not None:
        city_hist = city_hist[city_hist["date"] >= max_date - pd.Timedelta(days=days_back)]

    city_hist = _convert_df_temps(city_hist, ["tmax_c", "tmin_c", "normal_tmax_c"], unit)

    records = []
    for row in city_hist.itertuples(index=False):
        records.append({
            "date": pd.Timestamp(row.date).strftime("%Y-%m-%d"),
            "tmax": _safe(row.tmax_c),
            "tmin": _safe(row.tmin_c),
            "normal_tmax": _safe(row.normal_tmax_c),
            "risk_level": _safe(row.risk_level),
        })
    return {"city": city, "unit": unit, "data": records}


@app.get("/api/forecast")
def get_forecast(
    city: str = Query(...),
    unit: str = Query("C"),
    scenario_uplift: float = Query(0.0),
    show_green: bool = Query(False),
):
    data = _load()
    forecast = data["forecast"]
    if forecast.empty:
        raise HTTPException(status_code=503, detail="Pipeline data not yet generated.")

    forecast["date"] = pd.to_datetime(forecast["date"])
    city_forecast = forecast[forecast["city"] == city].sort_values("date").copy()

    if city_forecast.empty:
        raise HTTPException(status_code=404, detail=f"No data for city: {city}")

    if scenario_uplift > 0:
        city_forecast["forecast_tmax_c"] = city_forecast["forecast_tmax_c"].astype(float) + scenario_uplift
        city_forecast["departure_c"] = city_forecast["forecast_tmax_c"] - city_forecast["normal_tmax_c"]
        levels, reasons, scores = [], [], []
        for row in city_forecast.itertuples(index=False):
            level, reason, score = classify_risk(
                row.forecast_tmax_c, row.departure_c, row.humidity_mean_pct, row.region_type
            )
            levels.append(level)
            reasons.append(reason)
            scores.append(score)
        city_forecast["risk_level"] = levels
        city_forecast["risk_reason"] = reasons
        city_forecast["risk_score"] = scores

    plot_fc = _convert_df_temps(city_forecast, ["forecast_tmax_c", "ml_pred_tmax_c", "forecast_tmin_c", "normal_tmax_c"], unit)

    records = []
    for row in plot_fc.itertuples(index=False):
        records.append({
            "date": pd.Timestamp(row.date).strftime("%Y-%m-%d"),
            "forecast_tmax": _safe(row.forecast_tmax_c),
            "ml_pred_tmax": _safe(getattr(row, "ml_pred_tmax_c", None)),
            "forecast_tmin": _safe(getattr(row, "forecast_tmin_c", None)),
            "normal_tmax": _safe(row.normal_tmax_c),
            "departure": _safe(getattr(row, "departure_c", None)),
            "risk_level": _safe(row.risk_level),
            "risk_score": _safe(getattr(row, "risk_score", None)),
            "risk_reason": _safe(getattr(row, "risk_reason", None)),
            "forecast_source": _safe(getattr(row, "forecast_source", None)),
        })
    return {"city": city, "unit": unit, "scenario_uplift": scenario_uplift, "data": records}


@app.get("/api/alerts")
def get_alerts(city: str = Query(...), unit: str = Query("C"), scenario_uplift: float = Query(0.0), show_green: bool = Query(False)):
    forecast_resp = get_forecast(city=city, unit=unit, scenario_uplift=scenario_uplift, show_green=True)
    all_rows = forecast_resp["data"]
    alert_rows = all_rows if show_green else [r for r in all_rows if r["risk_level"] in ("YELLOW", "ORANGE", "RED")]
    level_rank = {"RED": 3, "ORANGE": 2, "YELLOW": 1, "GREEN": 0}
    alert_rows.sort(key=lambda r: (level_rank.get(r["risk_level"], 0), r["risk_score"] or 0), reverse=True)
    return {"city": city, "alerts": alert_rows[:5]}


@app.get("/api/seasonal")
def get_seasonal(city: str = Query(...), unit: str = Query("C")):
    data = _load()
    historical = data["historical"]
    if historical.empty:
        raise HTTPException(status_code=503, detail="Pipeline data not yet generated.")

    historical["date"] = pd.to_datetime(historical["date"])
    city_hist = historical[historical["city"] == city].copy()
    city_hist["month"] = city_hist["date"].dt.month

    monthly = city_hist.groupby("month", as_index=False).agg(
        mean_tmax=("tmax_c", "mean"),
        p95_tmax=("tmax_c", lambda x: x.quantile(0.95)),
        heat_days=("risk_level", lambda x: int(x.isin(["YELLOW", "ORANGE", "RED"]).sum())),
    )
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly["month_name"] = monthly["month"].map(lambda m: month_names[int(m) - 1])

    if unit == "F":
        monthly["mean_tmax"] = monthly["mean_tmax"] * 9 / 5 + 32
        monthly["p95_tmax"] = monthly["p95_tmax"] * 9 / 5 + 32

    return {
        "city": city,
        "unit": unit,
        "data": [
            {
                "month": row.month_name,
                "mean_tmax": round(float(row.mean_tmax), 2),
                "p95_tmax": round(float(row.p95_tmax), 2),
                "heat_days": int(row.heat_days),
            }
            for row in monthly.itertuples(index=False)
        ],
    }


@app.get("/api/risk-distribution")
def get_risk_distribution(city: str = Query(...)):
    data = _load()
    historical = data["historical"]
    if historical.empty:
        raise HTTPException(status_code=503, detail="Pipeline data not yet generated.")

    historical["date"] = pd.to_datetime(historical["date"])
    city_hist = historical[historical["city"] == city].copy()
    counts = city_hist["risk_level"].value_counts().reindex(["GREEN", "YELLOW", "ORANGE", "RED"], fill_value=0)
    return {
        "city": city,
        "data": [{"level": lvl, "days": int(counts[lvl]), "color": ALERT_COLORS[lvl]} for lvl in ["GREEN", "YELLOW", "ORANGE", "RED"]],
    }


@app.get("/api/city-peaks")
def get_city_peaks(unit: str = Query("C")):
    data = _load()
    forecast = data["forecast"]
    if forecast.empty:
        raise HTTPException(status_code=503, detail="Pipeline data not yet generated.")

    forecast["date"] = pd.to_datetime(forecast["date"])
    peaks = forecast.loc[forecast.groupby("city")["forecast_tmax_c"].idxmax()].copy()
    if unit == "F":
        peaks["forecast_tmax_c"] = peaks["forecast_tmax_c"] * 9 / 5 + 32

    records = [
        {
            "city": _safe(row.city),
            "peak_tmax": round(float(row.forecast_tmax_c), 2),
            "date": pd.Timestamp(row.date).strftime("%Y-%m-%d"),
            "risk_level": _safe(row.risk_level),
            "risk_score": _safe(getattr(row, "risk_score", None)),
            "color": ALERT_COLORS.get(_safe(row.risk_level), "#64748b"),
        }
        for row in peaks.itertuples(index=False)
    ]
    records.sort(key=lambda r: r["peak_tmax"], reverse=True)
    return {"unit": unit, "data": records}


@app.get("/api/metrics")
def get_metrics(unit: str = Query("C")):
    data = _load()
    metrics = data["metrics"]
    if metrics.empty:
        return {"data": []}

    out = metrics.copy()
    if unit == "F":
        for col in ["MAE (°C)", "RMSE (°C)"]:
            if col in out.columns:
                out[col] = (out[col] * 9 / 5).round(3)
                out = out.rename(columns={col: col.replace("°C", "°F")})

    return {"unit": unit, "data": out.to_dict(orient="records")}


@app.get("/api/feature-importance")
def get_feature_importance(city: str = Query(...), target: str = Query("tmax")):
    data = _load()
    importance = data["importance"]
    if importance.empty:
        return {"city": city, "target": target, "data": []}

    imp = importance[
        (importance["City"] == city) & (importance["Target"] == target)
    ].nlargest(12, "Importance").sort_values("Importance")

    return {
        "city": city,
        "target": target,
        "data": [{"feature": str(row.Feature), "importance": round(float(row.Importance), 6)} for row in imp.itertuples(index=False)],
    }


@app.get("/api/download/forecast")
def download_forecast(city: str = Query(...)):
    data = _load()
    forecast = data["forecast"]
    if forecast.empty:
        raise HTTPException(status_code=503, detail="Pipeline data not yet generated.")

    city_forecast = forecast[forecast["city"] == city].copy()
    if city_forecast.empty:
        raise HTTPException(status_code=404, detail=f"No forecast data for city: {city}")

    csv_bytes = city_forecast.to_csv(index=False).encode("utf-8")
    filename = f"{city.lower()}_heatwave_forecast.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
