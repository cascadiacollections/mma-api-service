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

container-build:
    docker build --tag mma-api-service:local .

container-run:
    docker run --rm --publish 8080:8080 --env-file .env mma-api-service:local
