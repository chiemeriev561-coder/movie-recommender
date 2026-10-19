"""
Tests for Scraper Microservice (Port 8001).
Verifies isolated operation, response schemas, and error resilience.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure snap python dist-packages and project root are discoverable
snap_dist_packages = "/home/victor/snap/antigravity-cli/common/local/lib/python3.14/dist-packages"
if Path(snap_dist_packages).is_dir() and snap_dist_packages not in sys.path:
    sys.path.insert(0, snap_dist_packages)

from scraper_service.main import app
from scraper_service.config import SCRAPER_PORT

client = TestClient(app)


def test_scraper_health():
    """Verify health endpoint responds with ok status and configured port."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "scraper-service"
    assert data["port"] == SCRAPER_PORT
    assert "uptime_seconds" in data


def test_scraper_root_info():
    """Verify root endpoint lists service metadata and routes."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Movie Scraper Microservice"
    assert data["port"] == SCRAPER_PORT
    assert "endpoints" in data


def test_scraper_search_endpoint():
    """Verify movie search skeleton endpoint."""
    payload = {"query": "Inception", "limit": 5, "source": "thenkiri"}
    response = client.post("/api/v1/scraper/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Inception"
    assert "results" in data
    assert isinstance(data["results"], list)
    assert "duration_ms" in data


def test_scraper_search_validation():
    """Verify validation for empty search query."""
    response = client.post("/api/v1/scraper/search", json={"query": ""})
    assert response.status_code == 422


def test_scraper_download_options_endpoint():
    """Verify download options skeleton endpoint."""
    payload = {"url": "https://thenkiri.com/download-movie-123", "title": "Inception"}
    response = client.post("/api/v1/scraper/options", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://thenkiri.com/download-movie-123"
    assert data["title"] == "Inception"
    assert "options" in data
    assert isinstance(data["options"], list)


def test_scraper_bypass_endpoint():
    """Verify bypass link resolution endpoint."""
    payload = {"url": "https://downloadwella.com/file/xyz123"}
    response = client.post("/api/v1/scraper/bypass", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["original_url"] == "https://downloadwella.com/file/xyz123"
    assert data["status"] in ("resolved", "failed")
    assert "duration_ms" in data


def test_scraper_stats_endpoint():
    """Verify operational stats tracking."""
    response = client.get("/api/v1/scraper/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert data["total_requests"] >= 1
    assert "uptime_seconds" in data


def test_thenkiri_search_html_parsing():
    """Verify Thenkiri search HTML parser accurately extracts title, url, year, poster."""
    from bs4 import BeautifulSoup
    from scraper_service.client import ThenkiriClient

    sample_html = """
    <article class="post-12345 entry" id="post-12345">
      <div class="search-entry-inner">
        <div class="thumbnail">
          <a class="thumbnail-link" href="https://thenkiri.com/sample-movie-2026-download/">
            <img src="https://thenkiri.com/uploads/sample.webp" alt="Sample Movie" />
          </a>
        </div>
        <div class="search-entry-content">
          <h2 class="search-entry-title entry-title">
            <a href="https://thenkiri.com/sample-movie-2026-download/">Sample Movie (2026) | Download Hollywood Movie</a>
          </h2>
          <div class="search-entry-summary"><p>Sample synopsis text</p></div>
        </div>
      </div>
    </article>
    """
    soup = BeautifulSoup(sample_html, "html.parser")
    client_obj = ThenkiriClient()
    results = client_obj._parse_search_results(soup, limit=10)

    assert len(results) == 1
    item = results[0]
    assert item.title == "Sample Movie (2026)"
    assert item.year == "2026"
    assert item.url == "https://thenkiri.com/sample-movie-2026-download/"
    assert item.poster_url == "https://thenkiri.com/uploads/sample.webp"


def test_thenkiri_download_page_parsing():
    """Verify Thenkiri download page parser extracts downloadwella links and size."""
    from bs4 import BeautifulSoup
    from scraper_service.client import ThenkiriClient

    sample_html = """
    <html>
      <head><title>DOWNLOAD Sample Movie (2026) - TheNkiri</title></head>
      <body>
        <h1 class="entry-title">Sample Movie (2026) | Download Hollywood Movie</h1>
        <div class="elementor-alert">
          <span class="elementor-alert-title">Download Size</span>
          <span class="elementor-alert-description">This Video is 750.5 MB</span>
        </div>
        <div class="elementor-button-wrapper">
          <a class="elementor-button elementor-button-link elementor-size-md" 
             href="https://downloadwella.com/abc12345/Sample.Movie.2026.720p.mkv.html">
            <span class="elementor-button-text">Download Movie</span>
          </a>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(sample_html, "html.parser")
    client_obj = ThenkiriClient()
    options, title = client_obj._parse_download_page(soup, "https://thenkiri.com/sample-movie-2026-download/")

    assert title == "Sample Movie (2026)"
    assert len(options) == 1
    opt = options[0]
    assert opt.hoster == "downloadwella"
    assert "downloadwella.com/abc12345" in opt.download_url
    assert opt.file_size == "750.5 MB"
    assert opt.quality == "720p"


def test_scraper_bypass_invalid_url():
    """Verify bypass handles non-existent or unreachable URL cleanly."""
    response = client.post("/api/v1/scraper/bypass", json={"url": "https://invalid-hoster-test-xyz.com/123"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["direct_url"] is None
    assert "error" in data


def test_downloadwella_http_bypass_logic(monkeypatch):
    """Verify HTTP bypass logic accurately handles Downloadwella step 1 and step 2."""
    import asyncio
    from scraper_service.bypass import resolve_downloadwella_http
    import httpx

    step1_html = """
    <form name="F1" method="POST" action="">
      <input type="hidden" name="op" value="download2" />
      <input type="hidden" name="id" value="test12345" />
      <button id="downloadbtn">Create download link</button>
    </form>
    """

    step2_html = """
    <div id="container">
      <table class="file_slot">
        <tr><td>Filename: <b>Test.Movie.2026.mkv</b><br/>Size: 500 MB</td></tr>
      </table>
      <a href="https://dwbe01.downloadwella.com/d/mocktoken123/Test.Movie.2026.mkv">
        <button id="downloadbtn"><span id="direct_link">Start download</span></button>
      </a>
    </div>
    """

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, text=step1_html, request=request)
            else:
                return httpx.Response(200, text=step2_html, request=request)

    # Monkeypatch AsyncClient in bypass module
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "scraper_service.bypass.httpx.AsyncClient",
        lambda *args, **kwargs: original_client(transport=MockTransport(), *args, **kwargs)
    )

    async def _run():
        return await resolve_downloadwella_http("https://downloadwella.com/test12345/movie.html")

    direct_url, file_name, file_size, err = asyncio.run(_run())

    assert err is None
    assert direct_url == "https://dwbe01.downloadwella.com/d/mocktoken123/Test.Movie.2026.mkv"
    assert file_name == "Test.Movie.2026.mkv"
    assert file_size == "500 MB"



