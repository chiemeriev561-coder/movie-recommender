import json

import api
import movie_recommender as mr


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
    assert cors_middleware.kwargs["allow_origin_regex"] == r"https://.*\.lovable\.app"
