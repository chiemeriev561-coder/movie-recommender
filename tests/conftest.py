from copy import deepcopy

import pytest

import movie_recommender as mr


@pytest.fixture(autouse=True)
def restore_recommender_state():
    original_movies = [deepcopy(movie) for movie in mr.movies]
    original_favorites = deepcopy(mr.favorites)
    original_favorites_set = mr._favorites_set.copy()
    original_last_save_error = mr.last_save_error

    yield

    mr.movies.clear()
    mr.movies.extend(original_movies)
    mr.favorites = original_favorites
    mr._favorites_set = original_favorites_set
    mr.last_save_error = original_last_save_error
