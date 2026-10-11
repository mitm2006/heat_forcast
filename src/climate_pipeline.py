"""Data, modelling, forecast, and risk-scoring helpers for the project."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import math
import warnings

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from config import (
    ALERT_LABELS,
    CITIES,
    DATA_DIR,
    FORECAST_DAYS,
    HISTORY_START,
    MODEL_DIR,
    RANDOM_STATE,
    TIMEZONE,
)

FEATURE_COLUMNS = [
    "lag_tmax_1", "lag_tmax_2", "lag_tmax_3", "lag_tmax_7", "lag_tmax_14",
    "lag_tmin_1", "lag_tmin_7", "roll_tmax_3", "roll_tmax_7", "roll_tmax_14",
    "roll_tmin_3", "day_sin", "day_cos", "month_sin", "month_cos",
]

HISTORY_FILE = DATA_DIR / "historical_daily.csv"
FORECAST_INPUT_FILE = DATA_DIR / "forecast_daily.csv"
HISTORICAL_RISK_FILE = DATA_DIR / "historical_risk.csv"
FORECAST_RESULTS_FILE = DATA_DIR / "forecast_results.csv"
ALERTS_FILE = DATA_DIR / "alerts.csv"
METRICS_FILE = DATA_DIR / "model_metrics.csv"
FEATURE_IMPORTANCE_FILE = DATA_DIR / "model_feature_importance.csv"


def _slug(city: str) -> str:
    return city.lower().replace(" ", "_")


def _safe_float(value, default=np.nan) -> float:
    try:
        result = float(value)
        return result if np.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def fetch_open_meteo_history(city: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch hourly ERA5-family historical data and aggregate it to daily records."""
    cfg = CITIES[city]
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation",
        "timezone": TIMEZONE,
    }
    response = requests.get(url, params=params, timeout=90)
    response.raise_for_status()
    payload = response.json()
    hourly = payload.get("hourly", {})
    if not hourly or not hourly.get("time"):
        raise ValueError(f"Open-Meteo returned no hourly data for {city}.")

    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(hourly["time"]),
        "temperature_c": hourly.get("temperature_2m", []),
        "humidity_pct": hourly.get("relative_humidity_2m", []),
        "precipitation_mm_hour": hourly.get("precipitation", []),
    })
    frame["date"] = frame["timestamp"].dt.normalize()
    daily = frame.groupby("date", as_index=False).agg(
        tmax_c=("temperature_c", "max"),
        tmin_c=("temperature_c", "min"),
        tmean_c=("temperature_c", "mean"),
        humidity_mean_pct=("humidity_pct", "mean"),
        precipitation_mm=("precipitation_mm_hour", "sum"),
    )
    daily.insert(0, "city", city)
    daily["data_source"] = "Open-Meteo Historical API"
    daily["latitude"] = cfg["latitude"]
    daily["longitude"] = cfg["longitude"]
    daily["region_type"] = cfg["region_type"]
    daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    return daily


def fetch_open_meteo_forecast(city: str, forecast_days: int = FORECAST_DAYS) -> pd.DataFrame:
    """Fetch the provider's daily forecast and aggregate hourly relative humidity."""
    cfg = CITIES[city]
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max",
        "hourly": "relative_humidity_2m",
        "forecast_days": forecast_days,
        "timezone": TIMEZONE,
    }
    response = requests.get(url, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    daily = payload.get("daily", {})
    if not daily or not daily.get("time"):
        raise ValueError(f"Open-Meteo returned no forecast data for {city}.")

    forecast = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "forecast_tmax_c": daily.get("temperature_2m_max", []),
        "forecast_tmin_c": daily.get("temperature_2m_min", []),
        "apparent_temperature_max_c": daily.get("apparent_temperature_max", []),
    })
    hourly = payload.get("hourly", {})
    if hourly.get("time") and hourly.get("relative_humidity_2m"):
        humidity = pd.DataFrame({
            "timestamp": pd.to_datetime(hourly["time"]),
            "humidity_pct": hourly["relative_humidity_2m"],
        })
        humidity["date"] = humidity["timestamp"].dt.normalize()
        humidity_daily = humidity.groupby("date", as_index=False)["humidity_pct"].mean()
        humidity_daily = humidity_daily.rename(columns={"humidity_pct": "humidity_mean_pct"})
        forecast = forecast.merge(humidity_daily, on="date", how="left")
    else:
        forecast["humidity_mean_pct"] = np.nan

    forecast.insert(0, "city", city)
    forecast["forecast_source"] = "Open-Meteo Forecast API"
    forecast["latitude"] = cfg["latitude"]
    forecast["longitude"] = cfg["longitude"]
    forecast["region_type"] = cfg["region_type"]
    forecast["date"] = pd.to_datetime(forecast["date"]).dt.strftime("%Y-%m-%d")
    return forecast


def generate_synthetic_history(city: str, start_date: str = "2014-01-01", end_date: str | None = None) -> pd.DataFrame:
    """Create clearly labelled synthetic demo data when live historical data is unavailable."""
    cfg = CITIES[city]
    if end_date is None:
        end_date = (pd.Timestamp.today().normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    dates = pd.date_range(start_date, end_date, freq="D")
    rng = np.random.default_rng(RANDOM_STATE + sum(ord(c) for c in city))
    city_adjustment = {
        "Pune": 0.0, "Mumbai": -2.8, "Nagpur": 2.7, "Delhi": 2.5, "Ahmedabad": 2.2,
    }.get(city, 0.0)
    humidity_base = {"Pune": 57, "Mumbai": 76, "Nagpur": 48, "Delhi": 43, "Ahmedabad": 45}.get(city, 50)
    rows = []
    for idx, timestamp in enumerate(dates):
        doy = timestamp.dayofyear
        # Northern-hemisphere seasonality: hottest period is late April to June.
        annual = math.cos(2 * math.pi * (doy - 135) / 365.25)
        tmax = 31.0 + city_adjustment + 7.0 * annual + rng.normal(0, 1.9)
        tmin = tmax - (8.5 + rng.normal(0, 1.2))
        monsoon = timestamp.month in (6, 7, 8, 9)
        if monsoon:
            humidity = humidity_base + 17 + rng.normal(0, 8)
            tmax -= rng.uniform(0.5, 2.5)
            tmin += rng.uniform(0.2, 1.2)
        else:
            humidity = humidity_base + rng.normal(0, 9)
        rainfall = max(0.0, rng.gamma(1.1, 3.0) if monsoon else rng.gamma(0.5, 1.3) - 0.5)
        # Add multi-day heat spells in the hot season to test early-warning logic.
        if timestamp.month in (4, 5, 6) and (timestamp.day in range(12, 18) or timestamp.day in range(25, 29)):
            tmax += {"Mumbai": 0.9, "Pune": 3.5, "Nagpur": 4.8, "Delhi": 4.6, "Ahmedabad": 4.5}.get(city, 3.0)
            tmin += 1.8
            humidity -= 4
        if city == "Mumbai":
            tmax = min(tmax, 41.5)
            tmin = max(tmin, 20.0)
        else:
            tmax = min(tmax, 49.0)
        rows.append({
            "city": city,
            "date": timestamp.strftime("%Y-%m-%d"),
            "tmax_c": round(float(tmax), 2),
            "tmin_c": round(float(min(tmin, tmax - 1.0)), 2),
            "tmean_c": round(float((tmax + tmin) / 2), 2),
            "humidity_mean_pct": round(float(np.clip(humidity, 15, 100)), 2),
            "precipitation_mm": round(float(rainfall), 2),
            "data_source": "synthetic_demo",
            "latitude": cfg["latitude"],
            "longitude": cfg["longitude"],
            "region_type": cfg["region_type"],
        })
    return pd.DataFrame(rows)


def make_supervised(history: pd.DataFrame) -> pd.DataFrame:
    """Create leakage-safe features: all temperature predictors are shifted by >= 1 day."""
    frame = history.sort_values("date").copy()
    frame["date"] = pd.to_datetime(frame["date"])
    features = pd.DataFrame(index=frame.index)
    for lag in (1, 2, 3, 7, 14):
        features[f"lag_tmax_{lag}"] = frame["tmax_c"].shift(lag)
    for lag in (1, 7):
        features[f"lag_tmin_{lag}"] = frame["tmin_c"].shift(lag)
    for window in (3, 7, 14):
        features[f"roll_tmax_{window}"] = frame["tmax_c"].shift(1).rolling(window).mean()
    features["roll_tmin_3"] = frame["tmin_c"].shift(1).rolling(3).mean()
    doy = frame["date"].dt.dayofyear.to_numpy()
    month = frame["date"].dt.month.to_numpy()
    features["day_sin"] = np.sin(2 * np.pi * doy / 365.25)
    features["day_cos"] = np.cos(2 * np.pi * doy / 365.25)
    features["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    features["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    features["date"] = frame["date"].values
    features["target_tmax_c"] = frame["tmax_c"].values
    features["target_tmin_c"] = frame["tmin_c"].values
    return features.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)


def _new_model() -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        min_samples_leaf=4,
        max_features=0.9,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )


def train_city_models(history: pd.DataFrame, city: str) -> tuple[dict, list[dict], list[dict]]:
    """Train Tmax/Tmin models and measure performance on the chronological holdout."""
    supervised = make_supervised(history)
    if len(supervised) < 250:
        raise ValueError(f"Not enough historical rows to train a reliable demo model for {city}.")
    split = max(int(len(supervised) * 0.8), 1)
    train, test = supervised.iloc[:split], supervised.iloc[split:]
    models = {}
    metrics = []
    feature_importance = []
    for target in ("target_tmax_c", "target_tmin_c"):
        validation_model = _new_model()
        validation_model.fit(train[FEATURE_COLUMNS], train[target])
        predicted = validation_model.predict(test[FEATURE_COLUMNS])
        actual = test[target].to_numpy()
        metrics.append({
            "City": city,
            "Target": "Maximum temperature (°C)" if target == "target_tmax_c" else "Minimum temperature (°C)",
            "MAE (°C)": round(float(mean_absolute_error(actual, predicted)), 3),
            "RMSE (°C)": round(float(np.sqrt(mean_squared_error(actual, predicted))), 3),
            "R²": round(float(r2_score(actual, predicted)), 4),
            "Train rows": int(len(train)),
            "Test rows": int(len(test)),
        })
        final_model = _new_model()
        final_model.fit(supervised[FEATURE_COLUMNS], supervised[target])
        target_name = "tmax" if target == "target_tmax_c" else "tmin"
        models[target_name] = final_model
        joblib.dump(final_model, MODEL_DIR / f"{_slug(city)}_{target_name}.joblib")
        for name, importance in zip(FEATURE_COLUMNS, final_model.feature_importances_):
            feature_importance.append({"City": city, "Target": target_name, "Feature": name, "Importance": float(importance)})
    return models, metrics, feature_importance


def _feature_for_date(history: pd.DataFrame, target_date: pd.Timestamp) -> pd.DataFrame:
    frame = history.sort_values("date").copy()
    frame["date"] = pd.to_datetime(frame["date"])
    max_values = frame["tmax_c"].astype(float).to_numpy()
    min_values = frame["tmin_c"].astype(float).to_numpy()
    if len(frame) < 14:
        raise ValueError("At least 14 days of history are required to build forecast features.")
    row = {}
    for lag in (1, 2, 3, 7, 14):
        row[f"lag_tmax_{lag}"] = max_values[-lag]
    for lag in (1, 7):
        row[f"lag_tmin_{lag}"] = min_values[-lag]
    for window in (3, 7, 14):
        row[f"roll_tmax_{window}"] = float(np.mean(max_values[-window:]))
    row["roll_tmin_3"] = float(np.mean(min_values[-3:]))
    doy = target_date.dayofyear
    month = target_date.month
    row["day_sin"] = math.sin(2 * math.pi * doy / 365.25)
    row["day_cos"] = math.cos(2 * math.pi * doy / 365.25)
    row["month_sin"] = math.sin(2 * math.pi * month / 12.0)
    row["month_cos"] = math.cos(2 * math.pi * month / 12.0)
    return pd.DataFrame([[row[c] for c in FEATURE_COLUMNS]], columns=FEATURE_COLUMNS)


def recursive_ml_forecast(history: pd.DataFrame, city: str, models: dict, days: int = FORECAST_DAYS) -> pd.DataFrame:
    """Recursively forecast temperatures when live provider forecasts are not available."""
    cfg = CITIES[city]
    work = history.copy().sort_values("date")
    work["date"] = pd.to_datetime(work["date"])
    start_date = pd.Timestamp.today().normalize()
    last_date = work["date"].max().normalize()
    start_date = max(start_date, last_date + pd.Timedelta(days=1))
    results = []
    for offset in range(days):
        target_date = start_date + pd.Timedelta(days=offset)
        x = _feature_for_date(work, target_date)
        pred_max = float(models["tmax"].predict(x)[0])
        pred_min = float(models["tmin"].predict(x)[0])
        pred_max = float(np.clip(pred_max, -5, 55))
        pred_min = float(np.clip(pred_min, -10, pred_max - 1))
        last_humidity = float(work["humidity_mean_pct"].tail(7).mean())
        results.append({
            "city": city,
            "date": target_date.strftime("%Y-%m-%d"),
            "forecast_tmax_c": round(pred_max, 2),
            "forecast_tmin_c": round(pred_min, 2),
            "humidity_mean_pct": round(last_humidity, 2),
            "forecast_source": "ML recursive fallback (demo)",
            "latitude": cfg["latitude"],
            "longitude": cfg["longitude"],
            "region_type": cfg["region_type"],
        })
        append_row = pd.DataFrame([{
            "city": city, "date": target_date, "tmax_c": pred_max, "tmin_c": pred_min,
            "tmean_c": (pred_max + pred_min) / 2, "humidity_mean_pct": last_humidity,
            "precipitation_mm": 0.0, "data_source": "recursive_prediction",
            "latitude": cfg["latitude"], "longitude": cfg["longitude"], "region_type": cfg["region_type"],
        }])
        work = pd.concat([work, append_row], ignore_index=True)
    return pd.DataFrame(results)


def climatology_normals(history: pd.DataFrame, dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Return a smoothed day-of-year Tmax normal based on the available historical record."""
    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["doy"] = frame["date"].dt.dayofyear
    grouped = frame.groupby("doy")["tmax_c"].mean().reindex(range(1, 367))
    grouped = grouped.interpolate(limit_direction="both")
    # Smooth circularly so December/January and leap-day boundaries behave sensibly.
    arr = grouped.to_numpy(dtype=float)
    if np.isnan(arr).all():
        return np.full(len(dates), np.nan)
    arr = pd.Series(arr).interpolate(limit_direction="both").to_numpy()
    extended = np.concatenate([arr[-15:], arr, arr[:15]])
    smoothed = np.convolve(extended, np.ones(31) / 31.0, mode="valid")
    normal_by_doy = smoothed[:366]
    date_values = pd.to_datetime(pd.Series(dates))
    doys = date_values.dt.dayofyear.to_numpy()
    return normal_by_doy[doys - 1]


def classify_risk(tmax: float, departure: float, humidity: float, region_type: str) -> tuple[str, str, float]:
    """Project heat-risk levels aligned with IMD temperature criteria, not official alerts."""
    tmax = _safe_float(tmax, -99.0)
    departure = _safe_float(departure, 0.0)
    humidity = _safe_float(humidity, 50.0)
    region_type = str(region_type or "plains").lower()

    if region_type == "coastal":
        if (tmax >= 45) or (tmax >= 37 and departure >= 6.5):
            level = "RED"
            reason = "Extreme coastal heat signal: very high maximum temperature or a large positive departure from normal."
        elif tmax >= 37 and departure >= 4.5:
            level = "ORANGE"
            reason = "Coastal heat signal: maximum temperature is at least 37°C and at least 4.5°C above normal."
        elif tmax >= 37 or departure >= 4.5:
            level = "YELLOW"
            reason = "Heat watch: elevated temperature or an unusually warm day; monitor the next forecast update."
        else:
            level = "GREEN"
            reason = "No temperature-based heat-watch trigger in this project rule set."
    else:
        if tmax >= 47 or (tmax >= 40 and departure >= 6.5):
            level = "RED"
            reason = "Extreme heat signal: maximum temperature is at least 47°C or is at least 40°C with a ≥6.5°C positive departure."
        elif tmax >= 45 or (tmax >= 40 and departure >= 4.5):
            level = "ORANGE"
            reason = "High heat signal: maximum temperature is at least 45°C, or at least 40°C with a 4.5–6.4°C positive departure."
        elif tmax >= 40 or departure >= 4.5 or (tmax >= 37 and humidity >= 75):
            level = "YELLOW"
            reason = "Heat watch: high absolute temperature, unusual warmth, or hot and humid conditions need monitoring."
        else:
            level = "GREEN"
            reason = "No temperature-based heat-watch trigger in this project rule set."

    # Explainable 0–100 research score. This is a project heuristic, not a clinical heat index.
    temp_component = np.clip((tmax - 32.0) / 15.0 * 50.0, 0, 50)
    anomaly_component = np.clip(max(departure, 0.0) / 7.0 * 25.0, 0, 25)
    humidity_component = np.clip((humidity - 40.0) / 50.0 * 15.0, 0, 15)
    score = float(np.clip(temp_component + anomaly_component + humidity_component, 0, 100))
    return level, reason, round(score, 1)


def enrich_with_risk(frame: pd.DataFrame, history: pd.DataFrame, is_forecast: bool = False) -> pd.DataFrame:
    """Attach climatology departures, transparent risk levels and composite risk scores."""
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"])
    result["normal_tmax_c"] = climatology_normals(history, result["date"])
    temp_col = "forecast_tmax_c" if is_forecast else "tmax_c"
    result["departure_c"] = result[temp_col].astype(float) - result["normal_tmax_c"].astype(float)
    if "humidity_mean_pct" not in result.columns:
        result["humidity_mean_pct"] = 50.0
    levels, reasons, scores = [], [], []
    for row in result.itertuples(index=False):
        level, reason, score = classify_risk(
            getattr(row, temp_col), getattr(row, "departure_c"),
            getattr(row, "humidity_mean_pct"), getattr(row, "region_type", "plains"),
        )
        levels.append(level)
        reasons.append(reason)
        scores.append(score)
    result["risk_level"] = levels
    result["risk_label"] = result["risk_level"].map(ALERT_LABELS)
    result["risk_reason"] = reasons
    result["risk_score"] = scores
    result["tmax_threshold_c"] = result["region_type"].apply(lambda region: 37.0 if region == "coastal" else 40.0)
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    return result


def prepare_forecast_input(
    history_by_city: dict[str, pd.DataFrame],
    models_by_city: dict[str, dict],
    refresh: bool = False,
) -> pd.DataFrame:
    """Use Open-Meteo forecasts when refreshing; otherwise use bundled demo forecast if current."""
    today = pd.Timestamp.today().normalize()
    existing = None
    if FORECAST_INPUT_FILE.exists() and not refresh:
        try:
            existing = pd.read_csv(FORECAST_INPUT_FILE)
            existing["date"] = pd.to_datetime(existing["date"])
            if (
                set(CITIES.keys()).issubset(set(existing["city"].unique()))
                and existing["date"].min() >= today
                and existing["date"].max() <= today + pd.Timedelta(days=FORECAST_DAYS + 1)
            ):
                return existing
        except Exception:
            existing = None

    live_rows = []
    if refresh:
        failed = []
        for city in CITIES:
            try:
                live_rows.append(fetch_open_meteo_forecast(city))
                print(f"[forecast] Retrieved Open-Meteo forecast for {city}.")
            except Exception as exc:  # API availability should not block local demo use.
                failed.append((city, str(exc)))
                print(f"[forecast] Live forecast unavailable for {city}: {exc}")
        if live_rows:
            live = pd.concat(live_rows, ignore_index=True)
            if failed:
                fallback_rows = []
                for city, _ in failed:
                    fallback_rows.append(recursive_ml_forecast(history_by_city[city], city, models_by_city[city]))
                live = pd.concat([live, *fallback_rows], ignore_index=True)
            live["date"] = pd.to_datetime(live["date"]).dt.strftime("%Y-%m-%d")
            return live

    # When a packaged forecast has become stale or API calls fail, create a fresh ML-only outlook.
    fallback_rows = []
    for city in CITIES:
        fallback_rows.append(recursive_ml_forecast(history_by_city[city], city, models_by_city[city]))
    fallback = pd.concat(fallback_rows, ignore_index=True)
    # Preserve an explicit fallback source so users don't confuse it with a meteorological forecast.
    fallback["forecast_source"] = "ML recursive fallback (demo)"
    return fallback


def ensure_history(refresh: bool = False) -> pd.DataFrame:
    """Load packaged data or fetch historical data, falling back to synthetic demo data."""
    today = (pd.Timestamp.today().normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if refresh:
        fetched = []
        failed = []
        for city in CITIES:
            try:
                fetched.append(fetch_open_meteo_history(city, HISTORY_START, today))
                print(f"[history] Retrieved historical weather for {city}.")
            except Exception as exc:
                failed.append((city, str(exc)))
                print(f"[history] Live history unavailable for {city}: {exc}")
        if fetched:
            new_data = pd.concat(fetched, ignore_index=True)
            if failed:
                old = pd.read_csv(HISTORY_FILE) if HISTORY_FILE.exists() else pd.DataFrame()
                replacement = set(new_data["city"].unique())
                if not old.empty:
                    old["date"] = pd.to_datetime(old["date"]).dt.strftime("%Y-%m-%d")
                    new_data = pd.concat([new_data, old[~old["city"].isin(replacement)]], ignore_index=True)
            new_data.to_csv(HISTORY_FILE, index=False)
            return new_data

    if HISTORY_FILE.exists():
        history = pd.read_csv(HISTORY_FILE)
        if set(CITIES.keys()).issubset(set(history["city"].unique())):
            return history

    parts = [generate_synthetic_history(city) for city in CITIES]
    history = pd.concat(parts, ignore_index=True)
    history.to_csv(HISTORY_FILE, index=False)
    return history


def run_pipeline(refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Train the models and write all dashboard-ready CSV outputs."""
    history = ensure_history(refresh=refresh)
    history["date"] = pd.to_datetime(history["date"])
    history = history.sort_values(["city", "date"]).drop_duplicates(["city", "date"], keep="last")
    history_by_city = {city: history[history["city"] == city].copy() for city in CITIES}
    models_by_city, all_metrics, all_importance = {}, [], []

    for city, city_history in history_by_city.items():
        models, metrics, importance = train_city_models(city_history, city)
        models_by_city[city] = models
        all_metrics.extend(metrics)
        all_importance.extend(importance)
        print(f"[model] {city}: trained Tmax and Tmin forecasting models on {len(city_history):,} daily records.")

    pd.DataFrame(all_metrics).to_csv(METRICS_FILE, index=False)
    pd.DataFrame(all_importance).to_csv(FEATURE_IMPORTANCE_FILE, index=False)

    forecast_input = prepare_forecast_input(history_by_city, models_by_city, refresh=refresh)
    forecast_input["date"] = pd.to_datetime(forecast_input["date"])
    forecast_output = []
    for city in CITIES:
        city_history = history_by_city[city]
        city_forecast = forecast_input[forecast_input["city"] == city].copy()
        if city_forecast.empty:
            city_forecast = recursive_ml_forecast(city_history, city, models_by_city[city])
        # Keep a second, independent ML forecast for model transparency.
        ml_forecast = recursive_ml_forecast(city_history, city, models_by_city[city])[
            ["city", "date", "forecast_tmax_c", "forecast_tmin_c"]
        ].rename(columns={
            "forecast_tmax_c": "ml_pred_tmax_c",
            "forecast_tmin_c": "ml_pred_tmin_c",
        })
        ml_forecast["date"] = pd.to_datetime(ml_forecast["date"])
        city_forecast["date"] = pd.to_datetime(city_forecast["date"])
        city_forecast = city_forecast.merge(ml_forecast, on=["city", "date"], how="left")
        # forecast_tmax/tmin remain the provider or fallback values used by the risk layer.
        city_forecast["date"] = pd.to_datetime(city_forecast["date"])
        if "humidity_mean_pct" not in city_forecast:
            city_forecast["humidity_mean_pct"] = float(city_history["humidity_mean_pct"].tail(7).mean())
        city_forecast["humidity_mean_pct"] = city_forecast["humidity_mean_pct"].fillna(float(city_history["humidity_mean_pct"].tail(7).mean()))
        city_forecast["latitude"] = city_forecast.get("latitude", CITIES[city]["latitude"])
        city_forecast["longitude"] = city_forecast.get("longitude", CITIES[city]["longitude"])
        city_forecast["region_type"] = city_forecast.get("region_type", CITIES[city]["region_type"])
        if "forecast_source" not in city_forecast.columns:
            city_forecast["forecast_source"] = "ML recursive fallback (demo)"
        forecast_output.append(city_forecast)

    forecast = pd.concat(forecast_output, ignore_index=True)
    forecast_risk_parts = []
    historical_risk_parts = []
    for city in CITIES:
        city_history = history_by_city[city].copy()
        city_forecast = forecast[forecast["city"] == city].copy()
        historical_risk_parts.append(enrich_with_risk(city_history, city_history, is_forecast=False))
        forecast_risk_parts.append(enrich_with_risk(city_forecast, city_history, is_forecast=True))

    historical_risk = pd.concat(historical_risk_parts, ignore_index=True)
    forecast_results = pd.concat(forecast_risk_parts, ignore_index=True)
    # Add a persistence hint: count consecutive forecast risk days up to that date.
    forecast_results["consecutive_watch_days"] = 0
    for city in CITIES:
        indices = forecast_results.index[forecast_results["city"] == city].tolist()
        streak = 0
        for idx in indices:
            level = forecast_results.loc[idx, "risk_level"]
            if level in ("YELLOW", "ORANGE", "RED"):
                streak += 1
            else:
                streak = 0
            forecast_results.loc[idx, "consecutive_watch_days"] = streak
    alerts = forecast_results[forecast_results["risk_level"].isin(["YELLOW", "ORANGE", "RED"])].copy()

    # Convert dates to strings for consistent CSV parsing across platforms.
    for frame in (history, historical_risk, forecast_results, alerts):
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    history.to_csv(HISTORY_FILE, index=False)
    historical_risk.to_csv(HISTORICAL_RISK_FILE, index=False)
    forecast_results.to_csv(FORECAST_RESULTS_FILE, index=False)
    alerts.to_csv(ALERTS_FILE, index=False)

    # Summary of source types is helpful for transparent demo-vs-live labelling.
    sources = sorted(set(history.get("data_source", pd.Series(dtype=str)).astype(str)))
    print("\nClimate Intelligence pipeline completed.")
    print(f"  Historical daily rows : {len(history):,}")
    print(f"  Locations             : {history['city'].nunique()}")
    print(f"  Historical risk rows  : {len(historical_risk):,}")
    print(f"  Forecast rows         : {len(forecast_results):,}")
    print(f"  Forecast alerts       : {len(alerts):,}")
    print(f"  Data source(s)         : {', '.join(sources)}")
    print(f"  Model metrics          : {METRICS_FILE}")
    return {
        "history": history,
        "historical_risk": historical_risk,
        "forecast": forecast_results,
        "alerts": alerts,
        "metrics": pd.DataFrame(all_metrics),
    }
