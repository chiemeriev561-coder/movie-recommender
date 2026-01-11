from movie_recommender import load_movies

# Load the movies
movies = load_movies('movies_cleaned.csv', 'ratings_cleaned.csv')

# Display the first 10 movies
print("First 10 movies:")
for i, movie in enumerate(movies[:10], 1):
    print(f"{i}. {movie['name']} ({movie.get('year', 'N/A')})")
    print(f"   Genres: {movie.get('genre', 'N/A')}")
    print(f"   Rating: {movie.get('rating', 'N/A')} (from {movie.get('rating_count', 0)} ratings)")
    print()