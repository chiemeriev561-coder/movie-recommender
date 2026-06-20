import pytest
from fastapi.testclient import TestClient
from api import app, TMDB_API_KEY
import movie_recommender as mr

client = TestClient(app)

def test_trending_fallback_when_no_key(monkeypatch):
    """Test that the trending endpoint falls back to CSV when TMDB_API_KEY is missing."""
    # Ensure TMDB_API_KEY is None for this test
    monkeypatch.setattr("api.TMDB_API_KEY", None)
    
    response = client.get("/api/movies/trending")
    assert response.status_code == 200
    data = response.json()
    
    # Should return up to 20 movies from the local dataset
    assert len(data) <= 20
    if len(mr.movies) > 0:
        assert len(data) > 0
        # Check that it's returning MovieResponse objects (based on local data)
        assert "name" in data[0]
        assert "year" in data[0]
        assert "category" in data[0]

def test_trending_error_fallback(monkeypatch):
    """Test that the trending endpoint falls back to CSV when TMDB API fails."""
    import api
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_key")
    
    class ErrorAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def get(self, url, params=None):
            raise api.httpx.RequestError("TMDB is down")
            
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda *args, **kwargs: ErrorAsyncClient())
    
    response = client.get("/api/movies/trending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    # Confirm it returned MovieResponse objects (based on local data)
    assert "name" in data[0]
    assert "year" in data[0]
