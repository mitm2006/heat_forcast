# Climate Intelligence — Docker & Kubernetes Deployment Guide

This guide covers how to build, run, and scale the Climate Intelligence Heatwave Early Warning System using **Docker**, **Docker Compose**, and **Kubernetes**.

---

## Architecture Overview

The system consists of two containerized services:
1. **`climate-api` (FastAPI backend)**
   - Serves analytical endpoints (`/api/summary`, `/api/historical`, `/api/forecast`, `/api/alerts`, `/api/city-peaks`, `/api/metrics`).
   - Runs on port `8000` via Uvicorn.
   - Includes `/health` and `/healthz` endpoints for liveness & readiness probes.
2. **`climate-frontend` (Flask dashboard)**
   - Serves the interactive dark-mode dashboard with Leaflet OpenStreetMap risk maps and Plotly temperature charts.
   - Runs on port `5000`.
   - Built-in reverse proxy forwards `/api/*` to the FastAPI service (`API_HOST`), avoiding cross-origin issues in container clusters.

```
                    ┌───────────────────────────────┐
                    │  Browser / Ingress / Client   │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │   climate-frontend (:5000)    │
                    │   Flask Dashboard & Proxy     │
                    └───────────────┬───────────────┘
                                    │ (Internal Network / ClusterIP)
                    ┌───────────────▼───────────────┐
                    │      climate-api (:8000)      │
                    │      FastAPI & ML Engine      │
                    └───────────────────────────────┘
```

---

## 1. Quick Start with Docker Compose

The easiest way to run the entire system locally with one command:

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac/Linux) with Docker Compose installed.

### Run
```bash
# Build images and start all services in the background
docker compose up --build -d
```

### Access Services
- **Web Dashboard:** [http://localhost:5000](http://localhost:5000)
- **FastAPI Interactive Docs (Swagger):** [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
- **FastAPI Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
- **Frontend Health Check:** [http://localhost:5000/health](http://localhost:5000/health)

### View Logs
```bash
docker compose logs -f
```

### Stop Services
```bash
docker compose down
```

---

## 2. Building Docker Images Individually

If you want to build and run the images manually:

### Build Backend
```bash
docker build -t climate-intelligence-api:latest -f Dockerfile.api .
```

### Build Frontend
```bash
docker build -t climate-intelligence-frontend:latest -f Dockerfile.frontend .
```

### Run Containers on a Shared Network
```bash
# 1. Create a user-defined bridge network
docker network create climate-net

# 2. Run the FastAPI backend
docker run -d --name climate-api \
  --network climate-net \
  -p 8000:8000 \
  climate-intelligence-api:latest

# 3. Run the Flask dashboard
docker run -d --name climate-frontend \
  --network climate-net \
  -p 5000:5000 \
  -e API_HOST=http://climate-api:8000 \
  climate-intelligence-frontend:latest
```

---

## 3. Kubernetes Deployment

The project includes production-ready manifests in the `k8s/` folder:

| File | Purpose |
| :--- | :--- |
| [`k8s/namespace.yaml`](k8s/namespace.yaml) | Creates dedicated `climate-intelligence` namespace |
| [`k8s/configmap.yaml`](k8s/configmap.yaml) | Configures environment variables, timezone, and internal endpoints |
| [`k8s/api-deployment.yaml`](k8s/api-deployment.yaml) | 2-replica Deployment for FastAPI backend with rolling updates & health probes |
| [`k8s/api-service.yaml`](k8s/api-service.yaml) | Internal `ClusterIP` service on port 8000 |
| [`k8s/frontend-deployment.yaml`](k8s/frontend-deployment.yaml) | 2-replica Deployment for Flask frontend with rolling updates & health probes |
| [`k8s/frontend-service.yaml`](k8s/frontend-service.yaml) | `NodePort` service exposing dashboard on port 30080 |
| [`k8s/ingress.yaml`](k8s/ingress.yaml) | NGINX Ingress routing `/api` to backend and `/` to frontend |
| [`k8s/kustomization.yaml`](k8s/kustomization.yaml) | Bundles all resources for single-command deploy |

### Step 1: Build & Load Images (for local clusters like Minikube or Kind)

If using **Minikube**:
```bash
# Point docker CLI to Minikube's Docker daemon
minikube docker-env | Invoke-Expression  # (PowerShell)
# or: eval $(minikube docker-env)       # (Bash)

# Build directly inside Minikube
docker build -t climate-intelligence-api:latest -f Dockerfile.api .
docker build -t climate-intelligence-frontend:latest -f Dockerfile.frontend .
```

If using **Kind**:
```bash
docker build -t climate-intelligence-api:latest -f Dockerfile.api .
docker build -t climate-intelligence-frontend:latest -f Dockerfile.frontend .
kind load docker-image climate-intelligence-api:latest
kind load docker-image climate-intelligence-frontend:latest
```

### Step 2: Deploy to Kubernetes

Deploy all resources in a single command using Kustomize:
```bash
kubectl apply -k k8s/
```

### Step 3: Check Deployment Status
```bash
# Check all resources in the namespace
kubectl get all -n climate-intelligence

# Check pod logs
kubectl logs -l app=climate-api -n climate-intelligence -f
kubectl logs -l app=climate-frontend -n climate-intelligence -f
```

### Step 4: Access the Dashboard

- **Via NodePort (Minikube / Kind / Docker Desktop):**
  Open [http://localhost:30080](http://localhost:30080) (or run `minikube service climate-frontend-service -n climate-intelligence`).

- **Via Port-Forwarding (Universal):**
  ```bash
  kubectl port-forward svc/climate-frontend-service -n climate-intelligence 5000:5000
  ```
  Then visit [http://localhost:5000](http://localhost:5000).

- **Via Ingress:**
  If an NGINX Ingress controller is installed in your cluster, access via your ingress IP or hostname configured in `k8s/ingress.yaml`.

### Step 5: Teardown / Cleanup
```bash
kubectl delete -k k8s/
```

---

## 4. Environment Variables Reference

| Variable | Default | Service | Description |
| :--- | :--- | :--- | :--- |
| `API_HOST` | `http://localhost:8000` | Frontend | Target URL for the FastAPI backend service |
| `PORT` | `5000` | Frontend | Port for the Flask web server |
| `HOST` | `0.0.0.0` | Both | Network host interface binding |
| `TIMEZONE` | `Asia/Kolkata` | Both | System timezone context |
| `PYTHONUNBUFFERED` | `1` | Both | Ensures standard output is immediately flushed to container logs |
