# GitOps Repository

Kubernetes manifests for deploying the application via Argo CD.

## Structure

charts/
├── backend/          # Go API backend (Helm chart)
│   ├── values.yaml        # Defaults
│   ├── values-test.yaml   # Test cluster overrides
│   └── values-prod.yaml   # Production cluster overrides
└── frontend/         # React web frontend (Helm chart)
├── values.yaml        # Defaults
├── values-test.yaml   # Test cluster overrides
└── values-prod.yaml   # Production cluster overrides
platform/
└── observability/    # Umbrella chart: kube-prometheus-stack + ESO wiring
├── Chart.yaml         # Pins the kube-prometheus-stack dependency (OCI)
├── values.yaml        # Shared values
├── values-test.yaml   # Test sizing/retention + optional Slack/ingress blocks
├── values-prod.yaml   # Prod sizing/retention + optional Slack/ingress blocks
├── dashboards/        # Grafana dashboard JSON (provisioned via ConfigMap)
└── templates/         # ClusterSecretStore, ExternalSecrets, StorageClass, alerts
argocd/               # Argo CD Application manifests
├── backend-test.yaml
├── backend-prod.yaml
├── frontend-test.yaml
├── frontend-prod.yaml
├── platform-observability-test.yaml
└── platform-observability-prod.yaml

## How Deployments Work

### Test Environment
Automated. When the CI pipeline in the app-repo merges to `main`, it builds new
container images and updates the image tags in `values-test.yaml`. Argo CD
auto-syncs the test cluster.

### Production Environment
Manual. Use the "Promote to Production" workflow in the app-repo to update
`values-prod.yaml` with a tested image tag. Argo CD detects the change but
requires a manual sync in the Argo CD UI.

## Validating Changes Locally

```bash
helm template backend-test charts/backend \
  -f charts/backend/values.yaml \
  -f charts/backend/values-test.yaml

# Observability umbrella chart (fetch the pinned dependency first)
helm dependency build platform/observability
helm template obs platform/observability \
  -f platform/observability/values.yaml \
  -f platform/observability/values-test.yaml --include-crds
```

## Environments

| Environment | Backend Host             | Frontend Host            |
|-------------|--------------------------|--------------------------|
| Test        | api.test.<your-domain>   | app.test.<your-domain>   |
| Production  | api.<your-domain>        | app.<your-domain>        |