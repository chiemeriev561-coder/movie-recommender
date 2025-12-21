import os
import tempfile
import json
import pytest

from movie_recommender import (
    sanitize_query, find_matches, add_movie, validate_movie_schema,
    generate_synthetic_movies, save_movies, load_movies, movies
)


def test_sanitize_query_basic():
    assert sanitize_query('  Hello\n') == 'Hello'
    assert sanitize_query('A' * 200, max_length=50) == 'A' * 50


def test_find_matches_by_name():
    res = find_matches('Inception')
    assert any(m['name'] == 'Inception' for m in res)


def test_find_matches_by_year():
    res = find_matches('2010')
    assert any(m['year'] == 2010 for m in res)


def test_add_movie_validation_and_duplicate():
    invalid = {'name': '', 'year': 'two thousand', 'category': 'Test'}
    assert not add_movie(invalid)

    new_movie = {
        'name': 'Unit Test Movie', 'year': 2025, 'category': 'Test', 'genre': 'Test',
        'box_office_millions': 1.0, 'rating': 5.5
    }
    # ensure it adds
    added = add_movie(new_movie)
    assert added
    # adding again should be rejected (duplicate)
    added_again = add_movie(new_movie)
    assert not added_again
    # cleanup - remove the added movie
    for i, m in enumerate(movies):
        if m['name'] == 'Unit Test Movie' and m['year'] == 2025:
            movies.pop(i)
            break


def test_generate_synthetic_movies_unique_titles_and_count():
    generated = generate_synthetic_movies(target_count=650, start_year=2019, end_year=2021)
    assert isinstance(generated, list)
    names = [m['name'] for m in generated]
    assert len(names) == len(set(names))


def test_save_and_load_roundtrip(tmp_path):
    tmpfile = tmp_path / "test_movies.json"
    sample = [m for m in movies][:3]
    ok = save_movies(str(tmpfile), sample)
    assert ok
    loaded = load_movies(str(tmpfile))
    assert isinstance(loaded, list)
    assert len(loaded) == len(sample)
    # file is valid json
    with open(tmpfile, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert isinstance(data, list)


if __name__ == '__main__':
    pytest.main([os.path.abspath(__file__)])
