# Movie Recommender API Documentation

## Overview

This REST API provides movie recommendation functionality including search, filtering, favorites management, and more. The API is built with FastAPI and includes automatic interactive documentation.

This API sources recommendations and metadata exclusively from TMDB. `TMDB_API_KEY` must be configured for recommendation, search, trending, and trailer endpoints to function.

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

- Interactive docs: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health check: <http://localhost:8000/api/health>

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

### 3. Trending Movies

```
GET /api/movies/trending
```

Fetch trending movies from TMDB API. Local CSV fallback has been removed; TMDB is the single source of truth for trending and recommendation data.

**Response:**

```json
[
  {
    "id": 693134,
    "name": "Dune: Part Two",
    "year": 2024,
    "category": "Trending",
    "genre": "Sci-Fi",
    "box_office_millions": null,
    "rating": 8.3,
    "poster_url": "https://image.tmdb.org/t/p/w500/8b8R8Pbd9uYvvw907XvUznv9v.jpg"
  }
]
```

### 4. Movie Trailer

```
GET /api/movies/{movie_id}/trailer
```

Fetch the best available YouTube trailer for a TMDB movie ID.

This endpoint prefers:

- Official YouTube trailers
- Other YouTube trailers
- Other YouTube videos

**Example:**

```bash
curl "http://localhost:8000/api/movies/550/trailer"
```

**Response:**

```json
{
  "youtube_key": "SUXWAEX2jlg"
}
```

**Common errors:**

- `404 Not Found`: movie does not exist on TMDB or no YouTube trailer was found
- `503 Service Unavailable`: `TMDB_API_KEY` is not configured
- `502 Bad Gateway`: TMDB request failed

### 5. Movie Streaming

```
GET /api/movies/{movie_id}/stream
```

Get the high-speed streaming embed URL for a given TMDB movie ID.

**Example:**

```bash
curl "http://localhost:8000/api/movies/550/stream"
```

**Response:**

```json
{
  "movie_id": "550",
  "stream_url": "https://vidlink.pro/movie/550",
  "provider": "Phlox Premium Secure Stream",
  "fallback_stream_url": "https://nontongo.win/movie/550",
  "fallback_provider": "Nontongo.win"
}
```

### 6. Movie Downloads

```
GET /api/movies/{movie_id}/downloads
```

Get available multi-quality torrent download links (`.torrent`) and magnet links for a given movie. Supports TMDB ID (e.g. `550`) or IMDB ID (e.g. `tt0137523`). Results are cached for 24 hours.

**Example:**

```bash
curl "http://localhost:8000/api/movies/550/downloads"
```

**Response:**

```json
{
  "movie_id": "550",
  "imdb_id": "tt0137523",
  "title": "Fight Club",
  "year": 1999,
  "available": true,
  "downloads": [
    {
      "quality": "720p",
      "type": "bluray",
      "size": "1.25 GB",
      "size_bytes": 1342177280,
      "seeds": 100,
      "peers": 25,
      "info_hash": "0FACFB2D11C9A8F15281A909B45084E6425EF2F0",
      "torrent_url": "https://yts.gg/torrent/download/0FACFB2D11C9A8F15281A909B45084E6425EF2F0",
      "magnet_url": "magnet:?xt=urn:btih:0FACFB2D11C9A8F15281A909B45084E6425EF2F0&dn=Fight%20Club&tr=udp%3A//tracker.opentrackr.org%3A1337/announce..."
    },
    {
      "quality": "1080p",
      "type": "bluray",
      "size": "2.40 GB",
      "size_bytes": 2576980377,
      "seeds": 250,
      "peers": 40,
      "info_hash": "...",
      "torrent_url": "https://yts.gg/torrent/download/...",
      "magnet_url": "magnet:?xt=urn:btih:..."
    }
  ]
}
```

### 7. Local qBittorrent Integration

The optional qBittorrent integration adds torrents to a qBittorrent instance running on the same computer. Configure `QBITTORRENT_URL`, `QBITTORRENT_USERNAME`, `QBITTORRENT_PASSWORD`, and optionally `QBITTORRENT_DOWNLOAD_DIR` in `.env`.

Check the connection:

```text
GET /api/qbittorrent/status
```

Add a movie to qBittorrent:

```text
POST /api/movies/{movie_id}/qbittorrent?quality=1080p
```

View download progress:

```text
GET /api/qbittorrent/torrents
```

### 8. Top Rated Movies

```
GET /api/movies/top?limit=10
```

Get top-rated movies sorted by rating.

**Parameters:**

- `limit`: Number of movies to return (1-50, default: 10)

### 7. Genres

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

### 8. Categories

```
GET /api/categories
```

Get all available categories with movie counts.

### 9. Favorites Management

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

### 10. Movie Details

```
GET /api/movies/{name}/{year}
```

Get detailed information about a specific movie.

**Example:**

```bash
curl "http://localhost:8000/api/movies/Inception/2010"
```

### 11. Health Check

```
GET /api/health
```

Check API health and get basic statistics.

### 12. Statistics

```
GET /api/statistics
```

Get detailed statistics about movie dataset (sourced from TMDB).

### 13. Hybrid Recommendations

```
GET /api/recommendations/hybrid
```

Return TMDB candidates re-ranked with content-based similarity. Candidates
come from TMDB recommendations/similar movies when `tmdb_id` is provided and
are supplemented with TMDB discover results. If the caller has favorites,
content scoring is personalized against those favorites.

**Query Parameters:**

- `tmdb_id` (optional): TMDB movie ID to use as the recommendation source.
- `genres` (optional): Comma-separated genre names, for example `Action,Sci-Fi`.
- `year_min`, `year_max` (optional): Release-year bounds.
- `rating_min` (optional): Minimum TMDB rating.
- `limit` (optional): Number of results, 1-50 (default: 20).
- `tmdb_weight` (optional): TMDB popularity/rank weight, 0.0-1.0 (default: 0.4).
- `content_weight` (optional): Content-similarity weight, 0.0-1.0 (default: 0.6).

The final score is:

```
hybrid_score = (tmdb_score * tmdb_weight) + (content_score * content_weight)
```

Both scores are normalized to approximately 0-1. The response's
`similarity_score` contains the hybrid score, and `match_reason` includes the
TMDB and content components.

**Example:**

```bash
curl "http://localhost:8000/api/recommendations/hybrid?tmdb_id=550&limit=10&tmdb_weight=0.3&content_weight=0.7"
```

**Caching:**

Completed hybrid responses are cached for 30 minutes. The cache key includes
the movie, filters, limit, both weights, and the requesting user's favorite
movies, so changing any scoring input creates a fresh result.

**Response shape:**

```json
{
  "recommendations": [
    {
      "movie": {
        "id": 680,
        "name": "Pulp Fiction",
        "year": 1994,
        "category": "TMDB",
        "genre": "Crime, Drama",
        "rating": 8.5,
        "poster_url": "https://image.tmdb.org/t/p/w500/example.jpg"
      },
      "similarity_score": 0.7421,
      "match_reason": "Hybrid: TMDB score 0.68 + Content score 0.78"
    }
  ],
  "based_on": {
    "tmdb_id": 550,
    "weights": {"tmdb": 0.3, "content": 0.7},
    "favorites_count": 0
  },
  "total_available": 1
}
```

## Data Models

### Movie Response

```json
{
  "id": 550,
  "name": "Inception",
  "year": 2010,
  "category": "Prestige",
  "genre": "Sci-Fi",
  "box_office_millions": 829.9,
  "rating": 8.8,
  "poster_url": "https://image.tmdb.org/t/p/w500/example.jpg"
}
```

`id` is optional and is populated for TMDB-backed results such as `/api/movies/trending` and TMDB search matches.

### Trailer Response

```json
{
  "youtube_key": "SUXWAEX2jlg"
}
```

### Stream Response

```json
{
  "movie_id": "550",
  "stream_url": "https://vidsrc.cc/v2/embed/movie/550",
  "provider": "Phlox Premium Secure Stream"
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

- All movie metadata and recommendations are sourced from TMDB only; local CSV datasets are no longer used.
- Favorites are persisted in `favorites.json`.
- The server requires `TMDB_API_KEY` to be set for recommendation, search, trending, and trailer functionality.

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
 http://127.0.0.1:8080