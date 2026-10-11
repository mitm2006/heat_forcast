"""Train the temperature models and create dashboard-ready outputs.

Default: use the packaged dataset (or existing local CSVs), so it runs offline.
Live data refresh: python src/run_pipeline.py --refresh
"""
import argparse
from climate_pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Heatwave Climate Intelligence pipeline.")
    parser.add_argument(
        "--refresh", action="store_true",
        help="Fetch historical and forecast data from Open-Meteo. Requires internet access.",
    )
    args = parser.parse_args()
    run_pipeline(refresh=args.refresh)


if __name__ == "__main__":
    main()
