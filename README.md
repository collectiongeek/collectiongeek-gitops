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
argocd/               # Argo CD Application manifests
├── backend-test.yaml
├── backend-prod.yaml
├── frontend-test.yaml
└── frontend-prod.yaml

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
```

## Environments

| Environment | Backend Host             | Frontend Host            |
|-------------|--------------------------|--------------------------|
| Test        | api.test.<your-domain>   | app.test.<your-domain>   |
| Production  | api.<your-domain>        | app.<your-domain>        |