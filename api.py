"""
Movie Recommender API
FastAPI application exposing movie recommendation functionality as REST endpoints
"""

import os
import logging
import httpx
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any, Set

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Load environment variables from .env file
load_dotenv(override=True)

# Configure logging early
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Limiter for rate limiting
limiter = Limiter(key_func=get_remote_address)

# Import the existing movie recommender functionality
from movie_recommender import (
    movies, find_matches, get_available_genres, get_available_categories,
    add_favorite, remove_favorite, get_favorite_movies, get_favorite_entries,
    load_favorites, save_favorites, format_movie, serialize_movies,
    expand_dataset_if_needed
)

# Import CSV statistics if available
try:
    from csv_loader import get_csv_statistics
    _HAS_CSV_STATS = True
except ImportError:
    _HAS_CSV_STATS = False

# Configuration from environment variables
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
RELOAD = os.getenv("RELOAD", "false").lower() == "true"
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# TMDB Genre ID to Name Mapping
TMDB_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western"
}

# Engagement tracker (In-memory: tracks unique genres searched/filtered per IP)
user_genres: Dict[str, Set[str]] = {}

# Add bare domains and both http/https for common origins
base_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "https://cine-craft-box.lovable.app",
    "http://cine-craft-box.lovable.app",
    "https://lovable.app",
    "http://lovable.app",
]
env_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()]
ALLOWED_ORIGINS = list(dict.fromkeys(base_origins + env_origins))
env_regex = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip()
ALLOWED_ORIGIN_REGEX = env_regex if env_regex else r"https?://(.*\.)?lovable(app|project)\.com|https?://(.*\.)?lovable\.app"

FAVORITES_FILE = os.getenv("FAVORITES_FILE", "favorites.json")

# Custom CORS Logging Middleware
class CORSLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        response = await call_next(request)
        if response.status_code == 400 and origin:
             logger.warning(f"Possible CORS rejection (400) for origin: {origin}")
        return response

def refresh_favorites_state() -> None:
    load_favorites(FAVORITES_FILE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Movie Recommender API")
    load_favorites(FAVORITES_FILE)
    logger.info(f"Loaded {len(get_favorite_entries())} favorites from {FAVORITES_FILE}")
    logger.info(f"API ready with {len(movies)} movies in dataset")
    yield
    logger.info("Shutting down Movie Recommender API")

# Initialize FastAPI app
app = FastAPI(
    title="Movie Recommender API",
    description="A REST API for movie recommendations with search, filtering, and favorites management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Rate limiting setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CORSLoggingMiddleware)

# Pydantic models for request/response
class MovieResponse(BaseModel):
    name: str
    year: int
    category: str
    genre: str
    box_office_millions: Optional[float] = None
    rating: float
    poster_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class TrendingResponse(BaseModel):
    movies: List[MovieResponse]
    engagement_count: int
    is_unlocked: bool
    needed_to_unlock: int

class SearchResponse(BaseModel):
    source: str
    results: List[MovieResponse]
    is_unlocked: bool

class FeaturedResponse(BaseModel):
    latest_movies: List[MovieResponse]
    old_movies: List[MovieResponse]

class FavoriteRequest(BaseModel):
    name: str
    year: int

class FavoriteResponse(BaseModel):
    name: str
    year: int

class GenreResponse(BaseModel):
    genre: str
    count: int

class CategoryResponse(BaseModel):
    category: str
    count: int

async def fetch_trending_from_tmdb() -> List[Dict[str, Any]]:
    """Helper to fetch trending movies from TMDB or fallback to local."""
    if not TMDB_API_KEY:
        return sorted(movies, key=lambda x: x.get("year", 0), reverse=True)[:20]

    url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise Exception("TMDB API failed")
            
            data = response.json()
            results = data.get("results", [])
            
            formatted = []
            for m in results:
                genre_ids = m.get("genre_ids", [])
                genre_names = [TMDB_GENRES.get(gid, "Movie") for gid in genre_ids]
                formatted.append({
                    "name": m.get("title"),
                    "year": int(m.get("release_date", "0000")[:4]) if m.get("release_date") else 0,
                    "rating": round(m.get("vote_average", 0), 1),
                    "poster_url": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else None,
                    "genre": genre_names[0] if genre_names else "Trending",
                    "category": "Trending",
                    "box_office_millions": None
                })
            return formatted
    except Exception as e:
        logger.warning(f"TMDB Fetch failed: {e}")
        return sorted(movies, key=lambda x: x.get("year", 0), reverse=True)[:20]

# Root endpoint
@app.get("/")
@limiter.limit("60/minute")
async def root(request: Request):
    """API root endpoint with basic information."""
    refresh_favorites_state()
    return {
        "message": "Movie Recommender API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "total_movies": len(movies),
        "favorites_count": len(get_favorite_entries())
    }

@app.get("/api/movies/trending", response_model=TrendingResponse)
@limiter.limit("20/minute")
async def get_trending_movies(request: Request, genre: Optional[str] = Query(None)):
    """Fetch trending movies and track unique genre engagement."""
    user_ip = request.client.host if request.client else "unknown"
    
    if user_ip not in user_genres:
        user_genres[user_ip] = set()

    if genre:
        user_genres[user_ip].add(genre.lower())
    
    trending_data = await fetch_trending_from_tmdb()
    
    # Filter by genre if provided
    if genre:
        g_lower = genre.lower()
        trending_data = [m for m in trending_data if g_lower in m['genre'].lower()]
        
    engagement_count = len(user_genres[user_ip])
    is_unlocked = engagement_count >= 5

    return {
        "movies": [MovieResponse(**m) for m in trending_data],
        "engagement_count": engagement_count,
        "is_unlocked": is_unlocked,
        "needed_to_unlock": max(0, 5 - engagement_count)
    }

@app.get("/api/movies/search", response_model=SearchResponse)
@limiter.limit("30/minute")
async def search_movies(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    genre: Optional[str] = Query(None),
    max_results: int = Query(30, ge=1, le=200)
):
    """
    Search endpoint with conditional locking.
    If locked (<5 unique genres explored), only searches trending TMDB data.
    If unlocked, searches the full Classic Vault (CSV).
    """
    user_ip = request.client.host if request.client else "unknown"
    engagement_count = len(user_genres.get(user_ip, set()))
    is_unlocked = engagement_count >= 5
    
    if not q:
        return {"source": "N/A", "results": [], "is_unlocked": is_unlocked}

    if not is_unlocked:
        # LOCKED: Only search through current trending results to prevent CSV leak
        trending = await fetch_trending_from_tmdb()
        q_lower = q.lower()
        matches = [m for m in trending if q_lower in m.get('name', '').lower()]
        return {
            "source": "TMDB (Locked)", 
            "results": [MovieResponse(**m) for m in matches],
            "is_unlocked": False
        }
    else:
        # UNLOCKED: Search the full 50k+ CSV movies
        matches = find_matches(
            query_text=q,
            max_results=max_results,
            genre=genre
        )
        return {
            "source": "Classic Vault (Unlocked)", 
            "results": [MovieResponse(**m) for m in matches],
            "is_unlocked": True
        }

@app.get("/api/movies/featured", response_model=FeaturedResponse)
@limiter.limit("20/minute")
async def get_featured_movies(request: Request):
    """Provide recent and older movies for frontend landing-page sections."""
    try:
        latest = sorted(movies, key=lambda x: x.get("year", 0), reverse=True)[:10]
        oldies = sorted(movies, key=lambda x: x.get("year", 0))[:10]
        return {
            "latest_movies": [MovieResponse(**movie) for movie in latest],
            "old_movies": [MovieResponse(**movie) for movie in oldies],
        }
    except Exception as e:
        logger.exception("Error getting featured movies")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred fetching featured datasets"
        )

@app.get("/api/movies/top", response_model=List[MovieResponse])
@limiter.limit("20/minute")
async def get_top_movies(
    request: Request,
    limit: int = Query(10, ge=1, le=50)
):
    try:
        top_movies = sorted(movies, key=lambda x: x.get('rating', 0), reverse=True)[:limit]
        return [MovieResponse(**movie) for movie in top_movies]
    except Exception as e:
        logger.exception("Error getting top movies")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving top movies"
        )

@app.get("/api/genres", response_model=List[GenreResponse])
@limiter.limit("20/minute")
async def get_genres(request: Request):
    try:
        return [GenreResponse(**genre) for genre in get_available_genres()]
    except Exception as e:
        logger.exception("Error getting genres")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred")

@app.get("/api/categories", response_model=List[CategoryResponse])
@limiter.limit("20/minute")
async def get_categories(request: Request):
    try:
        return [CategoryResponse(**category) for category in get_available_categories()]
    except Exception as e:
        logger.exception("Error getting categories")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred")

@app.get("/api/favorites", response_model=List[MovieResponse])
@limiter.limit("20/minute")
async def get_favorites(request: Request):
    try:
        refresh_favorites_state()
        fav_movies = get_favorite_movies()
        return [MovieResponse(**movie) for movie in fav_movies]
    except Exception as e:
        logger.exception("Error getting favorites")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred")

@app.post("/api/favorites", response_model=Dict[str, str])
@limiter.limit("5/minute")
async def add_to_favorites(request: Request, favorite: FavoriteRequest):
    try:
        success = add_favorite(favorite.name, favorite.year, FAVORITES_FILE)
        if success:
            return {"message": f"Added to favorites"}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not found or already in favorites")
    except Exception as e:
        logger.exception("Error adding to favorites")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred")

@app.delete("/api/favorites", response_model=Dict[str, str])
@limiter.limit("5/minute")
async def remove_from_favorites(request: Request, favorite: FavoriteRequest):
    try:
        success = remove_favorite(favorite.name, favorite.year, FAVORITES_FILE)
        if success:
            return {"message": f"Removed from favorites"}
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found in favorites")
    except Exception as e:
        logger.exception("Error removing from favorites")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred")

@app.get("/api/health")
@limiter.limit("60/minute")
async def health_check(request: Request):
    refresh_favorites_state()
    return {
        "status": "healthy",
        "movies_count": len(movies),
        "favorites_count": len(get_favorite_entries()),
        "csv_integration": _HAS_CSV_STATS,
        "tmdb_integration": bool(TMDB_API_KEY)
    }

@app.get("/api/statistics")
@limiter.limit("20/minute")
async def get_statistics(request: Request):
    try:
        refresh_favorites_state()
        stats = {
            "total_movies": len(movies),
            "favorites_count": len(get_favorite_entries()),
            "available_genres": len(get_available_genres()),
            "available_categories": len(get_available_categories())
        }
        if _HAS_CSV_STATS:
            csv_stats = get_csv_statistics()
            stats["csv_data"] = csv_stats if 'error' not in csv_stats else {"error": csv_stats['error']}
        return stats
    except Exception as e:
        logger.exception("Error getting statistics")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred")

@app.get("/api/movies/{name}/{year}", response_model=MovieResponse)
@limiter.limit("30/minute")
async def get_movie_details(request: Request, name: str, year: int):
    try:
        for movie in movies:
            if movie.get('name', '').lower() == name.lower() and movie.get('year') == year:
                return MovieResponse(**movie)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    except Exception as e:
        logger.exception("Error getting movie details")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred")

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host=HOST, port=PORT, reload=RELOAD)
