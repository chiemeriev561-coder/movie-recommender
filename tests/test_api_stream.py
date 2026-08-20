from fastapi.testclient import TestClient
import api

client = TestClient(api.app)

def test_movie_stream_endpoint_returns_vidlink_and_nontongo_fallback():
    movie_id = "550"
    response = client.get(f"/api/movies/{movie_id}/stream")

    assert response.status_code == 200
    data = response.json()
    assert data["movie_id"] == "550"
    assert data["stream_url"] == "https://vidlink.pro/movie/550"
    assert data["provider"] == "Phlox Premium Secure Stream"
    assert data["fallback_stream_url"] == "https://nontongo.win/movie/550"
    assert data["fallback_provider"] == "Nontongo.win"

def test_stream_endpoint_strips_movie_id():
    movie_id = "  12345  "
    response = client.get(f"/api/movies/{movie_id}/stream")

    assert response.status_code == 200
    data = response.json()
    assert data["movie_id"] == "12345"
    assert data["stream_url"] == "https://vidlink.pro/movie/12345"
    assert data["fallback_stream_url"] == "https://nontongo.win/movie/12345"

def test_tv_episode_stream_endpoint_returns_nontongo_fallback():
    response = client.get("/api/tv/100/season/1/episode/5/stream")

    assert response.status_code == 200
    data = response.json()
    assert data["series_id"] == 100
    assert data["season_number"] == 1
    assert data["episode_number"] == 5
    assert data["stream_url"] == "https://vidlink.pro/tv/100/1/5"
    assert data["provider"] == "VidLink"
    assert data["fallback_stream_url"] == "https://nontongo.win/tv/100/1/5"
    assert data["fallback_provider"] == "Nontongo.win"
