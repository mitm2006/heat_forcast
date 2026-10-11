"""Non-invasive Performance Benchmarker for Climate Intelligence Workload.

Measures throughput (RPS), latency percentiles (P50, P90, P95, P99),
and error rates across analytical and frontend endpoints without modifying
any cluster or host configuration.
"""
from __future__ import annotations

import concurrent.futures
import statistics
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional


TEST_ENDPOINTS = [
    {"name": "Frontend Health", "url": "http://localhost:30080/health", "weight": 2},
    {"name": "Frontend Web UI", "url": "http://localhost:30080/", "weight": 2},
    {"name": "API Status", "url": "http://localhost:30080/api/status", "weight": 1},
    {"name": "API Cities", "url": "http://localhost:30080/api/cities", "weight": 1},
    {"name": "API Summary (Delhi)", "url": "http://localhost:30080/api/summary?city=Delhi", "weight": 3},
    {"name": "API Alerts (Delhi)", "url": "http://localhost:30080/api/alerts?city=Delhi", "weight": 2},
    {"name": "API Forecast (Delhi)", "url": "http://localhost:30080/api/forecast?city=Delhi", "weight": 2},
    {"name": "API City Peaks", "url": "http://localhost:30080/api/city-peaks", "weight": 1},
]


def _make_request(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Execute a single HTTP GET request and record latency in ms."""
    t0 = time.perf_counter()
    status_code = 0
    success = False
    error_msg = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Climate-Rightsize-Benchmark/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            success = 200 <= status_code < 400
            # Read small payload
            _ = resp.read(8192)
    except urllib.error.HTTPError as e:
        status_code = e.code
        error_msg = f"HTTP {e.code}"
    except Exception as e:
        error_msg = str(e)
    t1 = time.perf_counter()
    latency_ms = (t1 - t0) * 1000.0

    return {
        "url": url,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "success": success,
        "error": error_msg,
    }


def run_benchmark(
    total_requests: int = 150,
    concurrency: int = 10,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """Execute concurrent benchmark across all endpoints."""
    # Build list of URLs respecting weights
    url_pool: List[Dict[str, str]] = []
    for ep in TEST_ENDPOINTS:
        for _ in range(ep["weight"]):
            url_pool.append({"name": ep["name"], "url": ep["url"]})

    request_targets = []
    for i in range(total_requests):
        target = url_pool[i % len(url_pool)]
        request_targets.append(target)

    results: List[Dict[str, Any]] = []
    start_time = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_make_request, t["url"]): t["name"]
            for t in request_targets
        }
        completed = 0
        for fut in concurrent.futures.as_completed(futures):
            ep_name = futures[fut]
            res = fut.result()
            res["endpoint_name"] = ep_name
            results.append(res)
            completed += 1
            if progress_callback:
                progress_callback(completed, total_requests)

    total_time = time.perf_counter() - start_time

    # Calculate statistics
    latencies = [r["latency_ms"] for r in results]
    successes = sum(1 for r in results if r["success"])
    failures = len(results) - successes

    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)

    def percentile(p: float) -> float:
        if not latencies_sorted:
            return 0.0
        k = (len(latencies_sorted) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(latencies_sorted) - 1)
        d = k - f
        return latencies_sorted[f] * (1.0 - d) + latencies_sorted[c] * d

    p50 = percentile(50)
    p90 = percentile(90)
    p95 = percentile(95)
    p99 = percentile(99)
    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
    mean_lat = statistics.mean(latencies) if latencies else 0.0
    throughput = len(results) / total_time if total_time > 0 else 0.0

    # Per-endpoint breakdown
    per_endpoint = {}
    for r in results:
        name = r["endpoint_name"]
        if name not in per_endpoint:
            per_endpoint[name] = []
        per_endpoint[name].append(r["latency_ms"])

    endpoint_stats = {}
    for name, lats in per_endpoint.items():
        endpoint_stats[name] = {
            "count": len(lats),
            "mean_ms": round(statistics.mean(lats), 2),
            "p50_ms": round(statistics.median(lats), 2),
            "p95_ms": round(sorted(lats)[int((len(lats) - 1) * 0.95)], 2) if lats else 0.0,
            "min_ms": round(min(lats), 2),
            "max_ms": round(max(lats), 2),
        }

    return {
        "total_requests": len(results),
        "concurrency": concurrency,
        "duration_seconds": round(total_time, 2),
        "throughput_rps": round(throughput, 1),
        "success_rate_pct": round((successes / len(results) * 100.0) if results else 0.0, 1),
        "failures": failures,
        "latency_min_ms": round(min_lat, 2),
        "latency_mean_ms": round(mean_lat, 2),
        "latency_p50_ms": round(p50, 2),
        "latency_p90_ms": round(p90, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
        "latency_max_ms": round(max_lat, 2),
        "endpoint_stats": endpoint_stats,
    }
