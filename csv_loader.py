"""
CSV Data Loader for Movie Recommender
Loads movies and ratings from CSV files and integrates with the existing dataset
"""

import csv
import logging
import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
import statistics
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Default CSV paths from environment variables
MOVIES_CSV_PATH = os.getenv('MOVIES_CSV_PATH', 'movies_cleaned.csv')
RATINGS_CSV_PATH = os.getenv('RATINGS_CSV_PATH', 'ratings_cleaned.csv')

def load_movies_from_csv(movies_csv_path: str = MOVIES_CSV_PATH) -> List[Dict[str, Any]]:
    """
    Load movies from the CSV file and convert to the expected format.
    
    Args:
        movies_csv_path: Path to the movies CSV file
        
    Returns:
        List of movie dictionaries in the expected format
    """
    movies = []
    csv_path = Path(movies_csv_path)
    
    if not csv_path.exists():
        logger.warning(f"Movies CSV file not found: {movies_csv_path}")
        return movies
    
    try:
        with csv_path.open('r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                try:
                    # Extract basic info
                    movie_id = int(row['movieId'])
                    title = row['title'].strip()
                    year = row['year'].strip()
                    genres = row['genres'].strip()
                    
                    # Parse year - some entries might have year in title
                    year_int = None
                    if year.isdigit():
                        year_int = int(year)
                    else:
                        # Try to extract year from title
                        year_match = re.search(r'\((\d{4})\)', title)
                        if year_match:
                            year_int = int(year_match.group(1))
                        else:
                            # Default to a reasonable year if not found
                            year_int = 2000
                    
                    # Clean title - remove year from title if present
                    clean_title = re.sub(r'\s*\(\d{4}\)$', '', title).strip()
                    
                    # Map genres to categories and determine primary genre
                    genre_list = [g.strip() for g in genres.split('|') if g.strip() and g != '(no genres listed)']
                    
                    # Determine category based on genres and other factors
                    category = determine_category(genre_list, year_int)
                    primary_genre = genre_list[0] if genre_list else "Unknown"
                    
                    # Create movie entry with required fields
                    movie = {
                        'name': clean_title,
                        'year': year_int,
                        'category': category,
                        'genre': primary_genre,  # Use primary genre for simplicity
                        'box_office_millions': 0.0,  # Not available in CSV
                        'rating': 0.0,  # Will be updated from ratings
                        'movieId': movie_id,  # Keep original ID
                        'all_genres': genre_list  # Store all genres for reference
                    }
                    
                    movies.append(movie)
                    
                except Exception as e:
                    logger.warning(f"Error processing movie row {row}: {e}")
                    continue
                    
        logger.info(f"Successfully loaded {len(movies)} movies from {movies_csv_path}")
        return movies
        
    except Exception as e:
        logger.exception(f"Failed to load movies from CSV {movies_csv_path}: {e}")
        return movies

def load_ratings_from_csv(ratings_csv_path: str = RATINGS_CSV_PATH) -> Dict[int, List[float]]:
    """
    Load ratings from CSV and organize by movie ID.
    
    Args:
        ratings_csv_path: Path to the ratings CSV file
        
    Returns:
        Dictionary mapping movieId to list of ratings
    """
    ratings_by_movie = defaultdict(list)
    csv_path = Path(ratings_csv_path)
    
    if not csv_path.exists():
        logger.warning(f"Ratings CSV file not found: {ratings_csv_path}")
        return dict(ratings_by_movie)
    
    try:
        with csv_path.open('r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                try:
                    movie_id = int(row['movieId'])
                    rating = float(row['rating'])
                    ratings_by_movie[movie_id].append(rating)
                except Exception as e:
                    logger.warning(f"Error processing rating row {row}: {e}")
                    continue
                    
        logger.info(f"Successfully loaded ratings for {len(ratings_by_movie)} movies from {ratings_csv_path}")
        return dict(ratings_by_movie)
        
    except Exception as e:
        logger.exception(f"Failed to load ratings from CSV {ratings_csv_path}: {e}")
        return dict(ratings_by_movie)

def determine_category(genres: List[str], year: int) -> str:
    """
    Determine movie category based on genres and year.
    
    Args:
        genres: List of genres
        year: Release year
        
    Returns:
        Category string
    """
    if not genres:
        return "Other"
    
    # Convert to lowercase for matching
    genres_lower = [g.lower() for g in genres]
    
    # Define category rules
    if any(g in genres_lower for g in ['animation', 'children']):
        return "Animation"
    elif any(g in genres_lower for g in ['action', 'adventure']):
        if year >= 2010:
            return "Blockbuster"
        else:
            return "Classic"
    elif any(g in genres_lower for g in ['sci-fi', 'fantasy']):
        return "Prestige"
    elif any(g in genres_lower for g in ['drama', 'romance']):
        return "Classic"
    elif any(g in genres_lower for g in ['comedy']):
        if year >= 2015:
            return "Streaming"
        else:
            return "Classic"
    elif any(g in genres_lower for g in ['thriller', 'crime', 'mystery']):
        return "Indie"
    elif any(g in genres_lower for g in ['horror']):
        return "Indie"
    elif any(g in genres_lower for g in ['documentary', 'biography']):
        return "Prestige"
    else:
        return "Other"

def calculate_average_ratings(movies: List[Dict[str, Any]], ratings_by_movie: Dict[int, List[float]]) -> List[Dict[str, Any]]:
    """
    Calculate average ratings for movies and update the movie entries.
    
    Args:
        movies: List of movie dictionaries
        ratings_by_movie: Dictionary mapping movieId to list of ratings
        
    Returns:
        Updated list of movies with average ratings
    """
    updated_movies = []
    
    for movie in movies:
        movie_copy = movie.copy()
        movie_id = movie.get('movieId')
        
        if movie_id and movie_id in ratings_by_movie:
            ratings = ratings_by_movie[movie_id]
            if ratings:
                avg_rating = round(statistics.mean(ratings), 1)
                movie_copy['rating'] = avg_rating
            else:
                movie_copy['rating'] = 0.0
        else:
            # No ratings available, use default
            movie_copy['rating'] = 0.0
        
        updated_movies.append(movie_copy)
    
    return updated_movies

def integrate_csv_data(builtin_movies: List[Dict[str, Any]], 
                      movies_csv_path: str = MOVIES_CSV_PATH,
                      ratings_csv_path: str = RATINGS_CSV_PATH) -> List[Dict[str, Any]]:
    """
    Integrate CSV data with built-in movies.
    
    Args:
        builtin_movies: List of built-in movies
        movies_csv_path: Path to movies CSV file
        ratings_csv_path: Path to ratings CSV file
        
    Returns:
        Combined list of movies
    """
    logger.info("Starting CSV data integration...")
    
    # Load movies from CSV
    csv_movies = load_movies_from_csv(movies_csv_path)
    
    # Load ratings
    ratings_by_movie = load_ratings_from_csv(ratings_csv_path)
    
    # Calculate average ratings for CSV movies
    csv_movies_with_ratings = calculate_average_ratings(csv_movies, ratings_by_movie)
    
    # Combine with built-in movies
    # Create a set to track existing movies (name + year)
    existing_movies = {(m['name'].lower(), m['year']) for m in builtin_movies}
    
    # Add CSV movies that don't duplicate built-in movies
    new_movies = []
    for movie in csv_movies_with_ratings:
        key = (movie['name'].lower(), movie['year'])
        if key not in existing_movies:
            new_movies.append(movie)
            existing_movies.add(key)
    
    # Combine all movies
    all_movies = builtin_movies + new_movies
    
    logger.info(f"Integration complete: {len(builtin_movies)} built-in + {len(new_movies)} CSV = {len(all_movies)} total movies")
    
    return all_movies

def get_csv_statistics(movies_csv_path: str = MOVIES_CSV_PATH, 
                       ratings_csv_path: str = RATINGS_CSV_PATH) -> Dict[str, Any]:
    """
    Get statistics about the CSV data.
    
    Args:
        movies_csv_path: Path to movies CSV file
        ratings_csv_path: Path to ratings CSV file
        
    Returns:
        Dictionary with statistics
    """
    try:
        movies = load_movies_from_csv(movies_csv_path)
        ratings_by_movie = load_ratings_from_csv(ratings_csv_path)
        
        # Calculate statistics
        total_ratings = sum(len(ratings) for ratings in ratings_by_movie.values())
        movies_with_ratings = len([m for m in movies if m.get('movieId') in ratings_by_movie])
        
        # Genre distribution
        genre_counts = defaultdict(int)
        for movie in movies:
            for genre in movie.get('all_genres', []):
                genre_counts[genre] += 1
        
        # Year distribution
        year_counts = defaultdict(int)
        for movie in movies:
            year_counts[movie['year']] += 1
        
        return {
            'total_movies': len(movies),
            'movies_with_ratings': movies_with_ratings,
            'total_ratings': total_ratings,
            'average_ratings_per_movie': round(total_ratings / len(movies), 2) if movies else 0,
            'genre_distribution': dict(sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            'year_range': {
                'earliest': min(year_counts.keys()) if year_counts else None,
                'latest': max(year_counts.keys()) if year_counts else None
            }
        }
        
    except Exception as e:
        logger.exception(f"Error calculating CSV statistics: {e}")
        return {'error': str(e)}
