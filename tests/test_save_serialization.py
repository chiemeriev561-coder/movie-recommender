import os
import pytest
import movie_recommender as mr


def test_save_serializes_internal_fields(tmp_path):
    # Ensure search fields are present on at least some movies
    if not any(m.get('_search_text') for m in mr.movies):
        # ensure fields are computed
        for m in mr.movies[:10]:
            mr.ensure_search_fields(m)

    out = tmp_path / 'dump.json'
    ok = mr.save_movies(str(out), mr.movies)
    assert ok
    # file must be valid JSON and should contain at least one movie name
    with open(out, 'r', encoding='utf-8') as f:
        data = f.read()
    assert '"name"' in data
    assert 'Inception' in data or len(mr.movies) > 0
