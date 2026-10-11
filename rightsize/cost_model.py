"""Cost & Efficiency Modeling for AWS EC2 and Kubernetes Workloads.

Provides exact pricing calculations for AWS EC2 instance tiers (us-east-1)
and AWS EKS / Fargate container allocation models.
"""
from __future__ import annotations

from typing import Any, Dict


# AWS EC2 On-Demand Rates (us-east-1, Linux)
EC2_CATALOG = {
    "t3.medium": {
        "name": "t3.medium (Current Provision)",
        "vcpus": 2,
        "ram_gb": 4.0,
        "hourly_cost": 0.0416,
        "monthly_cost": 0.0416 * 730.0,  # $30.368
        "annual_cost": 0.0416 * 8760.0,   # $364.416
    },
    "t3.small": {
        "name": "t3.small (Recommended Right-Size)",
        "vcpus": 2,
        "ram_gb": 2.0,
        "hourly_cost": 0.0208,
        "monthly_cost": 0.0208 * 730.0,  # $15.184
        "annual_cost": 0.0208 * 8760.0,   # $182.208
    },
    "t3.micro": {
        "name": "t3.micro (Ultra-minimal)",
        "vcpus": 2,
        "ram_gb": 1.0,
        "hourly_cost": 0.0104,
        "monthly_cost": 0.0104 * 730.0,  # $7.592
        "annual_cost": 0.0104 * 8760.0,   # $91.104
    },
    "t4g.small": {
        "name": "t4g.small (Graviton2 ARM)",
        "vcpus": 2,
        "ram_gb": 2.0,
        "hourly_cost": 0.0168,
        "monthly_cost": 0.0168 * 730.0,  # $12.264
        "annual_cost": 0.0168 * 8760.0,   # $147.168
    },
}

# AWS Fargate Compute Pricing (us-east-1)
FARGATE_VCPU_HOURLY = 0.04048
FARGATE_GB_HOURLY = 0.004445
HOURS_PER_MONTH = 730.0


def calculate_ec2_savings(
    current_instance: str = "t3.medium",
    target_instance: str = "t3.small",
) -> Dict[str, Any]:
    """Calculate EC2 instance level right-sizing cost reduction."""
    cur = EC2_CATALOG.get(current_instance, EC2_CATALOG["t3.medium"])
    target = EC2_CATALOG.get(target_instance, EC2_CATALOG["t3.small"])

    monthly_savings = cur["monthly_cost"] - target["monthly_cost"]
    annual_savings = cur["annual_cost"] - target["annual_cost"]
    savings_pct = (monthly_savings / cur["monthly_cost"]) * 100.0

    return {
        "current_instance": cur["name"],
        "target_instance": target["name"],
        "current_monthly_cost": round(cur["monthly_cost"], 2),
        "target_monthly_cost": round(target["monthly_cost"], 2),
        "monthly_savings": round(monthly_savings, 2),
        "annual_savings": round(annual_savings, 2),
        "savings_percent": round(savings_pct, 1),
        "ram_saving_gb": round(cur["ram_gb"] - target["ram_gb"], 1),
    }


def calculate_container_savings(
    current_cpu_req_m: float = 600.0,
    current_mem_req_mb: float = 1024.0,
    target_cpu_req_m: float = 150.0,
    target_mem_req_mb: float = 416.0,
) -> Dict[str, Any]:
    """Calculate container compute cost under AWS Fargate / EKS pricing model."""
    cur_vcpu = current_cpu_req_m / 1000.0
    cur_gb = current_mem_req_mb / 1024.0
    cur_cpu_cost = cur_vcpu * FARGATE_VCPU_HOURLY * HOURS_PER_MONTH
    cur_mem_cost = cur_gb * FARGATE_GB_HOURLY * HOURS_PER_MONTH
    cur_total = cur_cpu_cost + cur_mem_cost

    target_vcpu = target_cpu_req_m / 1000.0
    target_gb = target_mem_req_mb / 1024.0
    target_cpu_cost = target_vcpu * FARGATE_VCPU_HOURLY * HOURS_PER_MONTH
    target_mem_cost = target_gb * FARGATE_GB_HOURLY * HOURS_PER_MONTH
    target_total = target_cpu_cost + target_mem_cost

    monthly_savings = cur_total - target_total
    savings_pct = (monthly_savings / cur_total * 100.0) if cur_total > 0 else 0.0

    return {
        "current_vcpu": cur_vcpu,
        "current_gb": round(cur_gb, 2),
        "current_monthly_cost": round(cur_total, 2),
        "target_vcpu": target_vcpu,
        "target_gb": round(target_gb, 2),
        "target_monthly_cost": round(target_total, 2),
        "monthly_savings": round(monthly_savings, 2),
        "savings_percent": round(savings_pct, 1),
    }


def generate_efficiency_summary(
    current_workload: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute before-and-after resource efficiency indicators."""
    cur_req_cpu = current_workload.get("total_req_cpu_m", 600.0)
    cur_limit_cpu = current_workload.get("total_limit_cpu_m", 2600.0)
    cur_req_mem = current_workload.get("total_req_mem_mb", 1024.0)
    cur_limit_mem = current_workload.get("total_limit_mem_mb", 2048.0)
    cur_pods_count = len(current_workload.get("pods", [])) or 6

    # Target Right-sized workload
    # 2 API pods (50m req, 250m lim, 160Mi req, 256Mi lim)
    # 2 Frontend pods (25m req, 150m lim, 48Mi req, 96Mi lim)
    target_req_cpu = 150.0
    target_limit_cpu = 800.0
    target_req_mem = 416.0
    target_limit_mem = 704.0
    target_pods_count = 4

    cpu_req_reduction_pct = ((cur_req_cpu - target_req_cpu) / cur_req_cpu * 100.0) if cur_req_cpu > 0 else 0.0
    cpu_limit_reduction_pct = ((cur_limit_cpu - target_limit_cpu) / cur_limit_cpu * 100.0) if cur_limit_cpu > 0 else 0.0
    mem_req_reduction_pct = ((cur_req_mem - target_req_mem) / cur_req_mem * 100.0) if cur_req_mem > 0 else 0.0
    mem_limit_reduction_pct = ((cur_limit_mem - target_limit_mem) / cur_limit_mem * 100.0) if cur_limit_mem > 0 else 0.0
    pod_reduction_pct = ((cur_pods_count - target_pods_count) / cur_pods_count * 100.0) if cur_pods_count > 0 else 0.0

    ec2_savings = calculate_ec2_savings("t3.medium", "t3.small")
    container_savings = calculate_container_savings(cur_req_cpu, cur_req_mem, target_req_cpu, target_req_mem)

    return {
        "current": {
            "pods_count": cur_pods_count,
            "req_cpu_m": cur_req_cpu,
            "limit_cpu_m": cur_limit_cpu,
            "req_mem_mb": cur_req_mem,
            "limit_mem_mb": cur_limit_mem,
            "node_cpu_overcommit_pct": round((cur_limit_cpu / 2000.0) * 100.0, 1),
        },
        "target": {
            "pods_count": target_pods_count,
            "req_cpu_m": target_req_cpu,
            "limit_cpu_m": target_limit_cpu,
            "req_mem_mb": target_req_mem,
            "limit_mem_mb": target_limit_mem,
            "node_cpu_overcommit_pct": round((target_limit_cpu / 2000.0) * 100.0, 1),
        },
        "improvements": {
            "cpu_req_savings_pct": round(cpu_req_reduction_pct, 1),
            "cpu_limit_savings_pct": round(cpu_limit_reduction_pct, 1),
            "mem_req_savings_pct": round(mem_req_reduction_pct, 1),
            "mem_limit_savings_pct": round(mem_limit_reduction_pct, 1),
            "pod_reduction_pct": round(pod_reduction_pct, 1),
            "overcommit_resolved": cur_limit_cpu > 2000.0 and target_limit_cpu <= 2000.0,
        },
        "ec2_cost": ec2_savings,
        "container_cost": container_savings,
    }
