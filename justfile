set dotenv-load

default:
    @just --list

setup:
    uv sync --frozen

dev:
    uv run uvicorn app.main:app --reload

format:
    uv run ruff format .

lint:
    uv run ruff format --check .
    uv run ruff check .

test:
    uv run pytest

check: lint test
    node --test tests/picks.test.js
    node --check app/static/app.js
    node --check app/static/theme.js

indexnow:
    uv run python scripts/submit_indexnow.py

audit:
    uv export --frozen --no-dev --format requirements-txt --no-hashes | uvx --from pip-audit pip-audit -r /dev/stdin

deploy-render:
    IMAGE=example-docker.pkg.dev/project/repo/mma-api-service:local \
    CLOUD_RUN_SERVICE=mma-api-service \
    CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT=runtime@project.iam.gserviceaccount.com \
    BUILD_SHA=local \
    deploy/render-service.sh

container-build:
    docker build --tag mma-api-service:local .

container-run:
    #!/usr/bin/env bash
    set -euo pipefail
    env_args=()
    if [[ -f .env ]]; then
      env_args+=(--env-file .env)
    fi
    docker run --rm --publish 8080:8080 "${env_args[@]}" mma-api-service:local
