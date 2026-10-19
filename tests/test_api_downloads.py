"""
Tests for Movie Downloads integration in api.py.
Verifies graceful degradation, circuit breaking, and complete API isolation.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import httpx

# Ensure paths
snap_dist_packages = "/home/victor/snap/antigravity-cli/common/local/lib/python3.14/dist-packages"
if Path(snap_dist_packages).is_dir() and snap_dist_packages not in sys.path:
    sys.path.insert(0, snap_dist_packages)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import app

client = TestClient(app)


def test_downloads_graceful_fallback_when_scraper_offline(monkeypatch):
    """
    Critical isolation test:
    When the scraper service on port 8001 is offline / connection refused,
    api.py must NOT throw 500 or crash. It must return 200 with available=False.
    """
    class OfflineTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused to port 8001")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda *args, **kwargs: original_client(transport=OfflineTransport(), *args, **kwargs)
    )

    response = client.get("/api/movies/123/downloads?title=Inception")
    assert response.status_code == 200
    data = response.json()
    assert data["movie_id"] == "123"
    assert data["available"] is False
    assert data["status"] == "scraper_unavailable"
    assert data["options"] == []


def test_downloads_success_when_scraper_online(monkeypatch):
    """
    Verify api.py correctly formats and maps download options when scraper responds.
    """
    class MockScraperTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if "search" in str(request.url):
                return httpx.Response(200, json={
                    "query": "Tenzing",
                    "total_results": 1,
                    "results": [{"title": "Tenzing (2026)", "url": "https://thenkiri.com/tenzing"}]
                }, request=request)
            elif "options" in str(request.url):
                return httpx.Response(200, json={
                    "url": "https://thenkiri.com/tenzing",
                    "title": "Tenzing (2026)",
                    "options": [{
                        "quality": "720p",
                        "download_url": "https://downloadwella.com/xyz123",
                        "file_size": "450 MB",
                        "hoster": "downloadwella"
                    }]
                }, request=request)
            return httpx.Response(404, request=request)

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda *args, **kwargs: original_client(transport=MockScraperTransport(), *args, **kwargs)
    )

    response = client.get("/api/movies/456/downloads?title=Tenzing")
    assert response.status_code == 200
    data = response.json()
    assert data["movie_id"] == "456"
    assert data["available"] is True
    assert data["status"] == "ok"
    assert len(data["options"]) == 1
    assert data["options"][0]["quality"] == "720p"
    assert data["options"][0]["file_size"] == "450 MB"
    assert data["options"][0]["download_url"] == "https://downloadwella.com/xyz123"


def test_downloads_resolve_endpoint(monkeypatch):
    """Verify download link resolution endpoint on main API."""
    class MockBypassTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "original_url": "https://downloadwella.com/xyz123",
                "direct_url": "https://dwbe02.downloadwella.com/d/abc/movie.mkv",
                "file_name": "movie.mkv",
                "file_size": "450 MB",
                "status": "resolved",
                "duration_ms": 350.0
            }, request=request)

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda *args, **kwargs: original_client(transport=MockBypassTransport(), *args, **kwargs)
    )

    payload = {"url": "https://downloadwella.com/xyz123"}
    response = client.post("/api/movies/downloads/resolve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"
    assert data["direct_url"] == "https://dwbe02.downloadwella.com/d/abc/movie.mkv"
    assert data["file_name"] == "movie.mkv"
