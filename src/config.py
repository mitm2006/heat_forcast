"""Project configuration for Climate Intelligence: Heatwave Monitoring & Early Warning."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "outputs"

TIMEZONE = "Asia/Kolkata"
HISTORY_START = "2015-01-01"
FORECAST_DAYS = 7
RANDOM_STATE = 42

# The project supports a small set of Indian cities for a useful regional comparison.
# Threshold context is configurable by region type. Mumbai is treated as coastal.
CITIES = {
    "Pune": {
        "latitude": 18.5204,
        "longitude": 73.8567,
        "region_type": "plains",
        "state": "Maharashtra",
    },
    "Mumbai": {
        "latitude": 19.0760,
        "longitude": 72.8777,
        "region_type": "coastal",
        "state": "Maharashtra",
    },
    "Nagpur": {
        "latitude": 21.1458,
        "longitude": 79.0882,
        "region_type": "plains",
        "state": "Maharashtra",
    },
    "Delhi": {
        "latitude": 28.6139,
        "longitude": 77.2090,
        "region_type": "plains",
        "state": "Delhi",
    },
    "Ahmedabad": {
        "latitude": 23.0225,
        "longitude": 72.5714,
        "region_type": "plains",
        "state": "Gujarat",
    },
}

ALERT_ORDER = ["GREEN", "YELLOW", "ORANGE", "RED"]
ALERT_LABELS = {
    "GREEN": "Normal",
    "YELLOW": "Heat watch",
    "ORANGE": "High heat risk",
    "RED": "Extreme heat risk",
}
ALERT_COLORS = {
    "GREEN": "#16a34a",
    "YELLOW": "#eab308",
    "ORANGE": "#f97316",
    "RED": "#dc2626",
}

for directory in (DATA_DIR, MODEL_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
