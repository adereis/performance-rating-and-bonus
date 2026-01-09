# Kubernetes Reference

Kubernetes concepts learned during AKS deployment. These apply to any Kubernetes cluster.

---

## Core Architecture

```
Deployment ──creates──▶ ReplicaSet ──manages──▶ Pods
     │                      │
     │                      └── Hash in pod name (e.g., 6497fc7d4c)
     └── Rollout creates new ReplicaSet, scales down old
```

**Pod Naming**: `deployment-name-replicaset-hash-pod-id`
```
perf-rating-6497fc7d4c-fth8t
     │           │        │
     │           │        └── Random suffix (unique per pod)
     │           └── ReplicaSet hash (from pod template)
     └── Deployment name
```

---

## Scaling

### Manual Scaling

```bash
kubectl scale deployment perf-rating --replicas=3
kubectl get pods -w                    # Watch pods come up
kubectl get endpoints perf-rating      # See pod IPs in service
```

### Session Affinity (Sticky Sessions)

**Problem**: Stateful apps break when requests hit different pods.

```bash
# Enable ClientIP affinity (1 hour timeout)
kubectl patch service perf-rating -p \
  '{"spec":{"sessionAffinity":"ClientIP","sessionAffinityConfig":{"clientIP":{"timeoutSeconds":3600}}}}'
```

| Affinity | Behavior |
|----------|----------|
| `None` (default) | Round-robin load balancing |
| `ClientIP` | Same client IP → same pod |

**Trade-offs**: Simple fix, but uneven load and breaks if pod restarts.

**Proper Solution**: External session store (Redis) or shared filesystem.

### Horizontal Pod Autoscaler (HPA)

```bash
kubectl autoscale deployment perf-rating --min=2 --max=10 --cpu-percent=80
kubectl get hpa
```

---

## Rolling Updates

### Default Strategy

```yaml
strategy:
  rollingUpdate:
    maxSurge: 25%        # Can create 1 extra pod
    maxUnavailable: 25%  # At most 1 pod down
```

### Commands

```bash
# Update image
kubectl set image deployment/perf-rating perf-rating=registry/image:v2

# Watch rollout
kubectl rollout status deployment/perf-rating

# History
kubectl rollout history deployment/perf-rating

# Rollback
kubectl rollout undo deployment/perf-rating
kubectl rollout undo deployment/perf-rating --to-revision=2
```

### Resource Deadlock

**Symptom**: Rolling update stuck, new pod in `Pending`.

**Cause**: `maxSurge` tries to create extra pod, but node has no capacity.

**Solutions**:
| Approach | Command |
|----------|---------|
| Scale down first | `kubectl scale deployment perf-rating --replicas=2` |
| Kill-first strategy | Set `maxSurge: 0, maxUnavailable: 1` |
| Add nodes | Scale node pool |

---

## Debugging

### Logs

```bash
kubectl logs <pod>                      # All logs
kubectl logs <pod> --tail=50            # Last 50 lines
kubectl logs <pod> -f                   # Follow (stream)
kubectl logs <pod> --previous           # Crashed container's logs
kubectl logs -l app=perf-rating         # All pods with label
kubectl logs -l app=perf-rating --prefix=true  # With pod name prefix
```

### Exec

```bash
kubectl exec -it <pod> -- /bin/bash     # Interactive shell
kubectl exec <pod> -- env | grep FLASK  # Single command
```

### Describe

```bash
kubectl describe pod <pod>              # Full details + events
kubectl describe pod <pod> | grep -A20 "^Events:"  # Just events
```

### Debug Containers

```bash
kubectl debug -it <pod> --image=busybox --target=perf-rating
```

**`--target` flag**: Shares PID namespace with target container (can see its processes with `ps aux`).

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Application error |
| 137 | SIGKILL (OOM or `kubectl delete pod`) |
| 143 | SIGTERM (graceful shutdown) |

### Debugging Flowchart

```
Pod not running?
├── Pending     → describe pod → check Events (Insufficient cpu/memory?)
├── CrashLoop   → logs --previous → see crash reason
└── Running but not Ready → describe pod → readiness probe failing
```

---

## ConfigMaps & Secrets

### Create

```bash
# ConfigMap (non-sensitive)
kubectl create configmap perf-rating-config \
  --from-literal=DEMO_MODE=true \
  --from-literal=FLASK_ENV=production

# Secret (sensitive)
kubectl create secret generic perf-rating-secrets \
  --from-literal=SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### Use in Deployment

```yaml
containers:
- name: app
  envFrom:                    # Load all keys as env vars
  - configMapRef:
      name: perf-rating-config
  - secretRef:
      name: perf-rating-secrets
```

Or selectively:
```yaml
env:
- name: MY_SECRET
  valueFrom:
    secretKeyRef:
      name: perf-rating-secrets
      key: SECRET_KEY
```

### View

```bash
kubectl get configmap perf-rating-config -o yaml
kubectl get secret perf-rating-secrets -o jsonpath='{.data.SECRET_KEY}' | base64 -d
```

**Note**: Secrets are base64-encoded, NOT encrypted. Use external secret managers for production.

---

## Ingress & TLS

### Concepts

| Resource | Layer | Features |
|----------|-------|----------|
| Service (LoadBalancer) | L4 (TCP) | One IP per service, no TLS termination |
| Ingress | L7 (HTTP) | Multiple services per IP, TLS, path routing |

### NGINX Ingress Controller

```bash
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace
```

### cert-manager (Automatic TLS)

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
```

**ClusterIssuer** for Let's Encrypt:
```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
    - http01:
        ingress:
          class: nginx
```

**Ingress with TLS**:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: perf-rating-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - your-domain.com
    secretName: perf-rating-tls
  rules:
  - host: your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: perf-rating
            port:
              number: 80
```

### Health Probe Path

Ingress controller has `/healthz` endpoint (bypasses routing). Azure LB needs this:
```bash
kubectl annotate svc ingress-nginx-controller -n ingress-nginx \
  service.beta.kubernetes.io/azure-load-balancer-health-probe-request-path="/healthz"
```

---

## CI/CD with GitHub Actions

### Workflow Pattern

```yaml
on:
  push:
    branches: [main]

jobs:
  deploy:
    steps:
    - uses: azure/login@v2
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}

    - name: Build image
      run: az acr build --registry $REGISTRY --image app:${{ github.sha }} .

    - name: Deploy
      run: |
        az aks get-credentials -g $RG -n $CLUSTER
        kubectl set image deployment/app app=$REGISTRY.azurecr.io/app:${{ github.sha }}
        kubectl rollout status deployment/app
```

### Credential Rotation

```bash
# Add new credential (old still works)
az ad sp credential reset --id <CLIENT_ID> --append --display-name "new-$(date +%Y%m%d)"

# Update GitHub secret
gh secret set AZURE_CREDENTIALS

# Delete old credential
az ad sp credential list --id <CLIENT_ID> --output table
az ad sp credential delete --id <CLIENT_ID> --key-id <OLD_KEY_ID>
```

---

## Resource Management

### Requests vs Limits

```yaml
resources:
  requests:      # Guaranteed minimum (scheduling)
    memory: "256Mi"
    cpu: "250m"
  limits:        # Maximum allowed (enforcement)
    memory: "512Mi"
    cpu: "500m"
```

### Probes

```yaml
livenessProbe:           # Restart if fails
  httpGet:
    path: /health
    port: 5000
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:          # Remove from LB if fails
  httpGet:
    path: /health
    port: 5000
```

### Resource Quotas

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ResourceQuota
metadata:
  name: demo-quota
spec:
  hard:
    requests.cpu: "2"
    requests.memory: 2Gi
    pods: "10"
EOF
```

---

## Node Maintenance

```bash
kubectl cordon <node>     # No new pods scheduled
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data  # Evict pods
kubectl uncordon <node>   # Allow scheduling again
```

---

## Twelve-Factor App Principles

| Factor | Principle | K8s Implementation |
|--------|-----------|-------------------|
| III. Config | Store config in environment | ConfigMaps, Secrets |
| VI. Processes | Stateless processes | No local state, external storage |
| VII. Port binding | Export via port | containerPort, Service |
| VIII. Concurrency | Scale via processes | replicas, HPA |
| IX. Disposability | Fast startup/shutdown | Probes, graceful termination |
| XI. Logs | Treat as streams | stdout → kubectl logs |

---

## Quick Reference

```bash
# View
kubectl get pods/svc/deploy/all
kubectl describe <resource> <name>
kubectl logs <pod> [-f] [--previous]

# Modify
kubectl apply -f <file>
kubectl delete -f <file>
kubectl scale deploy <name> --replicas=N
kubectl set image deploy/<name> <container>=<image>

# Debug
kubectl exec -it <pod> -- /bin/bash
kubectl debug -it <pod> --image=busybox
kubectl port-forward <pod> 8080:5000

# Rollout
kubectl rollout status/history/undo deploy/<name>
```
