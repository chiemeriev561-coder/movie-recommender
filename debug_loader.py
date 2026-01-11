import logging
import os
import sys
from pathlib import Path
from movie_recommender import load_movies, logger

def debug_load_movies():
    # Set up logging to console
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    # Get the directory of the current script
    script_dir = Path(__file__).parent
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script directory: {script_dir}")
    
    # Define file paths
    movies_file = script_dir / 'movies_cleaned.csv'
    ratings_file = script_dir / 'ratings_cleaned.csv'
    
    # Check if files exist
    print(f"\nChecking files:")
    print(f"- Movies file: {movies_file} - {'EXISTS' if movies_file.exists() else 'MISSING'}")
    print(f"- Ratings file: {ratings_file} - {'EXISTS' if ratings_file.exists() else 'MISSING'}")
    
    if not movies_file.exists():
        print("\nError: movies_cleaned.csv not found in the script directory.")
        print("Please make sure the file exists and try again.")
        return
    
    # Try to load movies
    print("\nAttempting to load movies...")
    try:
        # First try with default settings
        print("\nTrying with default settings...")
        movies = load_movies(str(movies_file), str(ratings_file))
        print(f"Loaded {len(movies)} movies with default settings")
        
        # If no movies loaded, try with different encodings
        if not movies:
            print("\nTrying with different encodings...")
            for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                try:
                    with open(movies_file, 'r', encoding=encoding) as f:
                        first_line = f.readline()
                        print(f"First line with {encoding}: {first_line[:100]}...")
                except Exception as e:
                    print(f"Error reading with {encoding}: {str(e)}")
            
            # Try with different column mappings
            print("\nTrying with different column mappings...")
            column_mappings = [
                {'movie_id': 'movieId', 'title': 'title', 'year': 'year', 'genres': 'genres'},
                {'movie_id': 'movie_id', 'title': 'title', 'year': 'year', 'genres': 'genres'},
                {'movie_id': 'movieId', 'title': 'name', 'year': 'year', 'genres': 'genre'},
            ]
            
            for mapping in column_mappings:
                try:
                    print(f"\nTrying mapping: {mapping}")
                    movies = load_movies(str(movies_file), str(ratings_file), column_map=mapping)
                    print(f"Loaded {len(movies)} movies with mapping: {mapping}")
                    if movies:
                        print("\nFirst movie sample:")
                        print(movies[0])
                        break
                except Exception as e:
                    print(f"Error with mapping {mapping}: {str(e)}")
        
        # If we have movies, show some stats
        if movies:
            print("\nMovie loading successful! Here are some stats:")
            print(f"Total movies loaded: {len(movies)}")
            print(f"First movie: {movies[0]['name']} ({movies[0].get('year', 'N/A')})")
            print(f"Genres in first movie: {movies[0].get('genre', 'N/A')}")
            print(f"Rating: {movies[0].get('rating', 'N/A')} (from {movies[0].get('rating_count', 0)} ratings)")
            
            # Check if we have any ratings
            rated_movies = [m for m in movies if m.get('rating_count', 0) > 0]
            print(f"\nMovies with ratings: {len(rated_movies)}/{len(movies)}")
            if rated_movies:
                avg_rating = sum(m['rating'] for m in rated_movies) / len(rated_movies)
                print(f"Average rating: {avg_rating:.2f}/5.0")
                
    except Exception as e:
        print(f"\nError loading movies: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_load_movies()