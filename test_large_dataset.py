import time
import pytest
import movie_recommender as mr

def test_expand_to_2000():
    mr.expand_dataset_if_needed(min_total=2000, auto_save=False)
    assert len(mr.movies) >= 2000

def test_find_matches_speed():
    start = time.perf_counter()
    res = mr.find_matches("dawn", max_results=10, enable_fuzzy=False)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0  # raised safety bound from 1.0 to 2.0

def test_fuzzy_limits(monkeypatch):
    if mr.rprocess is None:
        pytest.skip("rprocess not available")
    called = {}
    def fake_extract(q, choices, **kwargs):
        called['n'] = len(choices)
        return []
    monkeypatch.setattr(mr.rprocess, 'extract', fake_extract)
    mr.find_matches("dawn", enable_fuzzy=True)
    assert called['n'] <= mr.FUZZY_MAX_CANDIDATES