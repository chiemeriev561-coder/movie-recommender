import json

from fastapi.testclient import TestClient

import api
import movie_recommender as mr


client = TestClient(api.app)


def test_add_favorite_persists_json_to_configured_path(monkeypatch, tmp_path):
    favorites_path = tmp_path / "favorites.json"
    monkeypatch.setenv("FAVORITES_FILE", str(favorites_path))

    added = mr.add_favorite("Inception", 2010, path=str(favorites_path))

    assert added is True
    assert json.loads(favorites_path.read_text(encoding="utf-8")) == [{"name": "Inception", "year": 2010}]


def test_cors_configuration_allows_lovable_origin_regex():
    cors_middleware = next(
        middleware for middleware in api.app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert "https://cine-craft-box.lovable.app" in cors_middleware.kwargs["allow_origins"]
    assert "http://localhost:5173" in cors_middleware.kwargs["allow_origins"]
    assert cors_middleware.kwargs["allow_origin_regex"] == (
        r"https?://(.*\.)?lovable(app|project)\.com|https?://(.*\.)?lovable\.app"
    )


def test_add_favorite_returns_client_error_instead_of_500(tmp_path, monkeypatch):
    favorites_path = tmp_path / "favorites.json"
    monkeypatch.setattr(api, "FAVORITES_FILE", str(favorites_path))
    api.user_favorite_keys.clear()
    api.user_preferences.clear()

    response = client.post("/api/favorites", json={"name": "Missing Movie", "year": 2000})

    assert response.status_code == 400
    assert response.json()["detail"] == "Not found or already in favorites"


def test_remove_favorite_returns_not_found_instead_of_500(tmp_path, monkeypatch):
    favorites_path = tmp_path / "favorites.json"
    monkeypatch.setattr(api, "FAVORITES_FILE", str(favorites_path))
    api.user_favorite_keys.clear()
    api.user_preferences.clear()

    response = client.request("DELETE", "/api/favorites", json={"name": "Inception", "year": 2010})

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found in favorites"


def test_recommendations_use_request_users_own_favorites(tmp_path, monkeypatch):
    favorites_path = tmp_path / "favorites.json"
    monkeypatch.setattr(api, "FAVORITES_FILE", str(favorites_path))
    api.user_favorite_keys.clear()
    api.user_preferences.clear()
    mr.load_favorites(str(favorites_path))

    first_user_client = TestClient(api.app, client=("198.51.100.10", 50000))
    second_user_client = TestClient(api.app, client=("198.51.100.11", 50001))

    add_response = first_user_client.post(
        "/api/favorites",
        json={"name": "Inception", "year": 2010},
    )
    assert add_response.status_code == 200

    first_recs = first_user_client.get("/api/recommendations")
    second_recs = second_user_client.get("/api/recommendations")

    assert first_recs.status_code == 200
    assert second_recs.status_code == 200
    assert first_recs.json()["based_on"]["favorites_count"] == 1
    assert second_recs.json()["based_on"]["favorites_count"] == 0
