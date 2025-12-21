import json
import pytest
from pathlib import Path
from movie_recommender import (
    add_favorite, load_favorites, get_favorite_entries, 
    get_favorite_movies, remove_favorite, get_last_save_error,
    FAVORITES_FILE, movies
)


def test_add_and_load_favorites(tmp_path):
    """Test basic add, load, and remove favorite functionality."""
    favfile = tmp_path / 'favs.json'
    
    # Test initial load with non-existent file
    load_favorites(str(favfile))
    assert get_favorite_entries() == []
    assert not favfile.exists()  # Shouldn't create file for empty favorites

    # Add a known movie from dataset
    assert add_favorite('Inception', 2010, path=str(favfile))
    assert favfile.exists()

    # Verify file content
    with open(favfile, 'r', encoding='utf-8') as f:
        favs = json.load(f)
    assert isinstance(favs, list)
    assert {'name': 'Inception', 'year': 2010} in favs

    # Test loading favorites
    loaded = load_favorites(str(favfile))
    assert isinstance(loaded, list)
    assert {'name': 'Inception', 'year': 2010} in loaded

    # Test get_favorite_movies returns the resolved movie dicts
    fm = get_favorite_movies()
    assert any(m['name'] == 'Inception' and m['year'] == 2010 for m in fm)

    # Test removing a favorite
    assert remove_favorite('Inception', 2010, path=str(favfile))
    loaded2 = load_favorites(str(favfile))
    assert {'name': 'Inception', 'year': 2010} not in loaded2


def test_duplicate_favorites(tmp_path):
    """Test that duplicate favorites are handled correctly."""
    favfile = tmp_path / 'favs_dup.json'
    
    # Add movie twice
    assert add_favorite('The Matrix', 1999, path=str(favfile))
    assert not add_favorite('The Matrix', 1999, path=str(favfile))  # Should return False for duplicate
    
    # Verify only one entry exists
    loaded = load_favorites(str(favfile))
    assert len(loaded) == 1
    assert loaded.count({'name': 'The Matrix', 'year': 1999}) == 1


def test_nonexistent_movie(tmp_path):
    """Test adding a movie that doesn't exist in the dataset."""
    favfile = tmp_path / 'favs_nonexistent.json'
    
    # Try to add a movie that doesn't exist
    assert not add_favorite('Nonexistent Movie', 9999, path=str(favfile))
    assert not favfile.exists()  # File shouldn't be created for invalid adds


def test_invalid_inputs():
    """Test handling of invalid inputs."""
    # Invalid year
    assert not add_favorite('Inception', 'not a year')
    
    # Empty name
    assert not add_favorite('', 2020)
    
    # None values
    assert not add_favorite('Inception', None)  # Invalid year


def test_favorites_persistence(tmp_path):
    """Test that favorites persist between loads."""
    favfile = tmp_path / 'favs_persist.json'
    
    # Add some favorites
    add_favorite('Inception', 2010, path=str(favfile))
    add_favorite('The Matrix', 1999, path=str(favfile))
    
    # Reload and verify
    load_favorites(str(favfile))
    entries = get_favorite_entries()
    assert len(entries) == 2
    assert {'name': 'Inception', 'year': 2010} in entries
    assert {'name': 'The Matrix', 'year': 1999} in entries


def test_remove_nonexistent_favorite(tmp_path):
    """Test removing a favorite that doesn't exist."""
    favfile = tmp_path / 'favs_remove.json'
    
    # Ensure we start with a clean state
    load_favorites(str(favfile))
    
    # Remove non-existent favorite
    assert not remove_favorite('Nonexistent', 2020, path=str(favfile))
    
    # Add a movie to the dataset for testing
    test_movie = {
        'name': 'Test Movie for Removal',
        'year': 2023,
        'category': 'Test',
        'genre': 'Test',
        'box_office_millions': 1.0,
        'rating': 5.0
    }
    
    # Add the test movie to the dataset
    import movie_recommender
    movie_recommender.movies.append(test_movie)
    
    try:
        # Add the test movie to favorites
        assert add_favorite('Test Movie for Removal', 2023, path=str(favfile))
        
        # Try to remove with wrong year
        assert not remove_favorite('Test Movie for Removal', 2020, path=str(favfile))
        
        # Try to remove with wrong name
        assert not remove_favorite('Nonexistent', 2023, path=str(favfile))
        
        # Original favorite should still be there
        load_favorites(str(favfile))
        entries = get_favorite_entries()
        assert any(m['name'] == 'Test Movie for Removal' and m['year'] == 2023 for m in entries)
    finally:
        # Clean up
        movie_recommender.movies = [m for m in movie_recommender.movies 
                                  if m['name'] != 'Test Movie for Removal']


def test_save_error_handling(tmp_path, monkeypatch):
    """Test error handling when saving favorites fails."""
    # Save the current state
    import movie_recommender
    original_favorites = movie_recommender.favorites.copy()
    original_save = movie_recommender.save_favorites
    
    try:
        # Mock the save function to always fail
        def mock_save_favorites(path=FAVORITES_FILE):
            return False
        
        # Apply the mock
        monkeypatch.setattr(movie_recommender, 'save_favorites', mock_save_favorites)
        
        # Reset favorites
        movie_recommender.favorites = []
        movie_recommender._favorites_set = set()
        
        # Add a test movie to the dataset
        test_movie = {
            'name': 'Test Movie for Save',
            'year': 2023,
            'category': 'Test',
            'genre': 'Test',
            'box_office_millions': 1.0,
            'rating': 5.0
        }
        
        # Add the test movie to the dataset
        original_movies = movie_recommender.movies.copy()
        movie_recommender.movies.append(test_movie)
        
        try:
            # Try to add a favorite - should fail due to mock
            assert not add_favorite('Test Movie for Save', 2023)
            
            # Verify the global state wasn't modified
            assert len(get_favorite_entries()) == 0
        finally:
            # Clean up
            movie_recommender.movies = original_movies
    finally:
        # Restore the original state
        movie_recommender.favorites = original_favorites
        movie_recommender.save_favorites = original_save
