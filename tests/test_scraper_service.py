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
    """Verify bypass link resolution skeleton endpoint."""
    payload = {"url": "https://downloadwella.com/file/xyz123"}
    response = client.post("/api/v1/scraper/bypass", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["original_url"] == "https://downloadwella.com/file/xyz123"
    assert data["status"] == "pending"
    assert "duration_ms" in data


def test_scraper_stats_endpoint():
    """Verify operational stats tracking."""
    response = client.get("/api/v1/scraper/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert data["total_requests"] >= 1
    assert "uptime_seconds" in data
