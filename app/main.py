import os
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as ApiPath
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.grading import grade_picks
from app.models import Event, EventSummary, GradeReport, PickSubmission
from app.providers.espn_mma import (
    EspnMmaDataError,
    EspnMmaError,
    EspnMmaEventNotFoundError,
    EspnMmaTimeoutError,
    close,
    default_event_window,
    get_event,
    list_events,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
REVISION = os.getenv("K_REVISION") or os.getenv("BUILD_SHA") or "development"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
ADSENSE_PUBLISHER_ID = os.getenv("ADSENSE_PUBLISHER_ID", "")
ADSENSE_SLOT_ID = os.getenv("ADSENSE_SLOT_ID", "")
GOOGLE_SITE_VERIFICATION = os.getenv("GOOGLE_SITE_VERIFICATION", "")
BING_SITE_VERIFICATION = os.getenv("BING_SITE_VERIFICATION", "")
INDEXNOW_KEY = os.getenv("INDEXNOW_KEY", "")
ADSENSE_ID_PATTERN = re.compile(r"^ca-pub-\d{16}$")
ADSENSE_SLOT_PATTERN = re.compile(r"^\d{10}$")
SITE_VERIFICATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{6,200}$")
INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")

if PUBLIC_BASE_URL:
    public_url_parts = urlsplit(PUBLIC_BASE_URL)
    if public_url_parts.scheme not in {"http", "https"} or not public_url_parts.netloc:
        raise RuntimeError("PUBLIC_BASE_URL must be an absolute HTTP or HTTPS URL")
if ADSENSE_PUBLISHER_ID and not ADSENSE_ID_PATTERN.fullmatch(ADSENSE_PUBLISHER_ID):
    raise RuntimeError("ADSENSE_PUBLISHER_ID must match ca-pub- followed by 16 digits")
if ADSENSE_SLOT_ID and not ADSENSE_SLOT_PATTERN.fullmatch(ADSENSE_SLOT_ID):
    raise RuntimeError("ADSENSE_SLOT_ID must contain exactly 10 digits")
if ADSENSE_SLOT_ID and not ADSENSE_PUBLISHER_ID:
    raise RuntimeError("ADSENSE_SLOT_ID requires ADSENSE_PUBLISHER_ID")
if GOOGLE_SITE_VERIFICATION and not SITE_VERIFICATION_PATTERN.fullmatch(GOOGLE_SITE_VERIFICATION):
    raise RuntimeError("GOOGLE_SITE_VERIFICATION contains unsupported characters")
if BING_SITE_VERIFICATION and not SITE_VERIFICATION_PATTERN.fullmatch(BING_SITE_VERIFICATION):
    raise RuntimeError("BING_SITE_VERIFICATION contains unsupported characters")
if INDEXNOW_KEY and not INDEXNOW_KEY_PATTERN.fullmatch(INDEXNOW_KEY):
    raise RuntimeError("INDEXNOW_KEY must contain 8-128 letters, numbers, or dashes")

templates = Jinja2Templates(directory=TEMPLATE_DIR)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close()


app = FastAPI(
    title="MMA Pick'em API",
    version="0.1.0",
    description="MMA fight cards, winner picks, and pick grading.",
    contact={
        "name": "Kevin T. Coughlin",
        "url": "https://github.com/cascadiacollections/mma-api-service",
    },
    license_info={"name": "MIT", "identifier": "MIT"},
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(EspnMmaError)
async def handle_provider_error(_: Request, exc: EspnMmaError) -> JSONResponse:
    if isinstance(exc, EspnMmaEventNotFoundError):
        status_code = 404
    elif isinstance(exc, EspnMmaTimeoutError):
        status_code = 504
    elif isinstance(exc, EspnMmaDataError):
        status_code = 502
    else:
        status_code = 502
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request.state.csp_nonce = secrets.token_urlsafe(16)
    response = await call_next(request)
    script_sources = f"'self' 'nonce-{request.state.csp_nonce}'"
    image_sources = "'self' data: https://a.espncdn.com"
    frame_sources = "'none'"
    connect_sources = "'self'"
    style_sources = "'self'"
    if ADSENSE_PUBLISHER_ID and request.url.path == "/":
        script_sources = (
            f"'nonce-{request.state.csp_nonce}' 'unsafe-inline' 'unsafe-eval' "
            "'strict-dynamic' https: http:"
        )
        image_sources = "'self' data: https:"
        frame_sources = "https:"
        connect_sources = "'self' https:"
        style_sources = "'self' 'unsafe-inline'"
    response.headers.setdefault(
        "Content-Security-Policy",
        f"default-src 'self'; base-uri 'none'; connect-src {connect_sources}; "
        f"form-action 'none'; frame-ancestors 'none'; frame-src {frame_sources}; "
        f"img-src {image_sources}; object-src 'none'; script-src {script_sources}; "
        f"style-src {style_sources}",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    if request.url.path.startswith("/api/") or request.url.path in {
        "/docs",
        "/redoc",
        "/openapi.json",
    }:
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    return response


@app.get("/", include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "canonical_url": public_url(request),
            "social_image_url": public_url(request, "/static/social-card.png"),
            "csp_nonce": request.state.csp_nonce,
            "adsense_publisher_id": ADSENSE_PUBLISHER_ID,
            "adsense_slot_id": ADSENSE_SLOT_ID,
            "google_site_verification": GOOGLE_SITE_VERIFICATION,
            "bing_site_verification": BING_SITE_VERIFICATION,
        },
        headers={"Cache-Control": "no-cache"},
    )


def legal_document(filename: str) -> FileResponse:
    return FileResponse(STATIC_DIR / filename, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/terms", include_in_schema=False)
async def terms() -> FileResponse:
    return legal_document("terms.html")


@app.get("/privacy", include_in_schema=False)
async def privacy() -> FileResponse:
    return legal_document("privacy.html")


@app.get("/data-policy", include_in_schema=False)
async def data_policy() -> FileResponse:
    return legal_document("data-policy.html")


@app.get("/about", include_in_schema=False)
async def about() -> FileResponse:
    return legal_document("about.html")


def public_url(request: Request, path: str = "") -> str:
    base_url = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return f"{base_url}/{path.lstrip('/')}" if path else base_url


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots(request: Request) -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {public_url(request, '/sitemap.xml')}\n"


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request) -> Response:
    static_paths = ("", "/about", "/terms", "/privacy", "/data-policy")
    event_start, event_end = default_event_window()
    event_summaries = await list_events(event_start, event_end)
    locations = [public_url(request, path) for path in static_paths]
    locations.extend(public_url(request, f"/events/{event.id}") for event in event_summaries)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{escape(location)}</loc></url>" for location in locations)
        + "</urlset>"
    )
    return Response(
        body,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600, s-maxage=3600"},
    )


@app.get("/events/{event_id}", response_class=HTMLResponse, include_in_schema=False)
async def event_page(
    request: Request,
    event_id: str = ApiPath(pattern=r"^\d{6,20}$"),
) -> HTMLResponse:
    ufc_event = await get_event(event_id)
    canonical_url = public_url(request, f"/events/{event_id}")
    competitors = [
        {"@type": "Person", "name": fighter.name}
        for bout in ufc_event.bouts
        for fighter in bout.fighters
    ]
    schema = {
        "@context": "https://schema.org",
        "@type": "SportsEvent",
        "name": ufc_event.name,
        "startDate": ufc_event.date,
        "eventStatus": (
            "https://schema.org/EventCompleted"
            if ufc_event.completed
            else "https://schema.org/EventScheduled"
        ),
        "url": canonical_url,
        "competitor": competitors,
    }
    return templates.TemplateResponse(
        request=request,
        name="event.html",
        context={
            "event": ufc_event,
            "canonical_url": canonical_url,
            "social_image_url": public_url(request, "/static/social-card.png"),
            "schema": schema,
            "csp_nonce": request.state.csp_nonce,
            "google_site_verification": GOOGLE_SITE_VERIFICATION,
            "bing_site_verification": BING_SITE_VERIFICATION,
        },
        headers={"Cache-Control": "public, max-age=300, s-maxage=900"},
    )


@app.get("/ads.txt", response_class=PlainTextResponse, include_in_schema=False)
async def ads_txt() -> PlainTextResponse:
    if not ADSENSE_PUBLISHER_ID:
        raise HTTPException(status_code=404, detail="Advertising is not configured")
    publisher_id = ADSENSE_PUBLISHER_ID.removeprefix("ca-")
    return PlainTextResponse(
        f"google.com, {publisher_id}, DIRECT, f08c47fec0942fa0\n",
        headers={"Cache-Control": "public, max-age=3600"},
    )


if INDEXNOW_KEY:

    @app.get(f"/{INDEXNOW_KEY}.txt", response_class=PlainTextResponse, include_in_schema=False)
    async def indexnow_key() -> PlainTextResponse:
        return PlainTextResponse(
            f"{INDEXNOW_KEY}\n",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "revision": REVISION}


@app.get("/api/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/api/events", response_model=list[EventSummary])
async def events(
    response: Response,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[EventSummary]:
    default_start, default_end = default_event_window()
    start = start or default_start
    end = end or default_end
    if end < start:
        raise HTTPException(status_code=422, detail="end must not be before start")
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="date range cannot exceed 366 days")
    response.headers["Cache-Control"] = (
        "public, max-age=300, s-maxage=600, stale-while-revalidate=60"
    )
    return await list_events(start, end)


@app.get("/api/events/{event_id}", response_model=Event)
async def event(
    response: Response,
    event_id: str = ApiPath(pattern=r"^\d{6,20}$"),
) -> Event:
    ufc_event = await get_event(event_id)
    if ufc_event.completed:
        response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
    elif ufc_event.status.lower() in {"in progress", "live"}:
        response.headers["Cache-Control"] = "public, max-age=5, s-maxage=15"
    else:
        response.headers["Cache-Control"] = "public, max-age=300, s-maxage=900"
    return ufc_event


@app.post("/api/events/{event_id}/grade", response_model=GradeReport)
async def grade(
    submission: PickSubmission,
    event_id: str = ApiPath(pattern=r"^\d{6,20}$"),
) -> GradeReport:
    return grade_picks(await get_event(event_id), submission)
