import pytest
import movie_recommender as mr
from pathlib import Path


def test_save_movies_failure(monkeypatch, tmp_path):
    # Simulate an IO error when opening the file for write
    tmpfile = tmp_path / "out.json"

    class FakePath(Path):
        def open(self, *args, **kwargs):
            raise OSError("disk full (simulated)")

    # Monkeypatch Path used inside save_movies
    monkeypatch.setattr(mr, 'Path', FakePath)

    ok = mr.save_movies(str(tmpfile), [{'name':'A','year':2020,'category':'Test','genre':'Test','box_office_millions':1.0,'rating':5.0}])
    assert not ok
    err = mr.get_last_save_error()
    assert err is not None and 'simulated' in err


def test_expand_dataset_autosave_error(monkeypatch, tmp_path):
    # Simulate save_movies returning False
    called = {}
    def fake_save(path, movie_list):
        called['path'] = path
        return False
    monkeypatch.setattr(mr, 'save_movies', fake_save)
    # ensure get_last_save_error returns a message we set
    monkeypatch.setattr(mr, 'last_save_error', 'simulated failure')
    # start with a small in-memory dataset so expansion will run
    monkeypatch.setattr(mr, 'movies', [])

    ok = mr.expand_dataset_if_needed(min_total=1000, auto_save=True, save_path=str(tmp_path / 'x.json'))
    assert not ok
    assert called.get('path') is not None
