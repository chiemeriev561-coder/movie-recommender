from fastapi.testclient import TestClient
import api

client = TestClient(api.app)

def test_stream_endpoint_returns_correct_embed_url():
    movie_id = "550"
    response = client.get(f"/api/movies/{movie_id}/stream")
    
    assert response.status_code == 200
    data = response.json()
    assert data["movie_id"] == "550"
    assert data["stream_url"] == "https://multiembed.mov/?video_id=550&tmdb=1"
    assert data["provider"] == "Phlox High-Speed Stream Network"

def test_stream_endpoint_strips_movie_id():
    movie_id = "  12345  "
    response = client.get(f"/api/movies/{movie_id}/stream")
    
    assert response.status_code == 200
    data = response.json()
    assert data["movie_id"] == "12345"
    assert data["stream_url"] == "https://multiembed.mov/?video_id=12345&tmdb=1"
