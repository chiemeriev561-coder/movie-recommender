import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import api

client = TestClient(api.app)

@pytest.fixture(autouse=True)
def clear_downloads_cache():
    for key in list(api.cache):
        if str(key).startswith("movie_downloads_"):
            del api.cache[key]

def test_build_magnet_uri():
    info_hash = "0FACFB2D11C9A8F15281A909B45084E6425EF2F0"
    title = "Fight Club"
    magnet = api.build_magnet_uri(info_hash, title)

    assert magnet.startswith("magnet:?xt=urn:btih:0FACFB2D11C9A8F15281A909B45084E6425EF2F0&dn=Fight%20Club")
    assert "&tr=udp%3A//tracker.opentrackr.org%3A1337/announce" in magnet

def test_downloads_endpoint_with_direct_imdb_id(monkeypatch):
    mock_yts_response = {
        "status": "ok",
        "data": {
            "movie_count": 1,
            "movies": [
                {
                    "title": "Fight Club",
                    "year": 1999,
                    "imdb_code": "tt0137523",
                    "torrents": [
                        {
                            "quality": "720p",
                            "type": "bluray",
                            "size": "1.25 GB",
                            "size_bytes": 1342177280,
                            "seeds": 100,
                            "peers": 25,
                            "hash": "0FACFB2D11C9A8F15281A909B45084E6425EF2F0",
                            "url": "https://yts.gg/torrent/download/0FACFB2D11C9A8F15281A909B45084E6425EF2F0"
                        },
                        {
                            "quality": "1080p",
                            "type": "bluray",
                            "size": "2.40 GB",
                            "size_bytes": 2576980377,
                            "seeds": 250,
                            "peers": 40,
                            "hash": "AABBCCDDEEFF00112233445566778899AABBCCDD",
                            "url": "https://yts.gg/torrent/download/AABBCCDDEEFF00112233445566778899AABBCCDD"
                        }
                    ]
                }
            ]
        }
    }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_yts_response
            return mock_resp

    monkeypatch.setattr(api.httpx, "AsyncClient", MockAsyncClient)

    response = client.get("/api/movies/tt0137523/downloads")
    assert response.status_code == 200
    data = response.json()

    assert data["movie_id"] == "tt0137523"
    assert data["imdb_id"] == "tt0137523"
    assert data["title"] == "Fight Club"
    assert data["year"] == 1999
    assert data["available"] is True
    assert len(data["downloads"]) == 2

    first = data["downloads"][0]
    assert first["quality"] == "720p"
    assert first["type"] == "bluray"
    assert first["size"] == "1.25 GB"
    assert first["seeds"] == 100
    assert first["peers"] == 25
    assert first["info_hash"] == "0FACFB2D11C9A8F15281A909B45084E6425EF2F0"
    assert first["torrent_url"] == "https://yts.gg/torrent/download/0FACFB2D11C9A8F15281A909B45084E6425EF2F0"
    assert first["magnet_url"].startswith("magnet:?xt=urn:btih:0FACFB2D11C9A8F15281A909B45084E6425EF2F0")

def test_downloads_endpoint_with_tmdb_id(monkeypatch):
    mock_tmdb_response = {
        "id": 550,
        "title": "Fight Club",
        "imdb_id": "tt0137523",
        "release_date": "1999-10-15"
    }

    mock_yts_response = {
        "status": "ok",
        "data": {
            "movie_count": 1,
            "movies": [
                {
                    "title": "Fight Club",
                    "year": 1999,
                    "imdb_code": "tt0137523",
                    "torrents": [
                        {
                            "quality": "1080p",
                            "type": "bluray",
                            "size": "2.1 GB",
                            "seeds": 80,
                            "peers": 15,
                            "hash": "HASH12345",
                            "url": "https://yts.gg/torrent/download/HASH12345"
                        }
                    ]
                }
            ]
        }
    }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            mock_resp = MagicMock()
            if "api.themoviedb.org" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = mock_tmdb_response
            else:
                mock_resp.status_code = 200
                mock_resp.json.return_value = mock_yts_response
            return mock_resp

    monkeypatch.setattr(api.httpx, "AsyncClient", MockAsyncClient)
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")

    response = client.get("/api/movies/550/downloads")
    assert response.status_code == 200
    data = response.json()

    assert data["movie_id"] == "550"
    assert data["imdb_id"] == "tt0137523"
    assert data["title"] == "Fight Club"
    assert data["available"] is True
    assert len(data["downloads"]) == 1
    assert data["downloads"][0]["quality"] == "1080p"

def test_downloads_endpoint_no_torrents_found(monkeypatch):
    mock_tmdb_response = {
        "id": 999999,
        "title": "Obscure Indie Film",
        "imdb_id": "tt9999999",
        "release_date": "2024-01-01"
    }

    mock_yts_response = {
        "status": "ok",
        "data": {
            "movie_count": 0
        }
    }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            mock_resp = MagicMock()
            if "api.themoviedb.org" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = mock_tmdb_response
            else:
                mock_resp.status_code = 200
                mock_resp.json.return_value = mock_yts_response
            return mock_resp

    monkeypatch.setattr(api.httpx, "AsyncClient", MockAsyncClient)
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")

    response = client.get("/api/movies/999999/downloads")
    assert response.status_code == 200
    data = response.json()
    assert data["movie_id"] == "999999"
    assert data["available"] is False
    assert data["downloads"] == []

def test_downloads_endpoint_tmdb_404(monkeypatch):
    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            return mock_resp

    monkeypatch.setattr(api.httpx, "AsyncClient", MockAsyncClient)
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")

    response = client.get("/api/movies/000000/downloads")
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie not found on TMDB"

def test_qbittorrent_status(monkeypatch):
    monkeypatch.setattr(api, "QBITTORRENT_PASSWORD", "test-password")

    async def fake_qbittorrent_request(method, path, **kwargs):
        response = MagicMock()
        response.status_code = 200
        response.text = "v5.2.3"
        return response

    monkeypatch.setattr(api, "qbittorrent_request", fake_qbittorrent_request)

    response = client.get("/api/qbittorrent/status")
    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["version"] == "v5.2.3"

def test_add_movie_to_qbittorrent(monkeypatch):
    monkeypatch.setattr(api, "QBITTORRENT_PASSWORD", "test-password")
    movie_downloads = api.MovieDownloadResponse(
        movie_id="tt0137523",
        title="Fight Club",
        available=True,
        downloads=[api.MovieDownloadItem(
            quality="1080p",
            type="bluray",
            size="2.40 GB",
            info_hash="HASH123",
            torrent_url="https://example.test/movie.torrent",
            magnet_url="magnet:?xt=urn:btih:HASH123",
        )],
    )

    async def fake_get_movie_downloads(request, movie_id):
        return movie_downloads

    async def fake_qbittorrent_request(method, path, **kwargs):
        assert method == "POST"
        assert path == "/api/v2/torrents/add"
        assert kwargs["data"]["urls"] == "magnet:?xt=urn:btih:HASH123"
        response = MagicMock()
        response.status_code = 200
        response.text = "Ok."
        return response

    monkeypatch.setattr(api, "get_movie_downloads", fake_get_movie_downloads)
    monkeypatch.setattr(api, "qbittorrent_request", fake_qbittorrent_request)

    response = client.post("/api/movies/tt0137523/qbittorrent?quality=1080p")
    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["torrent_hash"] == "HASH123"
