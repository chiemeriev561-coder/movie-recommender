import math
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import api


@pytest.mark.asyncio
async def test_hybrid_scoring_blends_normalized_tmdb_and_content_scores(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", "test-key")

    candidate = {
        "id": 101,
        "name": "Popular Match",
        "year": 2020,
        "category": "TMDB",
        "genre": "Action",
        "rating": 9.0,
        "tmdb_popularity": 100.0,
        "tmdb_rank": 1000,
    }

    async def fake_candidates(*args, **kwargs):
        return [candidate]

    monkeypatch.setattr(api, "tmdb_get_recommendations", fake_candidates)
    monkeypatch.setattr(api, "tmdb_get_similar", fake_candidates)
    monkeypatch.setattr(api, "tmdb_discover", fake_candidates)

    results = await api.get_hybrid_recommendations(
        tmdb_id=None,
        limit=10,
        tmdb_weight=0.25,
        content_weight=0.75,
    )

    tmdb_score = (
        math.log(101) / math.log(1000)
        + math.log(1001) / math.log(10000)
    ) / 2
    content_score = 0.9
    expected = tmdb_score * 0.25 + content_score * 0.75

    assert len(results) == 1
    assert results[0]["tmdb_score"] == round(tmdb_score, 4)
    assert results[0]["content_score"] == content_score
    assert results[0]["hybrid_score"] == round(expected, 4)


def test_hybrid_endpoint_caches_final_response_per_scoring_inputs(monkeypatch):
    api.cache.clear()
    monkeypatch.setattr(api, "TMDB_API_KEY", "test-key")
    favorite_keys = set()
    monkeypatch.setattr(api, "get_user_favorite_keys", lambda user_ip: favorite_keys)

    hybrid_result = {
        "id": 101,
        "name": "Cached Match",
        "year": 2020,
        "category": "TMDB",
        "genre": "Action",
        "rating": 8.0,
        "hybrid_score": 0.8,
        "tmdb_score": 0.7,
        "content_score": 0.9,
    }
    generate = AsyncMock(return_value=[hybrid_result])
    monkeypatch.setattr(api, "get_hybrid_recommendations", generate)
    client = TestClient(api.app)

    try:
        first = client.get(
            "/api/recommendations/hybrid?tmdb_id=987654&limit=1"
        )
        second = client.get(
            "/api/recommendations/hybrid?tmdb_id=987654&limit=1"
        )
        changed_weight = client.get(
            "/api/recommendations/hybrid?tmdb_id=987654&limit=1&content_weight=0.7&tmdb_weight=0.3"
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert changed_weight.status_code == 200
        assert second.json() == first.json()
        assert generate.await_count == 2
    finally:
        api.cache.clear()


def test_hybrid_endpoint_loads_favorite_movies(monkeypatch):
    api.cache.clear()
    monkeypatch.setattr(api, "TMDB_API_KEY", "test-key")
    monkeypatch.setattr(api, "get_user_favorite_keys", lambda user_ip: {("Inception", 2010)})

    favorite = {"name": "Inception", "year": 2010, "genre": "Sci-Fi"}
    monkeypatch.setattr(api.movie_recommender, "_movies_map", {("inception", 2010): favorite})
    update_map = Mock()
    monkeypatch.setattr(api.movie_recommender, "_update_movies_map_if_needed", update_map)
    generate = AsyncMock(return_value=[])
    monkeypatch.setattr(api, "get_hybrid_recommendations", generate)

    try:
        response = TestClient(api.app).get("/api/recommendations/hybrid?tmdb_id=123")

        assert response.status_code == 200
        assert generate.await_args.kwargs["favorite_movies"] == [favorite]
        update_map.assert_called_once_with()
    finally:
        api.cache.clear()
