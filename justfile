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

audit:
    uv export --frozen --no-dev --format requirements-txt --no-hashes | uvx --from pip-audit pip-audit -r /dev/stdin

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
