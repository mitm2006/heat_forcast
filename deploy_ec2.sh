#!/usr/bin/env bash
# ==============================================================================
# deploy_ec2.sh — Automated Setup for AWS EC2 (Docker & Kubernetes / K3s)
#
# This script sets up Docker, Docker Compose, and a lightweight Kubernetes
# cluster (K3s) on an AWS EC2 instance (Ubuntu 22.04/24.04 or Amazon Linux 2023),
# builds the container images, and deploys the Climate Intelligence Dashboard.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================================${NC}"
echo -e "${BLUE}  Climate Intelligence — EC2 Docker & Kubernetes Deployment Setup  ${NC}"
echo -e "${BLUE}==================================================================${NC}"

# Detect Public IP
PUBLIC_IP=$(curl -s http://checkip.amazonaws.com || curl -s https://ifconfig.me || echo "<EC2_PUBLIC_IP>")
echo -e "${GREEN}Detected Public IP: ${PUBLIC_IP}${NC}\n"

# ------------------------------------------------------------------------------
# 1. System Updates & Docker Installation
# ------------------------------------------------------------------------------
echo -e "${YELLOW}[1/5] Checking and Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "$ID" in
      ubuntu|debian)
        sudo apt-get update -y
        sudo apt-get install -y ca-certificates curl gnupg lsb-release
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo \
          "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
          $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update -y
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        ;;
      amzn)
        sudo dnf update -y || sudo yum update -y
        sudo dnf install -y docker || sudo yum install -y docker
        sudo systemctl enable --now docker
        ;;
      *)
        echo -e "${RED}Unsupported OS for auto-install. Please install Docker manually.${NC}"
        ;;
    esac
  fi
  sudo usermod -aG docker "$USER" || true
  sudo systemctl enable --now docker
  echo -e "${GREEN}Docker installed successfully.${NC}"
else
  echo -e "${GREEN}Docker is already installed.${NC}"
fi

# ------------------------------------------------------------------------------
# 2. Build Docker Images
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[2/5] Building Container Images...${NC}"
sudo docker build -t climate-intelligence-api:latest -f Dockerfile.api .
sudo docker build -t climate-intelligence-frontend:latest -f Dockerfile.frontend .
echo -e "${GREEN}Images built successfully:${NC}"
sudo docker images | grep climate-intelligence

# ------------------------------------------------------------------------------
# 3. Choose Deployment Mode (Docker Compose or Kubernetes)
# ------------------------------------------------------------------------------
MODE="${1:-all}"

if [[ "$MODE" == "docker" ]]; then
  echo -e "\n${YELLOW}[3/5] Starting services with Docker Compose...${NC}"
  sudo docker compose down --remove-orphans || true
  sudo docker compose up -d
  echo -e "${GREEN}Docker Compose services started successfully!${NC}"

  echo -e "\n${BLUE}==================================================================${NC}"
  echo -e "${GREEN}  DEPLOYMENT COMPLETE (Docker Compose Mode)${NC}"
  echo -e "${BLUE}==================================================================${NC}"
  echo -e "Dashboard URL:   ${YELLOW}http://${PUBLIC_IP}:5000${NC}"
  echo -e "API Docs (REST): ${YELLOW}http://${PUBLIC_IP}:8000/api/docs${NC}"
  echo -e "Health Check:    ${YELLOW}http://${PUBLIC_IP}:8000/health${NC}"
  exit 0
fi

# ------------------------------------------------------------------------------
# 4. Install K3s (Lightweight Kubernetes)
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[3/5] Setting up Kubernetes (K3s)...${NC}"
if ! command -v k3s &> /dev/null; then
  # Install K3s without Traefik to avoid port conflicts with direct ingress
  curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
  mkdir -p "$HOME/.kube"
  sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
  sudo chown -R "$USER:$USER" "$HOME/.kube"
  export KUBECONFIG="$HOME/.kube/config"
  echo "export KUBECONFIG=$HOME/.kube/config" >> "$HOME/.bashrc"
  echo -e "${GREEN}K3s Kubernetes cluster installed!${NC}"
else
  echo -e "${GREEN}K3s is already installed.${NC}"
fi

# Wait for node ready
echo "Waiting for Kubernetes node to become ready..."
sudo k3s kubectl wait --for=condition=Ready node --all --timeout=60s || true

# ------------------------------------------------------------------------------
# 5. Import Docker Images into K3s Containerd
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[4/5] Loading Docker images into Kubernetes (K3s)...${NC}"
sudo docker save climate-intelligence-api:latest | sudo k3s ctr images import -
sudo docker save climate-intelligence-frontend:latest | sudo k3s ctr images import -
echo -e "${GREEN}Images imported into Kubernetes containerd runtime.${NC}"

# ------------------------------------------------------------------------------
# 6. Deploy Manifests to Kubernetes
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[5/5] Deploying Kubernetes manifests (k8s/)...${NC}"
sudo k3s kubectl apply -k k8s/

echo "Waiting for deployments to roll out..."
sudo k3s kubectl rollout status deployment/climate-api -n climate-intelligence --timeout=90s || true
sudo k3s kubectl rollout status deployment/climate-frontend -n climate-intelligence --timeout=90s || true

echo -e "\n${BLUE}==================================================================${NC}"
echo -e "${GREEN}  DEPLOYMENT COMPLETE (Kubernetes / K3s Mode)${NC}"
echo -e "${BLUE}==================================================================${NC}"
echo -e "Kubernetes Pods & Services Status:"
sudo k3s kubectl get pods,svc -n climate-intelligence

echo -e "\n${GREEN}Access your live deployment:${NC}"
echo -e "• Web Dashboard (NodePort 30080): ${YELLOW}http://${PUBLIC_IP}:30080${NC}"
echo -e "• Web Dashboard (via Ingress/Port 80): ${YELLOW}http://${PUBLIC_IP}/${NC}"
echo -e "• API Health Check: ${YELLOW}http://${PUBLIC_IP}:30080/health${NC}"
echo -e "\n${BLUE}Helpful commands:${NC}"
echo -e "• Check Pods:   sudo k3s kubectl get pods -n climate-intelligence"
echo -e "• View API Log: sudo k3s kubectl logs -l app=climate-api -n climate-intelligence -f"
echo -e "• View UI Log:  sudo k3s kubectl logs -l app=climate-frontend -n climate-intelligence -f"
echo -e "• Teardown:     sudo k3s kubectl delete -k k8s/"
echo -e "${BLUE}==================================================================${NC}\n"
