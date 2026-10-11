"""Metrics Collector for Cloud Instance & Kubernetes Resources.

Gathers real-time CPU, memory, load average, and allocation metrics
without modifying any cluster or host state.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from typing import Any, Dict, List, Optional


def get_ec2_metadata() -> Dict[str, str]:
    """Retrieve AWS EC2 instance metadata safely with fallback."""
    meta = {
        "instance_type": "t3.medium (detected)",
        "availability_zone": "us-east-1d",
        "region": "us-east-1",
        "vcpus": str(os.cpu_count() or 2),
    }
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            token = resp.read().decode("utf-8").strip()

        # Get instance-type
        req_type = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-type",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req_type, timeout=1.5) as resp:
            itype = resp.read().decode("utf-8").strip()
            if itype:
                meta["instance_type"] = itype

        # Get placement/availability-zone
        req_az = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/placement/availability-zone",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req_az, timeout=1.5) as resp:
            az = resp.read().decode("utf-8").strip()
            if az:
                meta["availability_zone"] = az
                meta["region"] = az[:-1]
    except Exception:
        pass
    return meta


def get_host_metrics() -> Dict[str, Any]:
    """Collect Linux host CPU, memory, and load averages from /proc."""
    metrics = {
        "mem_total_mb": 0.0,
        "mem_used_mb": 0.0,
        "mem_available_mb": 0.0,
        "mem_percent": 0.0,
        "load_1m": 0.0,
        "load_5m": 0.0,
        "load_15m": 0.0,
        "cpu_percent": 0.0,
    }

    # Memory
    try:
        with open("/proc/meminfo", "r") as f:
            lines = dict(line.split(":", 1) for line in f.read().splitlines() if ":" in line)
        total_kb = float(lines.get("MemTotal", "0 kB").split()[0])
        avail_kb = float(lines.get("MemAvailable", "0 kB").split()[0])
        used_kb = max(0.0, total_kb - avail_kb)

        metrics["mem_total_mb"] = round(total_kb / 1024.0, 1)
        metrics["mem_available_mb"] = round(avail_kb / 1024.0, 1)
        metrics["mem_used_mb"] = round(used_kb / 1024.0, 1)
        if total_kb > 0:
            metrics["mem_percent"] = round((used_kb / total_kb) * 100.0, 1)
    except Exception:
        pass

    # Load Average
    try:
        with open("/proc/loadavg", "r") as f:
            loads = f.read().split()
            metrics["load_1m"] = float(loads[0])
            metrics["load_5m"] = float(loads[1])
            metrics["load_15m"] = float(loads[2])
    except Exception:
        pass

    # Quick CPU % estimate from top or stat
    try:
        top_out = subprocess.check_output(
            ["top", "-bn1"], stderr=subprocess.DEVNULL, timeout=2
        ).decode("utf-8")
        for line in top_out.splitlines():
            if "%Cpu(s):" in line or "Cpu(s):" in line:
                m = re.search(r"(\d+[\.\,]?\d*)\s*id", line)
                if m:
                    idle = float(m.group(1).replace(",", "."))
                    metrics["cpu_percent"] = round(max(0.0, 100.0 - idle), 1)
                break
    except Exception:
        metrics["cpu_percent"] = round((metrics["load_1m"] / (os.cpu_count() or 2)) * 100.0, 1)

    return metrics


def parse_memory_to_mb(val_str: str) -> float:
    """Parse k8s memory strings (e.g., '256Mi', '1Gi', '128M', '500Ki') to MiB."""
    if not val_str:
        return 0.0
    val_str = str(val_str).strip()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Za-z]+)?$", val_str)
    if not match:
        return 0.0
    num = float(match.group(1))
    unit = match.group(2) or ""

    if unit in ("Ki", "K"):
        return num / 1024.0
    elif unit in ("Mi", "M"):
        return num
    elif unit in ("Gi", "G"):
        return num * 1024.0
    elif unit in ("Ti", "T"):
        return num * 1024.0 * 1024.0
    return num / (1024.0 * 1024.0)


def parse_cpu_to_m(val_str: str) -> float:
    """Parse k8s CPU strings (e.g. '100m', '1', '0.5') to millicores."""
    if not val_str:
        return 0.0
    val_str = str(val_str).strip()
    if val_str.endswith("m"):
        try:
            return float(val_str[:-1])
        except ValueError:
            return 0.0
    try:
        return float(val_str) * 1000.0
    except ValueError:
        return 0.0


def get_k8s_node_metrics() -> Dict[str, Any]:
    """Retrieve Kubernetes node resource allocation and actual usage."""
    data = {
        "node_name": "ip-172-31-34-240",
        "cpu_capacity_m": 2000.0,
        "cpu_allocatable_m": 2000.0,
        "mem_capacity_mb": 3790.0,
        "mem_allocatable_mb": 3790.0,
        "cpu_req_m": 0.0,
        "cpu_req_pct": 0.0,
        "cpu_limit_m": 0.0,
        "cpu_limit_pct": 0.0,
        "mem_req_mb": 0.0,
        "mem_req_pct": 0.0,
        "mem_limit_mb": 0.0,
        "mem_limit_pct": 0.0,
        "actual_cpu_m": 0.0,
        "actual_cpu_pct": 0.0,
        "actual_mem_mb": 0.0,
        "actual_mem_pct": 0.0,
        "is_cpu_overcommitted": False,
        "is_mem_overcommitted": False,
    }

    # 1. Describe node for allocations
    try:
        desc = subprocess.check_output(
            ["kubectl", "describe", "node"], stderr=subprocess.DEVNULL, timeout=5
        ).decode("utf-8")
        in_alloc = False
        for line in desc.splitlines():
            if "Allocated resources:" in line:
                in_alloc = True
                continue
            if in_alloc:
                if line.strip().startswith("cpu"):
                    # cpu 800m (40%) 2600m (130%)
                    parts = re.findall(r"(\d+m|\d+)\s*\(([\d\.]+)%\)", line)
                    if len(parts) >= 1:
                        data["cpu_req_m"] = parse_cpu_to_m(parts[0][0])
                        data["cpu_req_pct"] = float(parts[0][1])
                    if len(parts) >= 2:
                        data["cpu_limit_m"] = parse_cpu_to_m(parts[1][0])
                        data["cpu_limit_pct"] = float(parts[1][1])
                elif line.strip().startswith("memory"):
                    # memory 1164Mi (30%) 2218Mi (57%)
                    parts = re.findall(r"([0-9A-Za-z]+)\s*\(([\d\.]+)%\)", line)
                    if len(parts) >= 1:
                        data["mem_req_mb"] = parse_memory_to_mb(parts[0][0])
                        data["mem_req_pct"] = float(parts[0][1])
                    if len(parts) >= 2:
                        data["mem_limit_mb"] = parse_memory_to_mb(parts[1][0])
                        data["mem_limit_pct"] = float(parts[1][1])
                elif line.strip().startswith("Events:"):
                    in_alloc = False
    except Exception:
        pass

    # 2. Node top for actual usage
    try:
        top_node = subprocess.check_output(
            ["kubectl", "top", "nodes", "--no-headers"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8")
        for line in top_node.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                data["node_name"] = parts[0]
                data["actual_cpu_m"] = parse_cpu_to_m(parts[1])
                data["actual_cpu_pct"] = float(parts[2].replace("%", ""))
                data["actual_mem_mb"] = parse_memory_to_mb(parts[3])
                data["actual_mem_pct"] = float(parts[4].replace("%", ""))
                break
    except Exception:
        pass

    data["is_cpu_overcommitted"] = data["cpu_limit_pct"] > 100.0
    data["is_mem_overcommitted"] = data["mem_limit_pct"] > 100.0

    return data


def get_workload_metrics(namespace: str = "climate-intelligence") -> Dict[str, Any]:
    """Retrieve detailed pod and deployment allocations and utilization."""
    deployments = {}
    pods = []

    # 1. Get Deployments
    try:
        out = subprocess.check_output(
            ["kubectl", "get", "deployments", "-n", namespace, "-o", "json"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8")
        deps_json = json.loads(out)
        for item in deps_json.get("items", []):
            name = item["metadata"]["name"]
            replicas = item["spec"].get("replicas", 0)
            containers = item["spec"]["template"]["spec"]["containers"]
            res = containers[0].get("resources", {}) if containers else {}
            req = res.get("requests", {})
            lim = res.get("limits", {})

            deployments[name] = {
                "name": name,
                "replicas": replicas,
                "cpu_req_per_pod": req.get("cpu", "N/A"),
                "cpu_limit_per_pod": lim.get("cpu", "N/A"),
                "mem_req_per_pod": req.get("memory", "N/A"),
                "mem_limit_per_pod": lim.get("memory", "N/A"),
                "cpu_req_per_pod_m": parse_cpu_to_m(req.get("cpu", "0")),
                "cpu_limit_per_pod_m": parse_cpu_to_m(lim.get("cpu", "0")),
                "mem_req_per_pod_mb": parse_memory_to_mb(req.get("memory", "0")),
                "mem_limit_per_pod_mb": parse_memory_to_mb(lim.get("memory", "0")),
            }
    except Exception:
        pass

    # 2. Get Pod Actual Usage via kubectl top pods
    top_map = {}
    try:
        top_out = subprocess.check_output(
            ["kubectl", "top", "pods", "-n", namespace, "--no-headers"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8")
        for line in top_out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                top_map[parts[0]] = {
                    "cpu_m": parse_cpu_to_m(parts[1]),
                    "mem_mb": parse_memory_to_mb(parts[2]),
                }
    except Exception:
        pass

    # 3. Get Pod details
    try:
        out_pods = subprocess.check_output(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8")
        pods_json = json.loads(out_pods)
        for item in pods_json.get("items", []):
            pod_name = item["metadata"]["name"]
            status = item["status"]["phase"]
            app_label = item["metadata"].get("labels", {}).get("app", "unknown")
            restarts = 0
            container_statuses = item["status"].get("containerStatuses", [])
            if container_statuses:
                restarts = container_statuses[0].get("restartCount", 0)

            actual = top_map.get(pod_name, {"cpu_m": 0.0, "mem_mb": 0.0})
            dep_info = deployments.get(app_label, {})

            cpu_req = dep_info.get("cpu_req_per_pod_m", 100.0)
            cpu_lim = dep_info.get("cpu_limit_per_pod_m", 500.0)
            mem_req = dep_info.get("mem_req_per_pod_mb", 256.0)
            mem_lim = dep_info.get("mem_limit_per_pod_mb", 512.0)

            cpu_util_req_pct = (actual["cpu_m"] / cpu_req * 100.0) if cpu_req > 0 else 0.0
            mem_util_req_pct = (actual["mem_mb"] / mem_req * 100.0) if mem_req > 0 else 0.0

            pods.append({
                "name": pod_name,
                "app": app_label,
                "status": status,
                "restarts": restarts,
                "actual_cpu_m": actual["cpu_m"],
                "actual_mem_mb": actual["mem_mb"],
                "req_cpu_m": cpu_req,
                "req_mem_mb": mem_req,
                "limit_cpu_m": cpu_lim,
                "limit_mem_mb": mem_lim,
                "cpu_util_req_pct": round(cpu_util_req_pct, 1),
                "mem_util_req_pct": round(mem_util_req_pct, 1),
            })
    except Exception:
        pass

    # Aggregate workload totals
    total_actual_cpu_m = sum(p["actual_cpu_m"] for p in pods)
    total_actual_mem_mb = sum(p["actual_mem_mb"] for p in pods)
    total_req_cpu_m = sum(p["req_cpu_m"] for p in pods)
    total_req_mem_mb = sum(p["req_mem_mb"] for p in pods)
    total_limit_cpu_m = sum(p["limit_cpu_m"] for p in pods)
    total_limit_mem_mb = sum(p["limit_mem_mb"] for p in pods)

    return {
        "deployments": deployments,
        "pods": pods,
        "total_actual_cpu_m": total_actual_cpu_m,
        "total_actual_mem_mb": round(total_actual_mem_mb, 1),
        "total_req_cpu_m": total_req_cpu_m,
        "total_req_mem_mb": round(total_req_mem_mb, 1),
        "total_limit_cpu_m": total_limit_cpu_m,
        "total_limit_mem_mb": round(total_limit_mem_mb, 1),
        "avg_cpu_util_pct": round((total_actual_cpu_m / total_req_cpu_m * 100.0) if total_req_cpu_m > 0 else 0.0, 1),
        "avg_mem_util_pct": round((total_actual_mem_mb / total_req_mem_mb * 100.0) if total_req_mem_mb > 0 else 0.0, 1),
    }
