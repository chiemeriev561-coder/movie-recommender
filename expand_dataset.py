import movie_recommender
import json

def expand_and_save():
    # First, let's see how many movies we have
    print(f"Initial movie count: {len(movie_recommender.movies)}")
    
    # Expand the dataset to 2000 movies
    print("Expanding dataset to 2000 movies...")
    movie_recommender.expand_dataset_if_needed(min_total=2000, auto_save=False)
    
    # Verify the expansion
    print(f"Current movie count after expansion: {len(movie_recommender.movies)}")
    
    # Save the expanded dataset
    output_file = 'expanded_movies.json'
    print(f"Saving expanded dataset to {output_file}...")
    
    # Save using the movie_recommender's save function if available
    if hasattr(movie_recommender, 'save_movies'):
        success = movie_recommender.save_movies(output_file, movie_recommender.movies)
        if success:
            print(f"Successfully saved {len(movie_recommender.movies)} movies to {output_file}")
        else:
            print(f"Failed to save movies: {movie_recommender.get_last_save_error() or 'Unknown error'}")
    else:
        # Fallback to direct JSON serialization
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(movie_recommender.movies, f, indent=2)
            print(f"Successfully saved {len(movie_recommender.movies)} movies to {output_file}")
        except Exception as e:
            print(f"Error saving movies: {str(e)}")

if __name__ == '__main__':
    expand_and_save()
