# Deploying Climate Intelligence on AWS EC2 with Docker & Kubernetes

This guide walks you through launching an AWS EC2 instance and deploying the **Climate Intelligence Heatwave Early Warning System** using **Docker Compose** or **Kubernetes (K3s)** for a live demonstration.

---

## 1. Launch Your AWS EC2 Instance

### Recommended Instance Specifications
- **AMI:** Ubuntu 22.04 LTS or Ubuntu 24.04 LTS (64-bit x86)
- **Instance Type:** `t3.medium` (2 vCPU, 4 GiB RAM) — *Ideal for running both Kubernetes and Docker smoothly. `t3.small` can be used if running Docker Compose only.*
- **Storage:** 20 GiB gp3 EBS volume
- **Key Pair:** Select your existing `.pem` key pair (or create a new one).

### Configure Security Group (Firewall Rules)
In the EC2 Launch Wizard, create or edit a Security Group with the following **Inbound Rules**:

| Type | Port Range | Source | Purpose |
| :--- | :--- | :--- | :--- |
| **SSH** | `22` | `My IP` (or `0.0.0.0/0`) | SSH Terminal Access |
| **HTTP** | `80` | `0.0.0.0/0` | Kubernetes Ingress / Web traffic |
| **Custom TCP** | `5000` | `0.0.0.0/0` | Flask Dashboard (Docker Compose mode) |
| **Custom TCP** | `8000` | `0.0.0.0/0` | FastAPI Backend & Swagger API Docs |
| **Custom TCP** | `30080` | `0.0.0.0/0` | Kubernetes NodePort Dashboard |

Click **Launch Instance**. Note the **Public IPv4 address** of your instance once running.

---

## 2. Connect to Your EC2 Instance

From your local machine (PowerShell or Bash), connect via SSH:

```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2_PUBLIC_IP>
```
*(Replace `<EC2_PUBLIC_IP>` with your instance's actual IP address).*

---

## 3. Copy Project Code to EC2

### Option A: Via Git (Recommended)
If your project is pushed to a Git repository (GitHub/GitLab):
```bash
git clone <YOUR_REPOSITORY_URL>
cd climate_intelligence_heatwave
```

### Option B: Via `scp` from your local machine
From your Windows/Mac terminal:
```powershell
# From your local workspace directory
scp -i /path/to/your-key.pem -r . ubuntu@<EC2_PUBLIC_IP>:~/climate_intelligence_heatwave
```
Then on EC2:
```bash
cd ~/climate_intelligence_heatwave
```

---

## 4. Run the Automated Deployment Script

We have provided an automated deployment script [`deploy_ec2.sh`](deploy_ec2.sh) that:
1. Installs Docker and Docker Compose.
2. Installs K3s (certified lightweight Kubernetes).
3. Builds the container images (`climate-intelligence-api` and `climate-intelligence-frontend`).
4. Imports images into the Kubernetes cluster.
5. Deploys all Kubernetes manifests (`k8s/`).

Make the script executable and run it:

```bash
chmod +x deploy_ec2.sh
./deploy_ec2.sh
```

---

## 5. Live Demonstration URLs

Once the script finishes, your deployment is immediately accessible in your web browser:

### In Kubernetes (K3s) Mode:
- **Interactive Dashboard (NodePort):**
  `http://<EC2_PUBLIC_IP>:30080`
- **Interactive Dashboard (Ingress Port 80):**
  `http://<EC2_PUBLIC_IP>/`
- **Backend API Health Check:**
  `http://<EC2_PUBLIC_IP>:30080/health`

### In Docker Compose Mode (Alternative):
If you prefer running in Docker Compose instead of Kubernetes:
```bash
./deploy_ec2.sh docker
```
- **Interactive Dashboard:**
  `http://<EC2_PUBLIC_IP>:5000`
- **FastAPI Interactive Swagger Docs:**
  `http://<EC2_PUBLIC_IP>:8000/api/docs`
- **FastAPI Health Check:**
  `http://<EC2_PUBLIC_IP>:8000/health`

---

## 6. Verifying the Deployment During a Demo

Here are the key commands to show during your demonstration to prove both Docker and Kubernetes orchestration:

### 1. Show Kubernetes Cluster & Pods
```bash
# View running pods, services, and node ports
sudo k3s kubectl get all -n climate-intelligence
```
*Expected Output:*
```text
NAME                                    READY   STATUS    RESTARTS   AGE
pod/climate-api-xxxxxxxxx-xxxxx         1/1     Running   0          2m
pod/climate-api-xxxxxxxxx-xxxxx         1/1     Running   0          2m
pod/climate-frontend-xxxxxxxxx-xxxxx   1/1     Running   0          2m
pod/climate-frontend-xxxxxxxxx-xxxxx   1/1     Running   0          2m

NAME                               TYPE        CLUSTER-IP      PORT(S)
service/climate-api-service        ClusterIP   10.43.x.x       8000/TCP
service/climate-frontend-service   NodePort    10.43.x.x       5000:30080/TCP
```

### 2. Demonstrate Kubernetes Self-Healing & Scaling
Demonstrate zero-downtime scaling:
```bash
# Scale frontend pods from 2 to 4
sudo k3s kubectl scale deployment/climate-frontend -n climate-intelligence --replicas=4

# Check the new pods launching instantly
sudo k3s kubectl get pods -n climate-intelligence
```

Demonstrate self-healing (delete a pod and watch K8s recreate it immediately):
```bash
# Delete one API pod
sudo k3s kubectl delete pod -l app=climate-api -n climate-intelligence | head -n 1

# Show that Kubernetes instantly replaced it
sudo k3s kubectl get pods -n climate-intelligence
```

### 3. View Live Container Logs
```bash
# View backend API logs
sudo k3s kubectl logs -l app=climate-api -n climate-intelligence -f

# View frontend dashboard logs
sudo k3s kubectl logs -l app=climate-frontend -n climate-intelligence -f
```

---

## 7. Teardown / Cleanup After Demo

When you are finished with the demonstration:

```bash
# To tear down Kubernetes resources:
sudo k3s kubectl delete -k k8s/

# Or if running Docker Compose:
sudo docker compose down
```

Remember to **Stop** or **Terminate** your EC2 instance in the AWS Management Console to avoid unnecessary AWS cloud charges.
