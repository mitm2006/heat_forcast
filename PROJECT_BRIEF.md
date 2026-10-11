# Project Brief: Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning

## Abstract

Heatwaves create risks for public health, outdoor workers, energy demand, transport, and vulnerable communities. This project prototypes a climate-intelligence workflow that monitors daily temperature patterns, predicts upcoming maximum and minimum temperatures, compares forecasts with local seasonal normals, and produces explainable heat-risk signals. A Random Forest regression model is trained on lagged temperature and seasonal features. A Streamlit dashboard visualises historical trends, model performance, forecast departures, risk levels, and city comparisons. The current package includes clearly labelled synthetic data for offline demonstration and supports refreshing historical/forecast data from Open-Meteo when internet access is available.

## Problem statement

Raw temperature tables are difficult to interpret as a forward-looking risk picture. Users need to see not only a predicted temperature, but whether it is unusual for the location and whether it crosses a risk threshold. A useful monitoring prototype should combine historical context, short-term prediction, transparent alert rules, and a dashboard that makes the reasoning visible.

## Aim

To develop a data-driven climate-intelligence prototype that analyses temperature records, predicts daily temperatures, and displays transparent heat-risk alerts for selected Indian cities.

## Objectives

1. Prepare daily maximum/minimum temperature, humidity, and precipitation records.
2. Discover seasonal patterns and identify historical days meeting the project's heat-risk rules.
3. Train and evaluate Random Forest regressors for daily maximum and minimum temperature.
4. Calculate forecast temperature departures from a smoothed day-of-year normal.
5. Generate risk levels and human-readable explanations from temperature, anomaly, region type, and humidity.
6. Build an interactive dashboard with city filtering, model metrics, forecast comparison, risk history, downloads, and what-if scenario testing.
7. Clearly distinguish synthetic demo data, weather-provider forecasts, model predictions, and official warning services.

## Methodology

1. **Data acquisition:** load bundled synthetic records or request historical and forecast records from Open-Meteo.
2. **Preprocessing:** normalise daily dates, aggregate hourly variables, inspect the daily series, and calculate a smoothed climatological Tmax normal.
3. **Feature engineering:** create 1-, 2-, 3-, 7-, and 14-day maximum-temperature lags; minimum-temperature lags; rolling means; and cyclical seasonal features.
4. **Model training:** fit separate Random Forest models for maximum and minimum temperature for each city. Hold out the latest 20% of supervised rows chronologically for evaluation.
5. **Risk assessment:** calculate departure from normal and apply explainable project-specific thresholds, with different base criteria for the configured coastal location.
6. **Visualisation:** present historical trend, forecast versus ML prediction, model evaluation, seasonal distribution, risk levels, city comparison, and CSV downloads.
7. **Scenario analysis:** increase the forecast Tmax by a user-controlled amount to test how the risk rules respond. Scenario results are marked as simulated.

## Technology stack

- Python
- Pandas and NumPy
- scikit-learn (Random Forest regression)
- Joblib
- Requests and Open-Meteo APIs
- Streamlit
- Plotly

## Expected outputs

- Daily temperature dataset for five configured cities
- City-wise maximum/minimum temperature model metrics (MAE, RMSE, R²)
- Historical risk table with local normal, anomaly, risk label, and reason
- Seven-day forecast table with provider forecast, independent ML forecast, and risk score
- Alert CSV containing non-green forecast days
- Interactive dashboard and what-if scenario control

## Evaluation plan

Model performance is reported with MAE, RMSE, and R² using a chronological holdout rather than a random split. Risk rules are covered by automated sanity tests. The dashboard should be checked for consistent source labels and should never describe synthetic data or scenario output as observed weather or an official warning. Final research evaluation should use real observed temperatures and assess forecasting errors against dates not used for training.

## Limitations and ethics

- Bundled data is synthetic and only validates the workflow. Its model scores are not evidence of real-world forecast accuracy.
- The recursive ML fallback can drift over multi-day horizons and is not a replacement for a numerical weather prediction model.
- The risk score is a project-specific heuristic, not a validated medical heat index.
- Official heatwave declarations require operational procedures and context beyond a single model output. This prototype is not an official warning service.
- Avoid exposing personal or sensitive data. If expanded to neighbourhood-level vulnerability, use aggregated and ethically governed data.

## Future scope

- Evaluate models on verified station observations and official IMD bulletins.
- Add probabilistic or ensemble forecasts and prediction intervals.
- Include apparent temperature/heat index only with a documented, validated method.
- Add persistence-aware alert logic and calibrated city-specific thresholds.
- Connect alert delivery to email/SMS only after safety, validation, and false-alarm procedures are defined.
- Extend beyond the five configured cities and support district-level monitoring with appropriate official data.
