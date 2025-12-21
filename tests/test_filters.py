import pytest
from movie_recommender import find_matches, serialize_movies, movies


def test_find_by_genre():
    res = find_matches('', genre='Animation')
    assert isinstance(res, list)
    assert any('Animation' in m.get('genre','') or 'Animation' in m.get('category','') for m in res)


def test_cli_genre_output(capsys):
    # Running main with filters should print JSON containing known animation movie
    from movie_recommender import main
    main(['--genre', 'Animation', '--format', 'json'])
    out = capsys.readouterr().out
    assert 'Coco' in out or 'Toy Story' in out


def test_cli_list_genres(capsys):
    from movie_recommender import main
    main(['--list-genres'])
    out = capsys.readouterr().out
    import json as _json
    data = _json.loads(out)
    assert any(d.get('genre') == 'Animation' and d.get('count',0) > 0 for d in data)


def test_cli_list_categories(capsys):
    from movie_recommender import main
    main(['--list-categories'])
    out = capsys.readouterr().out
    import json as _json
    data = _json.loads(out)
    assert any(d.get('category') == 'Blockbuster' and d.get('count',0) > 0 for d in data)
