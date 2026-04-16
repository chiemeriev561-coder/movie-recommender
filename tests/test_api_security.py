import json

import pytest

import api
import movie_recommender as mr


def test_require_api_key_rejects_missing_header(monkeypatch):
    monkeypatch.setenv("MUTATION_API_KEY", "secret-key")

    with pytest.raises(api.HTTPException) as exc_info:
        api.require_api_key(None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API key"


def test_require_api_key_returns_503_without_configured_key(monkeypatch):
    monkeypatch.delenv("MUTATION_API_KEY", raising=False)

    with pytest.raises(api.HTTPException) as exc_info:
        api.require_api_key("anything")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Favorites API is not configured"


def test_add_favorite_persists_json_to_configured_path(monkeypatch, tmp_path):
    favorites_path = tmp_path / "favorites.json"
    monkeypatch.setenv("FAVORITES_FILE", str(favorites_path))

    added = mr.add_favorite("Inception", 2010, path=str(favorites_path))

    assert added is True
    assert json.loads(favorites_path.read_text(encoding="utf-8")) == [{"name": "Inception", "year": 2010}]
