import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import Bout, Event, Fighter


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client


async def test_health_and_security_headers(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "revision": "development"}
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_event_id_must_be_numeric(client: AsyncClient) -> None:
    response = await client.get("/api/events/not-an-event")

    assert response.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "start=2026-10-01&end=2026-09-01",
        "start=2025-01-01&end=2026-12-31",
    ],
)
async def test_rejects_invalid_event_windows(client: AsyncClient, query: str) -> None:
    response = await client.get(f"/api/events?{query}")

    assert response.status_code == 422


async def test_completed_event_has_cache_headers(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def completed_event(_: str) -> Event:
        return Event(
            id="600000001",
            name="UFC Test",
            date="2026-09-20T00:00:00Z",
            status="Final",
            completed=True,
            bout_count=1,
            bouts=[
                Bout(
                    id="401000001",
                    order=1,
                    status="Final",
                    completed=True,
                    fighters=[
                        Fighter(id="1", name="Winner"),
                        Fighter(id="2", name="Opponent"),
                    ],
                    winner_id="1",
                )
            ],
        )

    monkeypatch.setattr("app.main.get_event", completed_event)
    response = await client.get("/api/events/600000001")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600, s-maxage=86400"
