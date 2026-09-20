# Cloud Run setup

The deployment workflow publishes every `main` revision to GHCR. It deploys to
Cloud Run only when the required repository variables are configured.

## 1. Define local values

```bash
export PROJECT_ID="your-project-id"
export REGION="us-west1"
export GAR_REPOSITORY="mma-services"
export CLOUD_RUN_SERVICE="mma-api-service"
export RUNTIME_SA="mma-api-runtime"
export DEPLOY_SA="mma-api-deployer"
export WIF_POOL="github"
export WIF_PROVIDER="mma-api-service"

gcloud config set project "${PROJECT_ID}"
export PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
```

## 2. Enable APIs and create Artifact Registry

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  run.googleapis.com \
  sts.googleapis.com

gcloud artifacts repositories create "${GAR_REPOSITORY}" \
  --location "${REGION}" \
  --repository-format docker \
  --description "MMA service images"
```

## 3. Create least-privilege service accounts

```bash
gcloud iam service-accounts create "${RUNTIME_SA}" \
  --display-name "MMA API Cloud Run runtime"

gcloud iam service-accounts create "${DEPLOY_SA}" \
  --display-name "MMA API GitHub deployer"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/run.admin"

gcloud artifacts repositories add-iam-policy-binding "${GAR_REPOSITORY}" \
  --location "${REGION}" \
  --member "serviceAccount:${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding \
  "${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --member "serviceAccount:${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/iam.serviceAccountUser"
```

The runtime service account intentionally needs no project-wide role for the
default public-upstream and in-memory-cache configuration.

## 4. Configure GitHub workload identity federation

```bash
gcloud iam workload-identity-pools create "${WIF_POOL}" \
  --location global \
  --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "${WIF_PROVIDER}" \
  --location global \
  --workload-identity-pool "${WIF_POOL}" \
  --display-name "mma-api-service GitHub Actions" \
  --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition "assertion.repository=='cascadiacollections/mma-api-service'"

gcloud iam service-accounts add-iam-policy-binding \
  "${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/iam.workloadIdentityUser" \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/cascadiacollections/mma-api-service"

export PROVIDER_RESOURCE="$(
  gcloud iam workload-identity-pools providers describe "${WIF_PROVIDER}" \
    --location global \
    --workload-identity-pool "${WIF_POOL}" \
    --format 'value(name)'
)"
```

No downloadable Google service-account key is created or stored.

## 5. Configure repository variables

Run these commands while authenticated to GitHub:

```bash
gh variable set GCP_PROJECT_ID --repo cascadiacollections/mma-api-service --body "${PROJECT_ID}"
gh variable set GCP_REGION --repo cascadiacollections/mma-api-service --body "${REGION}"
gh variable set GAR_REPOSITORY --repo cascadiacollections/mma-api-service --body "${GAR_REPOSITORY}"
gh variable set CLOUD_RUN_SERVICE --repo cascadiacollections/mma-api-service --body "${CLOUD_RUN_SERVICE}"
gh variable set CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT \
  --repo cascadiacollections/mma-api-service \
  --body "${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER \
  --repo cascadiacollections/mma-api-service \
  --body "${PROVIDER_RESOURCE}"
gh variable set GCP_DEPLOY_SERVICE_ACCOUNT \
  --repo cascadiacollections/mma-api-service \
  --body "${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
```

Create a protected GitHub environment named `production` and optionally require
review before deployment.

## 6. Optional shared cache

The service defaults to a bounded process cache, which is usually sufficient
with the three-instance ceiling. For sustained multi-instance traffic, store a
Redis connection URL in Google Secret Manager and expose it as `REDIS_URL`:

```bash
printf '%s' 'rediss://example' | gcloud secrets create mma-redis-url --data-file=-

gcloud secrets add-iam-policy-binding mma-redis-url \
  --member "serviceAccount:${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/secretmanager.secretAccessor"

gcloud run services update "${CLOUD_RUN_SERVICE}" \
  --region "${REGION}" \
  --set-secrets "REDIS_URL=mma-redis-url:latest"
```

Prefer a TLS Redis endpoint. A private Memorystore instance additionally
requires VPC connectivity, which adds cost and operational complexity.

## Cost controls

- Keep minimum instances at zero until latency data justifies a warm instance.
- Keep the maximum instance count low and raise it only after observing load.
- Configure a Google Cloud budget and billing alerts; budgets notify but do not
  hard-stop spend.
- Put a CDN in front only after traffic measurements show meaningful origin
  egress or latency savings.
