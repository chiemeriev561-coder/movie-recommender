import movie_recommender

def verify_dataset():
    # 1. Check total count
    total_movies = len(movie_recommender.movies)
    print(f"1. Total movies in dataset: {total_movies}")
    
    # 2. Check structure of first few movies
    print("\n2. Sample movies (first 3):")
    for i, movie in enumerate(movie_recommender.movies[:3], 1):
        print(f"   Movie {i}:")
        for key, value in movie.items():
            print(f"     {key}: {value}")
    
    # 3. Check year distribution
    years = [m['year'] for m in movie_recommender.movies]
    year_min, year_max = min(years), max(years)
    print(f"\n3. Year range: {year_min} - {year_max}")
    
    # 4. Check rating distribution
    ratings = [m['rating'] for m in movie_recommender.movies]
    avg_rating = sum(ratings) / len(ratings)
    print(f"4. Average rating: {avg_rating:.2f}/10")
    print(f"   Min rating: {min(ratings):.1f}")
    print(f"   Max rating: {max(ratings):.1f}")
    
    # 5. Check genres
    genres = {}
    for m in movie_recommender.movies:
        for genre in m['genre'].split('/'):
            genres[genre.strip()] = genres.get(genre.strip(), 0) + 1
    print("\n5. Genre distribution:")
    for genre, count in sorted(genres.items(), key=lambda x: x[1], reverse=True):
        print(f"   {genre}: {count} movies")
    
    # 6. Verify required fields
    required_fields = {'name', 'year', 'genre', 'category', 'rating', 'box_office_millions'}
    missing_fields = []
    for m in movie_recommender.movies:
        missing = required_fields - set(m.keys())
        if missing:
            missing_fields.append((m['name'], missing))
    
    if missing_fields:
        print("\n6. Missing fields found:")
        for name, fields in missing_fields[:5]:
            print(f"   {name}: Missing {', '.join(fields)}")
        if len(missing_fields) > 5:
            print(f"   ... and {len(missing_fields) - 5} more")
    else:
        print("\n6. All movies have all required fields")

if __name__ == '__main__':
    verify_dataset()
