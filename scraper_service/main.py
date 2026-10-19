"""
FastAPI application for the isolated Movie Scraper Service.
Runs independently on port 8001.
"""

import time
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from scraper_service.config import (
    SCRAPER_PORT,
    SCRAPER_HOST,
    ALLOWED_ORIGINS,
    SCRAPER_LOG_LEVEL
)
from scraper_service.models import (
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    DownloadOptionsRequest,
    DownloadOptionsResponse,
    DownloadOptionItem,
    BypassRequest,
    BypassResponse,
    ScraperStatsResponse
)

from scraper_service.client import ThenkiriClient

# Setup logging
logging.basicConfig(
    level=getattr(logging, SCRAPER_LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("scraper_service")

# Service state and metrics
_service_start_time: float = 0.0
_metrics: Dict[str, Any] = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_duration_ms": 0.0,
}

scraper_client = ThenkiriClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _service_start_time
    _service_start_time = time.time()
    logger.info("Scraper Service starting up on port %d...", SCRAPER_PORT)
    yield
    logger.info("Scraper Service shutting down...")
    await scraper_client.close()


app = FastAPI(
    title="Movie Scraper Service",
    description="Independent service dedicated to movie searches and download link resolution",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    _metrics["total_requests"] += 1
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        _metrics["total_duration_ms"] += duration_ms
        if response.status_code < 400:
            _metrics["successful_requests"] += 1
        else:
            _metrics["failed_requests"] += 1
        return response
    except Exception as exc:
        _metrics["failed_requests"] += 1
        logger.error("Unhandled error processing %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal scraper service error", "error": str(exc)}
        )


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Liveness & readiness probe."""
    uptime = time.time() - _service_start_time if _service_start_time > 0 else 0.0
    return HealthResponse(
        status="ok",
        service="scraper-service",
        version="1.0.0",
        uptime_seconds=round(uptime, 2),
        port=SCRAPER_PORT
    )


@app.get("/", tags=["Info"])
async def root_info():
    """Root info endpoint providing service metadata."""
    return {
        "service": "Movie Scraper Microservice",
        "version": "1.0.0",
        "port": SCRAPER_PORT,
        "status": "operational",
        "documentation": "/docs",
        "health": "/health",
        "endpoints": {
            "search": "/api/v1/scraper/search",
            "options": "/api/v1/scraper/options",
            "bypass": "/api/v1/scraper/bypass",
            "stats": "/api/v1/scraper/stats"
        }
    }


@app.get("/api/v1/scraper/stats", response_model=ScraperStatsResponse, tags=["Metrics"])
async def get_stats():
    """Retrieve scraper operational stats."""
    uptime = time.time() - _service_start_time if _service_start_time > 0 else 0.0
    total = _metrics["total_requests"]
    avg_duration = (_metrics["total_duration_ms"] / total) if total > 0 else 0.0
    return ScraperStatsResponse(
        total_requests=total,
        successful_requests=_metrics["successful_requests"],
        failed_requests=_metrics["failed_requests"],
        average_duration_ms=round(avg_duration, 2),
        uptime_seconds=round(uptime, 2)
    )


@app.post("/api/v1/scraper/search", response_model=SearchResponse, tags=["Scraper"])
async def search_movie_endpoint(req: SearchRequest):
    """
    Search for movies across Thenkiri download providers.
    Returns list of matching movie cards with titles, URLs, years, and posters.
    """
    start_time = time.perf_counter()
    results, error_msg = await scraper_client.search_movies(query=req.query, limit=req.limit or 10)
    duration_ms = (time.perf_counter() - start_time) * 1000.0

    return SearchResponse(
        query=req.query,
        total_results=len(results),
        results=results,
        duration_ms=round(duration_ms, 2),
        error=error_msg
    )


@app.post("/api/v1/scraper/options", response_model=DownloadOptionsResponse, tags=["Scraper"])
async def download_options_endpoint(req: DownloadOptionsRequest):
    """
    Retrieve available download options (qualities/links) for a movie page URL.
    Extracts direct hoster links (e.g. Downloadwella) and file sizes.
    """
    start_time = time.perf_counter()
    options, found_title, error_msg = await scraper_client.get_download_options(movie_url=req.url, title=req.title)
    duration_ms = (time.perf_counter() - start_time) * 1000.0

    return DownloadOptionsResponse(
        url=req.url,
        title=found_title or req.title,
        options=options,
        duration_ms=round(duration_ms, 2),
        error=error_msg
    )


from scraper_service.bypass import resolve_download_link


@app.post("/api/v1/scraper/bypass", response_model=BypassResponse, tags=["Scraper"])
async def bypass_intermediate_endpoint(req: BypassRequest):
    """
    Bypass intermediate hoster waiting screen / countdown / form.
    Resolves intermediate Downloadwella link directly to final CDN stream link.
    """
    start_time = time.perf_counter()
    direct_url, file_name, file_size, error_msg = await resolve_download_link(url=req.url)
    duration_ms = (time.perf_counter() - start_time) * 1000.0

    status = "resolved" if direct_url else "failed"

    return BypassResponse(
        original_url=req.url,
        direct_url=direct_url,
        file_name=file_name,
        file_size=file_size,
        status=status,
        duration_ms=round(duration_ms, 2),
        error=error_msg
    )
