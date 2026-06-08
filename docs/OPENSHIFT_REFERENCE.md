# OpenShift Reference

OpenShift-specific concepts learned during ARO deployment. For cluster creation, see [AZURE_REFERENCE.md](AZURE_REFERENCE.md).

**Live Demo**: https://demo-perf-rating.apps.vbj6calm.eastus.aroapp.io/

---

## OpenShift vs Kubernetes

| Aspect | Kubernetes | OpenShift |
|--------|------------|-----------|
| CLI | `kubectl` | `oc` (superset of kubectl) |
| Namespaces | Namespaces | Projects (with RBAC) |
| Ingress | Ingress + Controller + cert-manager | Routes (built-in, one command) |
| Image builds | External CI/CD | S2I (built-in) |
| Security | Opt-in | Secure by default (SCC) |
| Console | Dashboard (optional) | Built-in web console |

---

## Source-to-Image (S2I)

Build container images from source code without a Dockerfile.

### How It Works

```
Git Repo ─────▶ S2I Build ─────▶ Container Image
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
 Fetch          Assemble         Push
 source      (pip install,     (to internal
              custom steps)      registry)
```

### Deploy with S2I

```bash
# Syntax: builder-image~git-repo
oc new-app python:3.11-ubi9~https://github.com/user/repo.git \
  --name=myapp \
  --env=DEMO_MODE=true

# Watch build
oc logs -f bc/myapp
```

**Builder Images**: OpenShift provides pre-built images in ImageStreams:
- `python:3.11-ubi9`, `python:3.9-ubi8`
- `nodejs:18-ubi8`, `nodejs:16-ubi8`
- `java:11`, `java:17`

List available: `oc get imagestreams -n openshift`

### Test Without Git Push

```bash
oc start-build myapp --from-dir=. --follow
```

Uploads local files directly—great for rapid iteration.

---

## Configuring Apps for S2I

S2I ignores your Dockerfile. Configure via `.s2i/` directory.

### `.s2i/environment`

Environment variables for build and runtime:

```bash
# Python: Gunicorn configuration
APP_MODULE=app:app              # Flask callable
APP_CONFIG=gunicorn.conf.py     # Config file
```

### `.s2i/bin/assemble`

Custom build steps (runs after default assemble):

```bash
#!/bin/bash
set -e

# Run default assemble first
/usr/libexec/s2i/assemble

# Add custom steps
python3 scripts/setup_data.py
```

### `.s2i/bin/run`

Custom run command (replaces default):

```bash
#!/bin/bash
exec gunicorn app:app --bind 0.0.0.0:8080
```

**Port 8080**: OpenShift expects containers to listen on 8080 by default.

---

## Routes

OpenShift's built-in ingress. One resource replaces Ingress + Controller + cert-manager.

### URL Anatomy

Route URLs follow a predictable pattern:

```
https://<route-name>-<project-name>.apps.<cluster-domain>
        └────┬─────┘ └─────┬──────┘     └──────┬───────┘
         you control   you control      cluster assigns
```

Example: `https://demo-perf-rating.apps.vbj6calm.eastus.aroapp.io`
- Route name: `demo`
- Project name: `perf-rating`
- Cluster domain: `vbj6calm.eastus.aroapp.io`

### Create Route

```bash
oc expose svc/myapp                    # Route inherits service name
oc expose svc/myapp --name=demo        # Explicit route name (recommended)
oc get route demo                      # Get URL
```

**Always use explicit `--name`** to control your URL. Without it, the route inherits the service name, which can cause awkward URLs like `myapp-v2-refactored-myproject.apps...`

### Naming Best Practices

| Resource | Naming Strategy | Example |
|----------|-----------------|---------|
| **Project** | App/product name (self-documenting in `oc get projects`) | `perf-rating` |
| **Service** | App name or component | `perf-rating` |
| **Route** | Environment or purpose | `demo`, `staging`, `prod`, `api` |

This gives clean, predictable URLs:
- `demo-perf-rating.apps...` (demo instance)
- `prod-perf-rating.apps...` (production)
- `api-perf-rating.apps...` (API endpoint)

### Multiple Routes to One Service

A single service can have multiple routes for different purposes:

```bash
# Public demo
oc expose svc/myapp --name=demo

# Internal testing (different URL, same backend)
oc expose svc/myapp --name=internal
```

### Change a Route

Routes can't be renamed. Delete and recreate:

```bash
oc delete route old-name
oc expose svc/myapp --name=new-name
oc patch route new-name -p '{"spec":{"tls":{"termination":"edge","insecureEdgeTerminationPolicy":"Redirect"}}}'
```

### TLS Termination

| Strategy | TLS Ends At | Use Case |
|----------|-------------|----------|
| **Edge** | Router | Most common—app serves HTTP |
| **Passthrough** | App | App needs client certs or SNI |
| **Reencrypt** | Both | High security—encrypted inside cluster |

```bash
# Enable edge TLS with HTTP→HTTPS redirect
oc patch route myapp -p '{"spec":{"tls":{"termination":"edge","insecureEdgeTerminationPolicy":"Redirect"}}}'
```

OpenShift uses its wildcard certificate (`*.apps.cluster.domain`) automatically.

---

## Projects

OpenShift's enhanced namespaces with built-in RBAC.

### Resource Hierarchy

```
CLUSTER (vbj6calm.eastus.aroapp.io)
│
├── PROJECT: perf-rating         ◄── isolation boundary
│   │
│   ├── Deployment: perf-rating  ◄── manages pods
│   │       │
│   │       └── Pods (replicas)
│   │
│   ├── Service: perf-rating     ◄── internal networking
│   │       internal: perf-rating.perf-rating.svc:8080
│   │
│   └── Route: demo                   ◄── external URL
│           external: demo-perf-rating.apps...
│
├── PROJECT: another-app
│   └── ...
│
└── PROJECT: openshift-*              ◄── system projects
    └── (monitoring, console, router, etc.)
```

### What Each Resource Does

| Resource | Scope | Purpose |
|----------|-------|---------|
| **Project** | Cluster-wide unique | Isolation, RBAC, quotas |
| **Deployment** | Unique within project | Runs and scales containers |
| **Service** | Unique within project | Internal cluster DNS |
| **Route** | Unique within project | External URL |

### Project Commands

```bash
oc new-project myproject       # Create and switch to it
oc project myproject           # Switch context
oc projects                    # List all you have access to
oc delete project myproject    # Delete (and ALL resources in it)
```

### Multi-Project Patterns

| Pattern | Example Projects | Use Case |
|---------|------------------|----------|
| **By environment** | `dev`, `staging`, `prod` | Same app, different lifecycles |
| **By app** | `perf-rating`, `inventory` | Clear `oc get projects` output |
| **By team** | `team-a`, `team-b` | Multi-tenant clusters |

**Tip**: A cluster can have many projects at no extra cost—projects are just logical isolation.

---

## BuildConfigs

Manage S2I build configuration.

```bash
oc get bc                          # List BuildConfigs
oc start-build myapp               # Trigger build
oc start-build myapp --from-dir=.  # Build from local
oc logs -f bc/myapp                # Follow build logs
oc logs build/myapp-3              # Specific build
```

### Webhooks

BuildConfigs have webhook URLs for GitHub/GitLab integration:

```bash
oc describe bc/myapp | grep -A2 "Webhook"
```

**Note**: ARO webhook endpoints require authentication and may return 403 for external callers. Use GitHub Actions instead (see below).

---

## CI/CD with GitHub Actions

For ARO, GitHub Actions triggering `oc start-build` is more reliable than webhooks.

### Setup

1. **Create service account**:
```bash
oc create serviceaccount github-actions -n perf-rating
oc policy add-role-to-user edit system:serviceaccount:perf-rating:github-actions -n perf-rating
```

2. **Generate long-lived token** (1 year):
```bash
oc create token github-actions -n perf-rating --duration=8760h
```

3. **Set GitHub secrets**:
```bash
echo "https://api.<cluster>.aroapp.io:6443" | gh secret set OPENSHIFT_SERVER -R owner/repo
oc create token github-actions -n perf-rating --duration=8760h | gh secret set OPENSHIFT_TOKEN -R owner/repo
```

### Workflow

`.github/workflows/deploy-openshift.yml`:
```yaml
name: Deploy to OpenShift

on:
  push:
    branches: [main]
    paths-ignore: ['**.md', 'docs/**']
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Install OpenShift CLI
        run: |
          curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
            | tar xz -C /usr/local/bin oc kubectl

      - name: Deploy
        run: |
          oc login --token=${{ secrets.OPENSHIFT_TOKEN }} --server=${{ secrets.OPENSHIFT_SERVER }}
          oc project perf-rating
          oc start-build perf-rating --follow
          oc rollout status deployment/perf-rating --timeout=120s
```

**Why direct curl instead of `redhat-actions/oc-installer@v1`**: The action depends on Node.js 20, which GitHub is deprecating. A direct download from the OpenShift mirror has no such dependency and no supply-chain risk from a third-party action.

### Flow

```
git push → GitHub Actions → oc login → oc start-build → S2I → auto-deploy
```

---

## Production Deployment Configuration

The live ARO deployment has additional hardening beyond what S2I creates by default. These are applied via `oc set` commands (not in the Git repo) and survive S2I rollouts because they modify the Deployment spec, not the container image.

### Environment Variables

```bash
oc set env deployment/perf-rating \
  DEMO_MODE=true \
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

`SECRET_KEY` is required for consistent Flask session cookies across Gunicorn workers. Without it, the app falls back to a dev-only key hardcoded in `app.py` — functional but publicly visible in the repo.

### Health Probes

```bash
oc set probe deployment/perf-rating \
  --liveness  --get-url=http://:8080/health --initial-delay-seconds=10 --period-seconds=30
oc set probe deployment/perf-rating \
  --readiness --get-url=http://:8080/health --initial-delay-seconds=5  --period-seconds=10
```

Without probes, OpenShift will not restart a deadlocked pod or remove it from the Service during startup.

### Resource Limits

```bash
oc set resources deployment/perf-rating \
  --requests=cpu=250m,memory=256Mi \
  --limits=cpu=500m,memory=512Mi
```

Required on shared clusters so the scheduler can place pods intelligently and a runaway process cannot starve other tenants.

### Verify Configuration

```bash
oc get deployment perf-rating -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
# Expected: DEMO_MODE SECRET_KEY

oc get deployment perf-rating -o jsonpath='{.spec.template.spec.containers[0].livenessProbe.httpGet.path}'
# Expected: /health

oc get deployment perf-rating -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'
# Expected: {"cpu":"250m","memory":"256Mi"}
```

**Important**: These settings live only in the Deployment object on the cluster. If the Deployment is deleted and recreated (e.g., `oc delete all -l app=perf-rating`), they must be reapplied.

---

## Security Context Constraints (SCC)

OpenShift blocks privileged containers by default.

```bash
oc get scc                         # List SCCs
oc describe scc restricted         # Default SCC
```

**Kubernetes** allows privileged pods by default (dangerous).
**OpenShift** blocks them unless explicitly allowed.

---

## Machine API & Scaling

OpenShift's Machine API bridges Kubernetes and cloud infrastructure.

### Architecture

```
MachineSet (desired state: N replicas)
    │
    └── Machine (represents one VM)
            │
            ├── Node (Kubernetes object)
            │
            └── Cloud VM (Azure, AWS, etc.)
```

### View Infrastructure

```bash
oc get machinesets -n openshift-machine-api     # Desired vs actual
oc get machines -n openshift-machine-api        # Individual VMs
oc get nodes                                     # Kubernetes view
```

### Scale Workers

ARO creates one MachineSet per availability zone. Scale them individually:

```bash
# List machinesets
oc get machinesets -n openshift-machine-api

# Scale one AZ to 0 (reduce workers)
oc scale machineset <name> -n openshift-machine-api --replicas=0

# Scale back up
oc scale machineset <name> -n openshift-machine-api --replicas=1
```

**Minimum ARO**: 3 masters (fixed) + 2 workers. Cannot go below 2 workers.

### Node Draining Process

When scaling down, OpenShift gracefully removes nodes:

```
1. CORDON    → Mark node SchedulingDisabled (no new pods)
2. DRAIN     → Evict pods (respects PodDisruptionBudgets)
3. DELETE    → Remove Node object from cluster
4. TERMINATE → Delete VM in cloud provider
```

**What happens to pods:**

| Replicas | PDB | Behavior |
|----------|-----|----------|
| 1 | None | Brief downtime during reschedule |
| 2+ | None | One pod always running |
| Any | `minAvailable: 1` | Drain waits for replacement pod |

### Machine Health Checks

OpenShift auto-replaces unhealthy nodes:

```bash
oc get machinehealthcheck -n openshift-machine-api
```

When a node fails health checks, the Machine is deleted and MachineSet creates a replacement.

---

## Debugging

```bash
oc logs <pod>                      # View logs
oc logs -f <pod>                   # Follow logs
oc rsh <pod>                       # Shell into pod
oc describe pod <pod>              # Details + events
oc debug deployment/myapp          # Start debug container
oc get events --sort-by='.lastTimestamp'
```

---

## oc vs kubectl

`oc` is a superset of `kubectl`. All kubectl commands work:

```bash
oc get pods          # Same as kubectl get pods
oc apply -f file.yaml
oc delete -f file.yaml
```

Plus OpenShift-specific:

```bash
oc new-project       # Create project with RBAC
oc new-app           # Deploy from image or source
oc expose            # Create route
oc start-build       # Trigger S2I build
oc rsh               # Remote shell (vs exec -it)
```

---

## Quick Reference

```bash
# Projects
oc new-project NAME
oc project NAME
oc projects

# Deploy
oc new-app IMAGE~GIT --name=NAME
oc new-app IMAGE --name=NAME

# Routes
oc expose svc/SERVICE --name=ROUTE   # Explicit name (recommended)
oc expose svc/NAME                    # Route inherits service name
oc get routes
oc patch route NAME -p '{"spec":{"tls":{"termination":"edge","insecureEdgeTerminationPolicy":"Redirect"}}}'

# Builds
oc start-build NAME
oc start-build NAME --from-dir=.
oc logs -f bc/NAME

# Debug
oc logs POD
oc rsh POD
oc describe pod POD
oc debug deployment/NAME

# Cleanup
oc delete all -l app=NAME             # Delete app resources
oc delete imagestream NAME            # Delete ImageStream too
oc delete project NAME                # Delete entire project
```

---

## S2I vs Alternatives

| Feature | S2I | Cloud Native Buildpacks | Dockerfile |
|---------|-----|------------------------|------------|
| Dockerfile needed | No | No | Yes |
| Customization | `.s2i/` scripts | Buildpack order | Full control |
| Layer caching | No (full rebuild) | Yes | Yes |
| Runtime | OpenShift only | Any | Any |
| Learning curve | Low | Medium | Low |

---

## App Cleanup

When `oc new-app` fails or you need to start over, OpenShift labels all resources with `app=<name>`:

```bash
# Delete all resources for an app
oc delete all -l app=myapp

# Also delete the ImageStream
oc delete imagestream myapp

# Verify cleanup
oc get all
```

To delete an entire project (and everything in it):

```bash
oc delete project myproject
```

---

## Gotchas

| Issue | Cause | Solution |
|-------|-------|----------|
| `python:3.11` not found | Need full tag | Use `python:3.11-ubi9` |
| App on wrong port | OpenShift expects 8080 | Set `bind = "0.0.0.0:8080"` |
| 503 Service Unavailable | App binding to localhost | Set `APP_MODULE` in `.s2i/environment` |
| HTTPS not working | Route has no TLS | Enable edge termination |
| Build steps missing | S2I ignores Dockerfile | Add `.s2i/bin/assemble` |
| URL has duplicate names | Route inherited service name | Use `oc expose --name=demo` |
| `oc get projects` unclear | Generic project names | Name projects after the app |

---

## Related Documentation

- [AZURE_REFERENCE.md](AZURE_REFERENCE.md) — ARO cluster creation
- [KUBERNETES_REFERENCE.md](KUBERNETES_REFERENCE.md) — K8s concepts (also work in OpenShift)
