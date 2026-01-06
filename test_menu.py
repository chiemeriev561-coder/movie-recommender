import importlib
import sys


def test_auto_menu_opens(monkeypatch, tmp_path):
    # Ensure stdin appears interactive
    class DummyStdin:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, 'stdin', DummyStdin())

    # Reload module to ensure fresh state
    mr = importlib.reload(__import__('movie_recommender'))

    called = {}

    def fake_menu(*a, **k):
        called['ok'] = True

    monkeypatch.setattr(mr, 'user_menu', fake_menu)

    # Call main with empty argv (no args provided)
    mr.main(argv=[])

    assert called.get('ok') is True
