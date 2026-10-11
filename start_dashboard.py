#!/usr/bin/env python3
"""
start_dashboard.py — Launch both FastAPI (port 8000) and Flask (port 5000) servers.

Usage:
    python start_dashboard.py
"""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent

def main():
    print("\n  Climate Intelligence — Heatwave Dashboard")
    print("  ==========================================")
    print("  Starting FastAPI backend  → http://localhost:8000")
    print("  Starting Flask frontend   → http://localhost:5000")
    print("  API documentation         → http://localhost:8000/api/docs")
    print("  Press Ctrl+C to stop.\n")

    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dashboard.api:app", "--port", "8000", "--reload"],
        cwd=str(ROOT),
    )
    time.sleep(2)

    flask_proc = subprocess.Popen(
        [sys.executable, str(ROOT / "dashboard" / "server.py")],
        cwd=str(ROOT),
    )
    time.sleep(1)

    webbrowser.open("http://localhost:5000")

    try:
        api_proc.wait()
        flask_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        api_proc.terminate()
        flask_proc.terminate()

if __name__ == "__main__":
    main()
