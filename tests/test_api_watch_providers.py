import pytest
from fastapi.testclient import TestClient
import api
import httpx

client = TestClient(api.app)

class MockResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

class MockAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        if "watch/providers" in url:
            return MockResponse(200, {
                "results": {
                    "US": {
                        "link": "https://www.themoviedb.org/movie/550/watch?locale=US",
                        "flatrate": [
                            {"provider_id": 9, "provider_name": "Amazon Prime Video", "logo_path": "/prime.jpg"}
                        ],
                        "buy": [
                            {"provider_id": 10, "provider_name": "Amazon Video", "logo_path": "/amazon.jpg"}
                        ]
                    }
                }
            })
        else:
            # Details endpoint
            return MockResponse(200, {
                "title": "Fight Club"
            })

def test_watch_providers_endpoint_success(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")
    # Clear cache for clean test run
    api.cache.clear()
    
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda *args, **kwargs: MockAsyncClient())

    response = client.get("/api/movies/550/watch-providers?country_code=US")
    assert response.status_code == 200
    data = response.json()
    
    assert data["movie_id"] == 550
    assert data["movie_title"] == "Fight Club"
    assert data["country"] == "US"
    
    providers = data["providers"]
    assert len(providers) == 2
    
    # Provider 9 should use the default TMDB link from results
    prov_9 = next(p for p in providers if p["provider_id"] == 9)
    assert prov_9["provider_name"] == "Amazon Prime Video"
    assert prov_9["link"] == "https://www.themoviedb.org/movie/550/watch?locale=US"
    assert prov_9["type"] == "stream"
    
    # Provider 10 should use the dynamic Amazon Affiliate Link
    prov_10 = next(p for p in providers if p["provider_id"] == 10)
    assert prov_10["provider_name"] == "Amazon Video"
    assert prov_10["link"] == "https://www.amazon.com/s?k=Fight+Club&tag=phloxmovies20-20"
    assert prov_10["type"] == "buy"

def test_watch_providers_endpoint_missing_key(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", None)
    
    response = client.get("/api/movies/550/watch-providers")
    assert response.status_code == 503
    assert response.json()["detail"] == "TMDB integration is not configured"

def test_watch_providers_endpoint_not_found(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")
    api.cache.clear()

    class NotFoundMockClient(MockAsyncClient):
        async def get(self, url, params=None):
            if "watch/providers" in url:
                return MockResponse(200, {"results": {}})
            else:
                return MockResponse(404, {"status_message": "Not Found"})

    monkeypatch.setattr(api.httpx, "AsyncClient", lambda *args, **kwargs: NotFoundMockClient())

    response = client.get("/api/movies/99999/watch-providers")
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie not found on TMDB"
