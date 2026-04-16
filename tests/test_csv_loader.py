import csv_loader


def test_load_movies_from_csv_loads_full_dataset():
    movies = csv_loader.load_movies_from_csv()
    sample_movie = movies[0]

    assert len(movies) > 4000
    assert {"name", "year", "category", "genre", "box_office_millions", "rating", "movieId", "all_genres"} <= sample_movie.keys()
    assert isinstance(sample_movie["all_genres"], list)
    assert any("Animation" in movie["all_genres"] for movie in movies)
