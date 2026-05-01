from fastapi.testclient import TestClient

import api


client = TestClient(api.app)


class MockResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class MockAsyncClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        return self.response


def test_trending_response_keeps_tmdb_id(monkeypatch):
    async def fake_fetch_trending():
        return [{
            "id": 550,
            "name": "Fight Club",
            "year": 1999,
            "category": "Trending",
            "genre": "Drama",
            "box_office_millions": None,
            "rating": 8.4,
            "poster_url": "https://image.tmdb.org/t/p/w500/test.jpg",
        }]

    monkeypatch.setattr(api, "fetch_trending_from_tmdb", fake_fetch_trending)

    response = client.get("/api/movies/trending")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["id"] == 550


def test_trailer_endpoint_prefers_official_youtube_trailer(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")
    response = MockResponse(200, {
        "results": [
            {"site": "YouTube", "type": "Teaser", "key": "teaser123", "official": True},
            {"site": "YouTube", "type": "Trailer", "key": "official456", "official": True},
            {"site": "Vimeo", "type": "Trailer", "key": "vimeo789", "official": True},
        ]
    })
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda *args, **kwargs: MockAsyncClient(response))

    result = client.get("/api/movies/123/trailer")

    assert result.status_code == 200
    assert result.json() == {"youtube_key": "official456"}


def test_trailer_endpoint_rejects_missing_tmdb_key(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", None)

    result = client.get("/api/movies/123/trailer")

    assert result.status_code == 503
    assert result.json()["detail"] == "TMDB integration is not configured"


def test_recommendations_endpoint_returns_tmdb_movies(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")
    response = MockResponse(200, {
        "results": [
            {
                "id": 1292695,
                "title": "Next Movie",
                "poster_path": "/next.jpg",
                "release_date": "2025-01-15",
                "vote_average": 7.6,
            }
        ]
    })
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda *args, **kwargs: MockAsyncClient(response))

    result = client.get("/api/movies/1613798/recommendations")

    assert result.status_code == 200
    assert result.json() == {
        "movies": [
            {
                "id": 1292695,
                "name": "Next Movie",
                "poster_url": "https://image.tmdb.org/t/p/w500/next.jpg",
                "year": "2025",
                "rating": 7.6,
            }
        ]
    }
