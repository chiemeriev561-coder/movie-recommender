import json
import pytest
from movie_recommender import find_matches, _HAS_RAPIDFUZZ, main, load_movies, save_movies


@pytest.mark.skipif(not _HAS_RAPIDFUZZ, reason="RapidFuzz not available; skipping fuzzy tests")
def test_fuzzy_matching_typo():
    # A small typo in 'Inception' should match if fuzzy matching is enabled
    res = find_matches('Incption', enable_fuzzy=True, fuzzy_threshold=60)
    assert any(m['name'] == 'Inception' for m in res)


def test_cli_query_json_output(capsys):
    main(['--query', 'Inception', '--format', 'json'])
    captured = capsys.readouterr()
    assert 'Inception' in captured.out


def test_cli_load_and_query(tmp_path, capsys):
    # Create a small movie file and load it
    movie_item = {
        'name': 'Tmp Movie', 'year': 2023, 'category': 'Test', 'genre': 'Test', 'box_office_millions': 1.0, 'rating': 5.0
    }
    p = tmp_path / 'tmp_movies.json'
    save_movies(str(p), [movie_item])
    main(['--load', str(p), '--query', 'Tmp Movie', '--format', 'json'])
    captured = capsys.readouterr()
    assert 'Tmp Movie' in captured.out


def test_fuzzy_flag_without_rapidfuzz(capsys):
    # Ensure we warn when --fuzzy is used but RapidFuzz is not installed
    main(['--query', 'Inception', '--fuzzy', '--format', 'text'])
    captured = capsys.readouterr()
    if _HAS_RAPIDFUZZ:
        assert 'RapidFuzz' not in captured.err
    else:
        assert 'RapidFuzz' in captured.err or 'Warning: --fuzzy' in captured.err
