# Movie Recommender

A robust movie recommendation system with a FastAPI REST API and an interactive command-line interface.

**Live Demo:** [https://movie-recommender-7zqv.onrender.com/](https://movie-recommender-7zqv.onrender.com/)

## Features

- **REST API**: FastAPI-powered endpoints for search, favorites, statistics, and TMDB trailer lookup.
- **Interactive CLI**: Command-line tool for searching and managing favorites.
- **Fuzzy Search**: Typo-tolerant movie searching (powered by RapidFuzz).
- **Data Integration**: Combines built-in movies with external CSV datasets and live TMDB metadata.
- **Deployment Ready**: Configured for production with Gunicorn/Uvicorn and environment variables.

## API Documentation

When running the server, you can access the interactive API documentation at:

- **Swagger UI**: [https://movie-recommender-7zqv.onrender.com/docs](https://movie-recommender-7zqv.onrender.com/docs)
- **ReDoc**: [https://movie-recommender-7zqv.onrender.com/redoc](https://movie-recommender-7zqv.onrender.com/redoc)

## Installation

Recommended: create and activate a virtual environment, then install dependencies:

```bash
python -m venv venv
source venv/bin/activate    # Linux/macOS
# or
.\venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## Configuration

Copy the template environment file and adjust as needed:

```bash
cp .env.template .env
```

Key configuration options in `.env`:
- `PORT`: API port (default: 8000)
- `TMDB_API_KEY`: The Movie Database API key used for trending movies and trailer lookup
- `ALLOWED_ORIGINS`: Comma-separated CORS allowed origins
- `ALLOWED_ORIGIN_REGEX`: Optional regex for additional allowed origins such as Lovable preview URLs
- `FAVORITES_FILE`: Path to store favorites JSON
- `MOVIES_CSV_PATH`: Path to movies dataset
- `RATINGS_CSV_PATH`: Path to ratings dataset

If you want TMDB-powered posters, movie IDs, and trailers, set:

```bash
TMDB_API_KEY=your_tmdb_api_key
```

## Running the Application

### Start the API Server

```bash
python run_api.py
```

For production deployment:
```bash
gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
```

### Start the Interactive CLI

```bash
python movie_recommender.py --menu
```

## Quick start (CLI)

Run single queries from the command line:

```bash
# Basic search
python movie_recommender.py --query "Inception"

# JSON output with fuzzy matching
python movie_recommender.py --query "Incption" --fuzzy --format json
```

## Frontend integration

TMDB-backed movie responses now include an optional `id` field. Use that `id` to fetch a trailer:

```bash
curl "http://localhost:8000/api/movies/550/trailer"
```

Response:

```json
{
  "youtube_key": "SUXWAEX2jlg"
}
```

Example movie payload from `/api/movies/trending` or `/api/movies/search`:

```json
{
  "id": 550,
  "name": "Fight Club",
  "year": 1999,
  "category": "Trending",
  "genre": "Drama",
  "box_office_millions": null,
  "rating": 8.4,
  "poster_url": "https://image.tmdb.org/t/p/w500/example.jpg"
}
```

## Tests

Run the test suite to verify the application:

```bash
PYTHONPATH=. python -m pytest
```

## Dataset notes

The repository includes a cleaned dataset (`movies_cleaned.csv`, `ratings_cleaned.csv`). The system automatically integrates this data on startup.

## Contributing and License

Contributions are welcome — open an issue or submit a pull request.

## Cine Craft Box

Check out the full stack application here: [Cine Craft Box](https://cine-craft-box.lovable.app)

---
Developed with FastAPI, Pydantic, and RapidFuzz.