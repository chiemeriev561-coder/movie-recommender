# Movie Recommender API Documentation

## Overview

This REST API provides movie recommendation functionality including search, filtering, favorites management, and more. The API is built with FastAPI and includes automatic interactive documentation.

## Quick Start

1. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Start the API server:**
   ```bash
   python run_api.py
   ```
   or
   ```bash
   uvicorn api:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Access the API:**
   - Interactive docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc
   - Health check: http://localhost:8000/api/health

## Endpoints

### Base URL
```
http://localhost:8000
```

### 1. Root Endpoint
```
GET /
```
Returns basic API information and statistics.

**Response:**
```json
{
  "message": "Movie Recommender API",
  "version": "1.0.0",
  "docs": "/docs",
  "redoc": "/redoc",
  "total_movies": 25,
  "favorites_count": 0
}
```

### 2. Movie Search
```
GET /api/movies/search
```
Search for movies with optional filters and sorting.

**Query Parameters:**
- `q` (optional): Search query (movie name, genre, etc.)
- `genre` (optional): Filter by genre
- `category` (optional): Filter by category
- `min_rating` (optional): Minimum rating (0-10)
- `year` (optional): Filter by exact year
- `year_from` (optional): Year range start
- `year_to` (optional): Year range end
- `sort_by` (optional): Sort by 'rating', 'box_office', or 'year'
- `fuzzy` (optional): Enable fuzzy matching (default: true)
- `max_results` (optional): Maximum results (1-200, default: 50)

**Examples:**
```bash
# Search for action movies
curl "http://localhost:8000/api/movies/search?q=action"

# Get movies with rating >= 8.0
curl "http://localhost:8000/api/movies/search?min_rating=8.0"

# Get 2021 movies sorted by box office
curl "http://localhost:8000/api/movies/search?year=2021&sort_by=box_office"
```

### 3. Top Rated Movies
```
GET /api/movies/top?limit=10
```
Get top-rated movies sorted by rating.

**Parameters:**
- `limit`: Number of movies to return (1-50, default: 10)

### 4. Genres
```
GET /api/genres
```
Get all available genres with movie counts.

**Response:**
```json
[
  {"genre": "Action", "count": 8},
  {"genre": "Drama", "count": 5},
  ...
]
```

### 5. Categories
```
GET /api/categories
```
Get all available categories with movie counts.

### 6. Favorites Management

#### Get Favorites
```
GET /api/favorites
```
Get all favorite movies with full details.

#### Add to Favorites
```
POST /api/favorites
```
Add a movie to favorites.

**Request Body:**
```json
{
  "name": "Inception",
  "year": 2010
}
```

#### Remove from Favorites
```
DELETE /api/favorites
```
Remove a movie from favorites.

**Request Body:**
```json
{
  "name": "Inception",
  "year": 2010
}
```

### 7. Movie Details
```
GET /api/movies/{name}/{year}
```
Get detailed information about a specific movie.

**Example:**
```bash
curl "http://localhost:8000/api/movies/Inception/2010"
```

### 8. Health Check
```
GET /api/health
```
Check API health and get basic statistics.

## Data Models

### Movie Response
```json
{
  "name": "Inception",
  "year": 2010,
  "category": "Prestige",
  "genre": "Sci-Fi",
  "box_office_millions": 829.9,
  "rating": 8.8
}
```

### Favorite Request
```json
{
  "name": "Inception",
  "year": 2010
}
```

## Error Handling

The API returns standard HTTP status codes:

- `200 OK`: Successful request
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

**Error Response Format:**
```json
{
  "detail": "Error message description"
}
```

## Features

### Search Capabilities
- **Exact matching**: Movie names, genres, categories
- **Fuzzy matching**: Intelligent typo tolerance (enabled by default)
- **Filtering**: By genre, category, rating, year ranges
- **Sorting**: By rating, box office, year

### Favorites System
- Persistent storage in `favorites.json`
- Add/remove movies by name and year
- Automatic validation against movie database

### Performance
- In-memory movie dataset for fast access
- Optimized fuzzy search with RapidFuzz
- Efficient filtering and sorting

## Development

### Running in Development Mode
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### Running in Production
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4
```

## Testing the API

### Using curl
```bash
# Basic search
curl "http://localhost:8000/api/movies/search?q=batman"

# With filters
curl "http://localhost:8000/api/movies/search?genre=Action&min_rating=7.5"

# Add to favorites
curl -X POST "http://localhost:8000/api/favorites" \
  -H "Content-Type: application/json" \
  -d '{"name": "The Dark Knight", "year": 2008}'
```

### Using Python requests
```python
import requests

# Search movies
response = requests.get("http://localhost:8000/api/movies/search", 
                       params={"q": "action", "min_rating": 8.0})
movies = response.json()

# Add to favorites
response = requests.post("http://localhost:8000/api/favorites",
                        json={"name": "Inception", "year": 2010})
```

## Configuration

### Environment Variables
- `VIRTUAL_ENV`: Virtual environment path (checked by startup script)

### Dataset
- Movies are loaded from the built-in dataset in `movie_recommender.py`
- Favorites are persisted in `favorites.json`
- Dataset can be expanded using the `expand_dataset_if_needed()` function

## Troubleshooting

### Common Issues

1. **Port already in use**: Change port with `--port` flag
2. **Module not found**: Ensure virtual environment is activated
3. **CORS issues**: Add CORS middleware if accessing from web browsers

### Logs
The API provides detailed logging for:
- Search queries and results
- Favorites operations
- Errors and exceptions

## License

This API is part of the Movie Recommender project.
