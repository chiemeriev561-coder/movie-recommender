import json

import api
import movie_recommender as mr


def test_add_favorite_persists_json_to_configured_path(monkeypatch, tmp_path):
    favorites_path = tmp_path / "favorites.json"
    monkeypatch.setenv("FAVORITES_FILE", str(favorites_path))

    added = mr.add_favorite("Inception", 2010, path=str(favorites_path))

    assert added is True
    assert json.loads(favorites_path.read_text(encoding="utf-8")) == [{"name": "Inception", "year": 2010}]
