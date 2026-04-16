import movie_recommender as mr


def test_genre_filter_does_not_match_category_text():
    results = mr.find_matches("", genre="classic", enable_fuzzy=False, max_results=20)

    assert results == []


def test_category_filter_matches_category_text():
    results = mr.find_matches("", category="classic", enable_fuzzy=False, max_results=20)

    assert results
    assert all("classic" in movie["category"].lower() for movie in results)


def test_genre_filter_uses_all_genres_from_csv_rows():
    results = mr.find_matches("", genre="Animation", enable_fuzzy=False, max_results=200)
    names = {movie["name"] for movie in results}

    assert "Toy Story" in names


def test_remove_favorite_rolls_back_when_save_fails(monkeypatch, tmp_path):
    favorites_path = tmp_path / "favorites.json"
    mr.load_favorites(str(favorites_path))
    mr.add_favorite("Inception", 2010, path=str(favorites_path))

    def fail_write(path, payload):
        raise OSError("disk full")

    monkeypatch.setattr(mr, "_atomic_write_json", fail_write)

    removed = mr.remove_favorite("Inception", 2010, path=str(favorites_path))

    assert removed is False
    assert mr.favorites == [{"name": "Inception", "year": 2010}]
    assert mr._favorites_set == {("inception", 2010)}


def test_get_favorite_movies_returns_matching_movie_details():
    mr.favorites = [{"name": "Spider-Man: No Way Home", "year": 2021}]
    mr._favorites_set = {("spider-man: no way home", 2021)}

    favorite_movies = mr.get_favorite_movies()

    assert len(favorite_movies) == 1
    assert favorite_movies[0]["name"] == "Spider-Man: No Way Home"
    assert favorite_movies[0]["year"] == 2021
