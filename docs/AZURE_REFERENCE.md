# Azure Deployment Reference

Reference for deploying the Performance Rating System across three Azure environments.

| Environment | URL | Cost | Use Case |
|-------------|-----|------|----------|
| **VM** | perf-rating-demo.eastus.cloudapp.azure.com | ~$15/mo | Simple, full control |
| **AKS** | perf-rating-aks.eastus.cloudapp.azure.com | ~$35/mo | Kubernetes learning |
| **ARO** | demo-perf-rating.apps.vbj6calm.eastus.aroapp.io | ~$450/mo | Enterprise OpenShift |

---

## Prerequisites

```bash
# Install Azure CLI
sudo dnf install azure-cli

# Login
az login
az account list --output table
az account set --subscription "<name-or-id>"
```

---

## 1. VM Deployment (Resource Group: perf-rating-demo-rg)

### Create Resources

```bash
# Resource group
az group create --name perf-rating-demo-rg --location eastus

# VM with RHEL 9
az vm create \
  --resource-group perf-rating-demo-rg \
  --name perf-rating-vm \
  --image RedHat:RHEL:9_7:latest \
  --size Standard_B1ms \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard

# Open ports
az vm open-port -g perf-rating-demo-rg -n perf-rating-vm --port 80 --priority 1010
az vm open-port -g perf-rating-demo-rg -n perf-rating-vm --port 443 --priority 1020

# DNS label
az network public-ip update \
  -g perf-rating-demo-rg \
  -n perf-rating-vmPublicIP \
  --dns-name perf-rating-demo
```

### VM Setup (SSH)

```bash
ssh azureuser@perf-rating-demo.eastus.cloudapp.azure.com

# RHEL setup
sudo subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms
sudo dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
sudo dnf install -y podman-compose git nginx certbot python3-certbot-nginx

# Extend /home if needed
sudo lvextend -L +10G /dev/mapper/rootvg-homelv && sudo xfs_growfs /home

# Firewall
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --reload

# SELinux for nginx reverse proxy
sudo setsebool -P httpd_can_network_connect 1

# Clone and run
git clone https://github.com/adereis/performance-rating-and-bonus.git /opt/performance-rating
cd /opt/performance-rating
podman-compose -f docker-compose.demo.yml up -d --build

# HTTPS
sudo certbot --nginx -d perf-rating-demo.eastus.cloudapp.azure.com
```

### Podman Auto-Restart with Quadlets

```bash
# Create user-level Quadlet
mkdir -p ~/.config/containers/systemd

cat > ~/.config/containers/systemd/perf-rating.container << 'EOF'
[Unit]
Description=Performance Rating Demo App

[Container]
Image=localhost/performance-rating_app:latest
PublishPort=5000:5000
Environment=DEMO_MODE=true
Environment=SECRET_KEY=your-secret-key
Volume=perf-rating-sessions:/tmp/demo_sessions

[Service]
Restart=always

[Install]
WantedBy=default.target
EOF

# Enable user services on boot
sudo loginctl enable-linger azureuser

# Start
systemctl --user daemon-reload
systemctl --user start perf-rating.service
```

---

## 2. AKS Deployment (Resource Group: perf-rating-demo-rg)

### Create ACR and AKS

```bash
# Container registry
az acr create --name perfratingdemoacr --resource-group perf-rating-demo-rg --sku Basic

# Build image in cloud
az acr build --registry perfratingdemoacr --image performance-rating:v1 .

# AKS cluster
az aks create \
  --resource-group perf-rating-demo-rg \
  --name perf-rating-aks \
  --node-count 1 \
  --node-vm-size Standard_B2s \
  --attach-acr perfratingdemoacr \
  --generate-ssh-keys

# Connect kubectl
az aks get-credentials -g perf-rating-demo-rg -n perf-rating-aks
```

### Deploy Application

```bash
# Apply manifests
kubectl apply -f azure/k8s/deployment.yaml

# Create ConfigMap and Secret
kubectl create configmap perf-rating-config \
  --from-literal=DEMO_MODE=true \
  --from-literal=FLASK_ENV=production

kubectl create secret generic perf-rating-secrets \
  --from-literal=SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Ingress + TLS

```bash
# Install NGINX Ingress
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace

# CRITICAL: Fix Azure LB health probe
kubectl annotate svc ingress-nginx-controller -n ingress-nginx \
  service.beta.kubernetes.io/azure-load-balancer-health-probe-request-path="/healthz"

# DNS for ingress IP (find IP name in Azure Portal)
az network public-ip update \
  --resource-group MC_perf-rating-demo-rg_perf-rating-aks_eastus \
  --name kubernetes-<id> \
  --dns-name perf-rating-aks

# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
```

### CI/CD with GitHub Actions

```bash
# Create Service Principal
az ad sp create-for-rbac \
  --name "github-actions-perf-rating" \
  --role contributor \
  --scopes /subscriptions/<sub-id>/resourceGroups/perf-rating-demo-rg \
  --sdk-auth

# Store in GitHub Secrets as AZURE_CREDENTIALS
gh secret set AZURE_CREDENTIALS
```

---

## 3. ARO Deployment (Resource Group: areis-aro-lab-rg)

### Prerequisites

```bash
# Register providers
az provider register --namespace Microsoft.RedHatOpenShift
az provider register --namespace Microsoft.Compute
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.Authorization

# Get pull secret from: https://console.redhat.com/openshift/install/pull-secret
```

### Create VNet and Cluster

```bash
# Dedicated resource group
az group create --name areis-aro-lab-rg --location eastus

# VNet with /22 (ARO needs large subnets)
az network vnet create \
  --resource-group areis-aro-lab-rg \
  --name aro-vnet \
  --address-prefixes 10.0.0.0/22

# Subnets
az network vnet subnet create \
  --resource-group areis-aro-lab-rg \
  --vnet-name aro-vnet \
  --name master-subnet \
  --address-prefixes 10.0.0.0/23 \
  --service-endpoints Microsoft.ContainerRegistry

az network vnet subnet create \
  --resource-group areis-aro-lab-rg \
  --vnet-name aro-vnet \
  --name worker-subnet \
  --address-prefixes 10.0.2.0/23 \
  --service-endpoints Microsoft.ContainerRegistry

# Create cluster (30-45 min)
az aro create \
  --resource-group areis-aro-lab-rg \
  --name areis-aro-cluster \
  --vnet aro-vnet \
  --master-subnet master-subnet \
  --worker-subnet worker-subnet \
  --pull-secret @~/pull-secret.txt
```

### Access Cluster

```bash
# Console URL
az aro show -g areis-aro-lab-rg -n areis-aro-cluster --query consoleProfile.url -o tsv

# Credentials
az aro list-credentials -g areis-aro-lab-rg -n areis-aro-cluster

# API URL
az aro show -g areis-aro-lab-rg -n areis-aro-cluster --query apiserverProfile.url -o tsv

# Login
oc login <api-url> -u kubeadmin -p <password>
```

See [OPENSHIFT_REFERENCE.md](OPENSHIFT_REFERENCE.md) for S2I deployment.

### Minimize ARO Costs

ARO minimum: 3 masters (fixed) + 2 workers. Scale workers via Machine API:

```bash
# View machinesets (one per AZ)
oc get machinesets -n openshift-machine-api

# Scale one AZ to 0 (reduces workers from 3 to 2)
oc scale machineset <name>-worker-eastus3 -n openshift-machine-api --replicas=0
```

See [OPENSHIFT_REFERENCE.md](OPENSHIFT_REFERENCE.md#machine-api--scaling) for details on draining.

---

## Cleanup

```bash
# Stop VM (saves compute, keeps disk)
az vm deallocate -g perf-rating-demo-rg -n perf-rating-vm

# Delete AKS
az aks delete -g perf-rating-demo-rg -n perf-rating-aks --yes

# Delete ARO
az aro delete -g areis-aro-lab-rg -n areis-aro-cluster --yes

# Nuclear option - delete everything
az group delete --name perf-rating-demo-rg --yes --no-wait
az group delete --name areis-aro-lab-rg --yes --no-wait
```

---

## Azure Gotchas

| Issue | Cause | Solution |
|-------|-------|----------|
| VM 502 after reboot | Podman is daemonless | Use Quadlets for auto-restart |
| Ingress external timeout | Azure LB health probe returns 404 | Annotate with `/healthz` path |
| ACR name taken | Must be globally unique | Add random suffix |
| ARO slow to create | 6 VMs across 3 AZs | Normal, takes 30-45 min |
| `/home` too small on RHEL | Default 960MB | `lvextend` + `xfs_growfs` |

---

## Cost Summary

| Resource | Spec | Monthly Cost |
|----------|------|--------------|
| VM (B1ms) | 1 vCPU, 2GB RAM | ~$15 |
| ACR (Basic) | 10GB storage | ~$5 |
| AKS (1x B2s) | 2 vCPU, 4GB RAM | ~$30 |
| ARO (minimum) | 3 masters + 3 workers | ~$450 |

**Tip**: Deallocate VMs when not learning. Delete AKS/ARO when done.
