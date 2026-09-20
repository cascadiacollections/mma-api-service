import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import Bout, Event, EventSummary, Fighter


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client


def make_completed_event() -> Event:
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


async def test_health_and_security_headers(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "revision": "development"}
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert "googlesyndication" not in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


async def test_homepage_uses_neutral_branding_and_disclosure(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert '<span class="brand-badge">MMA</span>' in response.text
    assert "<h1>Pick'em</h1>" in response.text
    assert "Not affiliated with or endorsed by UFC" in response.text
    assert "<h1>UFC Pick'em</h1>" not in response.text
    assert '<link rel="canonical" href="http://test">' in response.text
    assert 'id="theme-select"' in response.text
    assert 'href="/static/themes.css"' in response.text


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        ("/terms", "Terms of use"),
        ("/privacy", "Privacy notice"),
        ("/data-policy", "Event data policy"),
        ("/about", "About MMA Pick'em"),
    ],
)
async def test_legal_documents_are_public(
    client: AsyncClient,
    path: str,
    heading: str,
) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text
    assert response.headers["cache-control"] == "public, max-age=3600"


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
        return make_completed_event()

    monkeypatch.setattr("app.main.get_event", completed_event)
    response = await client.get("/api/events/600000001")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600, s-maxage=86400"


async def test_robots_and_sitemap_use_public_origin(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def event_summaries(*_args) -> list[EventSummary]:
        return [make_completed_event()]

    monkeypatch.setattr("app.main.list_events", event_summaries)
    robots = await client.get("/robots.txt")
    sitemap = await client.get("/sitemap.xml")

    assert robots.status_code == 200
    assert "Allow: /" in robots.text
    assert "Disallow: /api/" not in robots.text
    assert "Sitemap: http://test/sitemap.xml" in robots.text
    assert sitemap.status_code == 200
    assert "<loc>http://test/about</loc>" in sitemap.text
    assert "<loc>http://test/events/600000001</loc>" in sitemap.text


async def test_event_page_is_crawlable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def completed_event(_: str) -> Event:
        return make_completed_event()

    monkeypatch.setattr("app.main.get_event", completed_event)
    response = await client.get("/events/600000001")

    assert response.status_code == 200
    assert '<link rel="canonical" href="http://test/events/600000001">' in response.text
    assert '<script type="application/ld+json"' in response.text
    assert "Winner (10" not in response.text
    assert "Winner" in response.text
    assert "Opponent" in response.text


async def test_advertising_is_disabled_by_default(client: AsyncClient) -> None:
    homepage = await client.get("/")
    ads_txt = await client.get("/ads.txt")

    assert "pagead2.googlesyndication.com" not in homepage.text
    assert 'id="ad-slot"' not in homepage.text
    assert ads_txt.status_code == 404
