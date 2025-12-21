import json

def show_sample():
    try:
        # Load the expanded movies
        with open('expanded_movies.json', 'r', encoding='utf-8') as f:
            movies = json.load(f)
        
        print(f"Total movies in dataset: {len(movies)}")
        print("\nSample of expanded dataset (first 5 movies):")
        print("-" * 80)
        
        # Show first 5 movies
        for i, movie in enumerate(movies[:5], 1):
            print(f"MOVIE {i}:")
            print(f"  Name: {movie.get('name')}")
            print(f"  Year: {movie.get('year')}")
            print(f"  Genre: {movie.get('genre')}")
            print(f"  Category: {movie.get('category')}")
            print(f"  Rating: {movie.get('rating')}/10")
            print(f"  Box Office: ${movie.get('box_office_millions'):.1f}M")
            print("-" * 80)
            
        # Show some statistics
        years = [m['year'] for m in movies]
        ratings = [m['rating'] for m in movies]
        
        print("\nDataset Statistics:")
        print(f"- Year range: {min(years)} - {max(years)}")
        print(f"- Average rating: {sum(ratings)/len(ratings):.2f}/10")
        print(f"- Total box office: ${sum(m['box_office_millions'] for m in movies):.1f}M")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == '__main__':
    show_sample()
