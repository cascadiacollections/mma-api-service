# Cloud Run setup

The deployment workflow publishes every `main` revision to GHCR. It deploys to
Cloud Run only when the required repository variables are configured, and then
only from a manual run on `main` until `CLOUD_RUN_AUTO_DEPLOY` is set to `true`.

The reviewed production configuration lives in
[`deploy/service.yaml`](../deploy/service.yaml): zero to three instances,
concurrency 80, one CPU, 512 MiB, a 30-second request timeout, request-based
CPU allocation with startup boost, a startup probe on `/api/ready`, and a
liveness probe on `/api/health`. The workflow fills in the image, service name,
runtime service account, and optional environment with
[`deploy/render-service.sh`](../deploy/render-service.sh) and applies it with
`gcloud run services replace`. Change scaling or resources in that file, not in
the Cloud Console, or the next deployment will revert the change.

> **Access is private by default.** A newly created service requires IAM
> authentication, and the deployment identity has no permission to change
> that. Making the service public is a separate owner decision; complete or
> explicitly accept the open items in [issue #3](https://github.com/cascadiacollections/mma-api-service/issues/3) (data licensing and legal review)
> first. See [Public access](#8-public-access-after-issue-3-review).

Every command below is run once by the owner. Nothing in this repository runs
`gcloud` against a project except the deployment workflow.

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
export BILLING_ACCOUNT="000000-000000-000000"   # gcloud billing accounts list

gcloud config set project "${PROJECT_ID}"
export PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
```

## 2. Enable APIs and create Artifact Registry

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  run.googleapis.com \
  sts.googleapis.com \
  billingbudgets.googleapis.com

gcloud artifacts repositories create "${GAR_REPOSITORY}" \
  --location "${REGION}" \
  --repository-format docker \
  --description "MMA service images"

# Keep the 10 newest images and delete anything older than 30 days.
gcloud artifacts repositories set-cleanup-policies "${GAR_REPOSITORY}" \
  --location "${REGION}" \
  --policy deploy/artifact-cleanup-policy.json \
  --no-dry-run
```

## 3. Create least-privilege service accounts

```bash
gcloud iam service-accounts create "${RUNTIME_SA}" \
  --display-name "MMA API Cloud Run runtime"

gcloud iam service-accounts create "${DEPLOY_SA}" \
  --display-name "MMA API GitHub deployer"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/run.developer"

gcloud artifacts repositories add-iam-policy-binding "${GAR_REPOSITORY}" \
  --location "${REGION}" \
  --member "serviceAccount:${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding \
  "${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --member "serviceAccount:${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/iam.serviceAccountUser"
```

The deployer can create and update Cloud Run services, act as the runtime
service account, and push to this one Artifact Registry repository. It holds
`roles/run.developer` rather than `roles/run.admin`, so it cannot change who may
invoke the service.

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

The `production` GitHub environment already exists. Restrict it to the `main`
branch and optionally require review before deployment:

```bash
gh api --method PUT repos/cascadiacollections/mma-api-service/environments/production \
  --input - <<'JSON'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
JSON
gh api --method POST \
  repos/cascadiacollections/mma-api-service/environments/production/deployment-branch-policies \
  -f name=main -f type=branch
```

None of these values are credentials. Never store a credential in a repository
variable; use Secret Manager as in step 6.

After a custom domain is serving the application, set its canonical origin:

```bash
gh variable set PUBLIC_BASE_URL \
  --repo cascadiacollections/mma-api-service \
  --body "https://picks.example.com"
```

Optional webmaster integration values can be configured after domain
verification is planned:

```bash
gh variable set GOOGLE_SITE_VERIFICATION \
  --repo cascadiacollections/mma-api-service \
  --body "google-verification-token"
gh variable set BING_SITE_VERIFICATION \
  --repo cascadiacollections/mma-api-service \
  --body "bing-verification-token"
gh variable set INDEXNOW_KEY \
  --repo cascadiacollections/mma-api-service \
  --body "random-indexnow-key"
```

DNS verification is preferred when available. See
[`seo-adsense.md`](seo-adsense.md) before enabling IndexNow or advertising.

## 6. Optional shared cache

The service defaults to a bounded process cache, which is usually sufficient
with the three-instance ceiling. For sustained multi-instance traffic, store a
Redis connection URL in Google Secret Manager. The deployment references the
secret by name; its value never passes through GitHub:

```bash
gcloud services enable secretmanager.googleapis.com

# Reads the URL from stdin so it does not land in shell history.
gcloud secrets create mma-redis-url --replication-policy automatic --data-file=-

gcloud secrets add-iam-policy-binding mma-redis-url \
  --member "serviceAccount:${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/secretmanager.secretAccessor"

gh variable set CLOUD_RUN_REDIS_URL_SECRET \
  --repo cascadiacollections/mma-api-service \
  --body "mma-redis-url"
```

The next deployment mounts it as `REDIS_URL`. Do not use
`gcloud run services update --set-secrets`; the next `services replace` would
remove it.

Prefer a TLS Redis endpoint. A private Memorystore instance additionally
requires VPC connectivity, which adds cost and operational complexity.

## 7. First deployment

Run the workflow manually on `main` and watch it:

```bash
gh workflow run deploy.yml --repo cascadiacollections/mma-api-service --ref main
gh run watch --repo cascadiacollections/mma-api-service \
  "$(gh run list --repo cascadiacollections/mma-api-service --workflow deploy.yml \
      --limit 1 --json databaseId --jq '.[0].databaseId')"
```

The service is private, so verify it with your own identity:

```bash
export SERVICE_URL="$(gcloud run services describe "${CLOUD_RUN_SERVICE}" \
  --region "${REGION}" --format 'value(status.url)')"
curl -fsS -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${SERVICE_URL}/api/ready"
```

Then open `/docs`, share a pick, and check grading through the same
authenticated route (for example `gcloud beta run services proxy "${CLOUD_RUN_SERVICE}"
--region "${REGION}"` and a browser on `http://localhost:8080`).

To deploy every merge to `main` automatically from then on:

```bash
gh variable set CLOUD_RUN_AUTO_DEPLOY --repo cascadiacollections/mma-api-service --body true
```

## 8. Public access (after issue #3 review)

[Issue #3](https://github.com/cascadiacollections/mma-api-service/issues/3) gates commercialization on data licensing and legal review. A public
service redistributes ESPN-derived event data to anyone, so review
[`legal-launch-checklist.md`](legal-launch-checklist.md) before this step, keep
the service free and non-commercial, and leave the AdSense variables unset
while #3 is open.

When you decide to open it:

```bash
gcloud run services add-iam-policy-binding "${CLOUD_RUN_SERVICE}" \
  --region "${REGION}" \
  --member allUsers \
  --role roles/run.invoker
```

An organization policy that restricts `allUsers` bindings (domain-restricted
sharing) blocks this; grant an exception for this project if so. To make the
service private again:

```bash
gcloud run services remove-iam-policy-binding "${CLOUD_RUN_SERVICE}" \
  --region "${REGION}" \
  --member allUsers \
  --role roles/run.invoker
```

## 9. Custom domain (optional)

Replace the placeholders. Verify ownership of the registered domain first:

```bash
export CUSTOM_DOMAIN="picks.example.com"

gcloud domains verify example.com

gcloud beta run domain-mappings create \
  --service "${CLOUD_RUN_SERVICE}" \
  --domain "${CUSTOM_DOMAIN}" \
  --region "${REGION}"

# Shows the DNS records to create at your DNS provider.
gcloud beta run domain-mappings describe \
  --domain "${CUSTOM_DOMAIN}" \
  --region "${REGION}"
```

Cloud Run domain mappings are in preview and only available in some regions.
If the region does not support them, put a global external Application Load
Balancer with a serverless network endpoint group, or Firebase Hosting, in
front of the service instead. Once the domain serves the app, set
`PUBLIC_BASE_URL` as in step 5 and redeploy.

## 10. Billing budget

Budgets notify; they do not stop spending.

```bash
gcloud billing budgets create \
  --billing-account "${BILLING_ACCOUNT}" \
  --display-name "mma-api-service" \
  --budget-amount 10USD \
  --filter-projects "projects/${PROJECT_ID}" \
  --threshold-rule percent=0.5 \
  --threshold-rule percent=0.9 \
  --threshold-rule percent=1.0
```

## Cost controls

- Keep minimum instances at zero until latency data justifies a warm instance.
- Keep the maximum instance count low (`maxScale` in `deploy/service.yaml`)
  and raise it only after observing load.
- Configure a Google Cloud budget and billing alerts; budgets notify but do not
  hard-stop spend.
- Put a CDN in front only after traffic measurements show meaningful origin
  egress or latency savings.

## Roll back

Cloud Run retains prior revisions. List them and move all traffic to a known
good revision without rebuilding:

```bash
gcloud run revisions list \
  --service "${CLOUD_RUN_SERVICE}" \
  --region "${REGION}"

gcloud run services update-traffic "${CLOUD_RUN_SERVICE}" \
  --region "${REGION}" \
  --to-revisions "REVISION_NAME=100"
```
