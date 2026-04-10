import csv_loader


def test_load_movies_from_csv_loads_full_dataset():
    movies = csv_loader.load_movies_from_csv()

    assert len(movies) > 9000
    assert movies[0]["name"] == "Toy Story"
    assert movies[0]["year"] == 1995
    assert movies[0]["genre"] == "Adventure"
    assert "Animation" in movies[0]["all_genres"]
