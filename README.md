# Movie Recommender

Movie recommendation service with three entry points:

- A FastAPI backend in `api.py`
- A CLI recommender in `movie_recommender.py`
- An optional Go gateway in `go-gateway/` for proxying, caching, and rate limiting

## What It Does

- Search movies with optional fuzzy matching
- Return trending, featured, top-rated, and recommendation results
- Persist favorites to `favorites.json`
- Fetch TMDB trailers, posters, and TMDB-based recommendations when `TMDB_API_KEY` is configured
- Fall back to the local dataset for core recommendation features

## Project Layout

```text
.
├── api.py
├── movie_recommender.py
├── run_api.py
├── go-gateway/
├── tests/
├── requirements.txt
└── .env.template
```

## Requirements

- Python 3.12 recommended
- TMDB API key for trailer, poster, trending, and TMDB recommendation endpoints
- Optional: Go toolchain and Redis if you want to run the gateway

## Setup

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your local environment file:

```bash
cp .env.template .env
```

Minimum useful config:

```env
TMDB_API_KEY=your_tmdb_api_key_here
PORT=8000
HOST=0.0.0.0
RELOAD=false
LOG_LEVEL=info
FAVORITES_FILE=favorites.json
```

Other supported config in `.env.template`:

- `MOVIES_CSV_PATH`
- `RATINGS_CSV_PATH`
- `ALLOWED_ORIGINS`
- `ALLOWED_ORIGIN_REGEX`

## Run The FastAPI App

For local development:

```bash
python run_api.py
```

The API will be available at:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`
- `http://localhost:8000/api/health`

Production command:

```bash
gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
```

This is also what the [`Procfile`](/home/victor/Documents/movie-recommender/Procfile:1) uses.

## Run The CLI

Interactive mode:

```bash
python movie_recommender.py --menu
```

Single query examples:

```bash
python movie_recommender.py --query "Inception"
python movie_recommender.py --query "Incption" --fuzzy --format json
python movie_recommender.py --genre Drama --min-rating 8 --sort-by rating
```

Useful CLI flags:

- `--query`
- `--fuzzy`
- `--format text|json`
- `--genre`
- `--category`
- `--min-rating`
- `--year`
- `--year-from`
- `--year-to`
- `--sort-by rating|box_office|year`
- `--max-results`
- `--list-genres`
- `--list-categories`
- `--menu`

## Run The Go Gateway

The Go gateway sits in front of FastAPI and adds:

- Redis-backed rate limiting
- Cached proxying for expensive endpoints
- Local handling for favorites reads

Default behavior:

- FastAPI upstream: `http://localhost:8000`
- Gateway port: `8080`
- Redis address: `localhost:6379`

Example:

```bash
cd go-gateway
go run .
```

Environment variables used by the gateway:

- `UPSTREAM_URL`
- `PORT`
- `REDIS_ADDR`
- `REDIS_PASSWORD`

Gateway endpoints of note:

- `GET /ping`
- `GET /api/favorites`
- `POST /api/favorites`
- `DELETE /api/favorites`
- cached proxy for `/api/movies/trending`, `/api/movies/search`, and `/api/movies/featured`

## Main API Endpoints

- `GET /api/movies/trending`
- `GET /api/movies/search`
- `GET /api/movies/featured`
- `GET /api/movies/top`
- `GET /api/movies/{movie_id}/trailer`
- `GET /api/movies/{movie_id}/stream`
- `GET /api/movies/{movie_id}/recommendations`
- `GET /api/favorites`
- `POST /api/favorites`
- `DELETE /api/favorites`
- `GET /api/genres`
- `GET /api/categories`
- `GET /api/statistics`
- `GET /api/recommend/by-title`
- `GET /api/recommendations`
- `GET /api/recommendations/discovery`

Detailed endpoint behavior is documented in [`API_DOCUMENTATION.md`](/home/victor/Documents/movie-recommender/API_DOCUMENTATION.md:1).

## Notes On Data Sources

- The core recommender ships with a built-in movie dataset.
- If a CSV loader is available, the dataset can be expanded from CSV files.
- TMDB is used for trailers, posters, and TMDB recommendation/trending data when configured.
- If `TMDB_API_KEY` is missing, some TMDB-backed endpoints degrade or return empty/fallback responses depending on the endpoint.

## Tests

Run the test suite with:

```bash
PYTHONPATH=. python -m pytest
```

Test files live in [`tests/`](/home/victor/Documents/movie-recommender/tests).

## Frontend

The README previously pointed at a frontend project. If you still use it, the related app link is:

- `https://cine-craft-box.lovable.app`

## Live Deployment

- App: `https://movie-recommender-7zqv.onrender.com/`
- Swagger: `https://movie-recommender-7zqv.onrender.com/docs`
- ReDoc: `https://movie-recommender-7zqv.onrender.com/redoc`
