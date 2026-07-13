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
Manual, and pinned. The prod Applications in `argocd/` track an immutable
commit SHA — not `main` — so a manual sync can only ever deploy the exact
changeset a promotion PR showed. Promoting to prod is two PRs working
together:

1. Image promotion (unchanged): the "Promote to Production" workflow in the
   app-repo updates `values-prod.yaml` with a tested image tag.
2. Revision promotion: a one-line PR per app bumping `targetRevision` in
   `argocd/*-prod.yaml` to the new `main` SHA (the PR diff is the exact
   changeset going out). After merge, `kubectl apply` the changed manifest
   (Application objects are not themselves Argo-managed), then manual sync
   in the Argo CD UI. Rollback = revert the promotion PR and repeat.

Test keeps tracking `main` with auto-sync — that is what test is for.

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