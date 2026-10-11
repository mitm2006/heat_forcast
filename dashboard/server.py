"""Flask frontend server — Climate Intelligence Heatwave Dashboard.

Serves the HTML/JS/CSS frontend. All data is fetched from the FastAPI backend.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import os
import requests
from flask import Flask, Response, render_template, request, send_from_directory

API_HOST = os.environ.get("API_HOST", "http://localhost:8000").rstrip("/")

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.route("/health")
@app.route("/healthz")
def health_check():
    """Health check endpoint for container and Kubernetes probes."""
    return {"status": "healthy", "service": "climate-frontend"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy_api(path):
    """Proxy API requests to the FastAPI backend service."""
    url = f"{API_HOST}/api/{path}"
    try:
        resp = requests.request(
            method=request.method,
            url=url,
            headers={key: value for (key, value) in request.headers if key.lower() not in ["host", "content-length"]},
            params=request.args,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30,
        )
        excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)
    except requests.exceptions.RequestException as e:
        return {"error": "API service unavailable", "details": str(e)}, 503


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ["true", "1"]
    app.run(host=host, port=port, debug=debug)
