# MMA Pick'em

A FastAPI-backed MMA pick'em web app currently covering UFC fight cards. It lets
users pick each bout winner, stores the picks in a shareable URL, and grades
completed cards into win/loss/pending/void results.

## Run locally

The repository includes a `mise.toml` for consistent Python, Node.js, and `uv`
versions:

```bash
mise install
```

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

With `just` installed:

```bash
just setup
just dev
just check
```

VS Code and compatible clients can instead reopen the repository in the
included devcontainer. It installs the locked environment automatically and
persists the `uv` download cache between rebuilds.

## API

- `GET /api/health`
- `GET /api/ready`
- `GET /api/events?start=YYYY-MM-DD&end=YYYY-MM-DD`
- `GET /api/events/{event_id}`
- `POST /api/events/{event_id}/grade`

Example grading request:

```json
{
  "picks": {
    "401905382": "4422355"
  }
}
```

Picks are packed as base-3 fighter choices and encoded with base64url in the
URL fragment. A typical payload requires roughly nine characters, including a
card fingerprint that prevents a changed lineup from silently remapping picks.
Fragments stay in the browser and are not sent in the page request. Previously
shared query-string, compact, and base64url JSON links remain supported. No
account, database, or server-side pick storage is required for the MVP.

The interface uses semantic tokens from `app/static/themes.css`. The compact
Classic theme is the default, and the Night theme demonstrates how additional
themes can be added without changing component layout. A user's theme choice is
stored only in browser local storage.

The ESPN integration lives behind the isolated
`app.providers.espn_mma` adapter. No suitable maintained package exposes the
same lightweight ESPN scoreboard contract without adding another hosted data
service or scraper. The adapter contains transport, validation, normalization,
and caching so the API layer remains replaceable when a licensed provider is
adopted.

Upstream requests are coalesced and cached according to event volatility:

- Event lists: 10 minutes
- Scheduled cards: 15 minutes
- Live cards: 15 seconds
- Completed cards: 24 hours, allowing eventual result corrections

GET responses also include matching browser/CDN cache directives. Sharing picks
does not call the API, and grading reuses the cached card whenever possible.

Set `REDIS_URL` to use a Redis-compatible shared cache across instances. If it
is unset, each process uses a bounded in-memory cache. A Redis outage is logged
and degrades to the process cache rather than interrupting picks.

## Containers

Build and run the same non-root image used in CI and production:

```bash
docker build -t mma-api-service:local .
docker run --rm -p 8080:8080 mma-api-service:local
```

The image exposes `/api/health` as its container health check and reads:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8080` | HTTP listener |
| `LOG_LEVEL` | `INFO` | Uvicorn log level |
| `PUBLIC_BASE_URL` | request origin | Canonical custom-domain URL |
| `GOOGLE_SITE_VERIFICATION` | unset | Optional Search Console meta token |
| `BING_SITE_VERIFICATION` | unset | Optional Bing Webmaster Tools meta token |
| `INDEXNOW_KEY` | unset | Optional IndexNow ownership key |
| `ADSENSE_PUBLISHER_ID` | unset | Optional `ca-pub-…` AdSense publisher ID |
| `ADSENSE_SLOT_ID` | unset | Optional responsive ad-unit slot ID |
| `REDIS_URL` | unset | Optional shared cache |

## Delivery

Pull requests run formatting, linting, tests, JavaScript syntax checks, an image
build, and a container smoke test. Merges to `main` always publish commit and
`latest` images to GHCR. Cloud Run deployment runs only after the Google Cloud
repository variables below are configured.

Configure the GitHub `production` environment with these repository variables:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `GAR_REPOSITORY`
- `CLOUD_RUN_SERVICE`
- `CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_DEPLOY_SERVICE_ACCOUNT`

The deployment identity should use GitHub OIDC workload identity federation;
no Google service-account key is required. The workflow deploys with zero
minimum instances, a three-instance ceiling, one CPU, 512 MiB memory, and
request-based CPU allocation. Configure `REDIS_URL` separately as a Cloud Run
secret only if shared caching is needed. See
[`docs/cloud-run.md`](docs/cloud-run.md) for the complete bootstrap procedure.

The service provides `robots.txt`, a dynamic `sitemap.xml`, crawlable event
pages, canonical links, social metadata, structured event data, optional
Google/Bing verification tags, IndexNow support, optional `ads.txt`, and an
AdSense loader that remains disabled by default. See
[`docs/seo-adsense.md`](docs/seo-adsense.md) for custom-domain, Search Console,
consent, content-quality, and AdSense setup.

## Test

```bash
uv run ruff check .
uv run pytest
```

## License and data

The application source is available under the [MIT License](LICENSE).

Event data is retrieved from ESPN's public UFC scoreboard feed. UFC, ESPN, and
fighter names and marks belong to their respective owners. This project is not
affiliated with or endorsed by UFC or ESPN. Deployments should retain the cache
policy and avoid unnecessary automated requests to the upstream service.

The application publishes user-facing
[Terms](app/static/terms.html), [Privacy](app/static/privacy.html), and
[Event Data Policy](app/static/data-policy.html) documents at `/terms`,
`/privacy`, and `/data-policy`. These notices do not grant a data license or
replace legal review.

Commercial launch, advertising, sponsorship, paid access, or prizes are gated
on replacing the undocumented feed with a licensed source or obtaining written
permission, reviewing branding, and receiving qualified legal approval for the
intended business model and jurisdictions. See the
[legal launch checklist](docs/legal-launch-checklist.md).
