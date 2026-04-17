"""
Movie Recommender API
FastAPI application exposing movie recommendation functionality as REST endpoints
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

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
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
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
# More robust regex for any lovable.app or lovableproject.com subdomain
# Defaults to a broader regex if not provided
env_regex = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip()
ALLOWED_ORIGIN_REGEX = env_regex if env_regex else r"https?://(.*\.)?lovable(app|project)\.com|https?://(.*\.)?lovable\.app"

logger.info(f"ALLOWED_ORIGINS: {ALLOWED_ORIGINS}")
logger.info(f"ALLOWED_ORIGIN_REGEX: {ALLOWED_ORIGIN_REGEX}")

FAVORITES_FILE = os.getenv("FAVORITES_FILE", "favorites.json")

# Custom CORS Logging Middleware
class CORSLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # We process preflight (OPTIONS) or actual requests
        origin = request.headers.get("origin")
        
        response = await call_next(request)
        
        # Log if it was a CORS rejection (often 400 with our current Starlette version)
        if response.status_code == 400 and origin:
             # Check if it looks like a CORS rejection
             # Since we can't easily read response body here without complex code, 
             # we just log that we got a 400 from an origin.
             logger.warning(f"Possible CORS rejection (400) for origin: {origin}")
        
        return response

def refresh_favorites_state() -> None:
    """Refresh in-memory favorites from disk so all workers see current state."""
    load_favorites(FAVORITES_FILE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    logger.info("Starting Movie Recommender API")
    
    # Load favorites from file
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

# Custom CORS Logging Middleware

 # Make sure ALLOWED_ORIGINS includes your lovable URL
# e.g., ALLOWED_ORIGINS = ["https://cine-craft-box.lovable.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,  # Changed to True for better frontend compatibility
    allow_methods=["*"], # Added OPTIONS for preflight
    allow_headers=["*"], # Flexible headers are safer during development
)
app.add_middleware(CORSLoggingMiddleware)

# Pydantic models for request/response
class MovieResponse(BaseModel):
    name: str
    
    year: int
    category: str
    genre: str
    box_office_millions: float
    rating: float

    model_config = ConfigDict(from_attributes=True)


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

class SearchFilters(BaseModel):
    genre: Optional[str] = None
    category: Optional[str] = None
    min_rating: Optional[float] = Field(None, ge=0, le=10, description="Minimum rating (0-10)")
    year: Optional[int] = Field(None, ge=1900, le=2030, description="Exact year")
    year_from: Optional[int] = Field(None, ge=1900, le=2030, description="Year range start")
    year_to: Optional[int] = Field(None, ge=1900, le=2030, description="Year range end")
    sort_by: Optional[str] = Field(None, pattern="^(rating|box_office|year)$")

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

# Movie search endpoint
@app.get("/api/movies/search", response_model=List[MovieResponse])
@limiter.limit("30/minute")
async def search_movies(
    request: Request,
    q: Optional[str] = Query(None, description="Search query (movie name, genre, etc.)"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_rating: Optional[float] = Query(None, ge=0, le=10, description="Minimum rating"),
    year: Optional[int] = Query(None, ge=1900, le=2030, description="Filter by year"),
    year_from: Optional[int] = Query(None, ge=1900, le=2030, description="Year from"),
    year_to: Optional[int] = Query(None, ge=1900, le=2030, description="Year to"),
    sort_by: Optional[str] = Query(None, pattern="^(rating|box_office|year)$", description="Sort by field"),
    fuzzy: bool = Query(True, description="Enable fuzzy matching"),
    max_results: int = Query(30, ge=1, le=200, description="Maximum results to return")
):
    """
    Search for movies with optional filters and sorting.
    
    - **q**: Search query (movie name, genre, category)
    - **genre**: Filter by genre (substring match)
    - **category**: Filter by category (substring match)
    - **min_rating**: Minimum rating filter (0-10)
    - **year**: Filter by exact year
    - **year_from**: Filter movies from this year onwards
    - **year_to**: Filter movies up to this year
    - **sort_by**: Sort results by 'rating', 'box_office', or 'year'
    - **fuzzy**: Enable fuzzy string matching
    - **max_results**: Maximum number of results to return (1-200)
    """
    try:
        matches = find_matches(
            query_text=q or '',
            max_results=max_results,
            enable_fuzzy=fuzzy,
            genre=genre,
            category=category,
            min_rating=min_rating,
            year=year,
            year_from=year_from,
            year_to=year_to,
            sort_by=sort_by
        )
        
        return [MovieResponse(**movie) for movie in matches]
        
    except Exception as e:
        logger.exception("Error during movie search")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching for movies"
        )

# Top rated movies endpoint
@app.get("/api/movies/top", response_model=List[MovieResponse])
@limiter.limit("20/minute")
async def get_top_movies(
    request: Request,
    limit: int = Query(10, ge=1, le=50, description="Number of top movies to return")
):
    """Get top-rated movies sorted by rating."""
    try:
        top_movies = sorted(movies, key=lambda x: x.get('rating', 0), reverse=True)[:limit]
        return [MovieResponse(**movie) for movie in top_movies]
    except Exception as e:
        logger.exception("Error getting top movies")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving top movies"
        )

# Genres endpoint
@app.get("/api/genres", response_model=List[GenreResponse])
@limiter.limit("20/minute")
async def get_genres(request: Request):
    """Get all available genres with movie counts."""
    try:
        return [GenreResponse(**genre) for genre in get_available_genres()]
    except Exception as e:
        logger.exception("Error getting genres")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving genres"
        )

# Categories endpoint
@app.get("/api/categories", response_model=List[CategoryResponse])
@limiter.limit("20/minute")
async def get_categories(request: Request):
    """Get all available categories with movie counts."""
    try:
        return [CategoryResponse(**category) for category in get_available_categories()]
    except Exception as e:
        logger.exception("Error getting categories")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving categories"
        )

# Favorites endpoints
@app.get("/api/favorites", response_model=List[MovieResponse])
@limiter.limit("20/minute")
async def get_favorites(request: Request):
    """Get all favorite movies with full details."""
    try:
        refresh_favorites_state()
        fav_movies = get_favorite_movies()
        return [MovieResponse(**movie) for movie in fav_movies]
    except Exception as e:
        logger.exception("Error getting favorites")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving favorites"
        )

@app.post("/api/favorites", response_model=Dict[str, str])
@limiter.limit("5/minute")
async def add_to_favorites(request: Request, favorite: FavoriteRequest):
    """Add a movie to favorites."""
    try:
        # Use configurable favorites file
        success = add_favorite(favorite.name, favorite.year, FAVORITES_FILE)
        if success:
            return {"message": f"Added '{favorite.name} ({favorite.year})' to favorites"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Movie not found in dataset or already in favorites"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error adding to favorites")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding to favorites"
        )

@app.delete("/api/favorites", response_model=Dict[str, str])
@limiter.limit("5/minute")
async def remove_from_favorites(request: Request, favorite: FavoriteRequest):
    """Remove a movie from favorites."""
    try:
        # Use configurable favorites file
        success = remove_favorite(favorite.name, favorite.year, FAVORITES_FILE)
        if success:
            return {"message": f"Removed '{favorite.name} ({favorite.year})' from favorites"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movie not found in favorites"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error removing from favorites")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while removing from favorites"
        )

# Health check endpoint
@app.get("/api/health")
@limiter.limit("60/minute")
async def health_check(request: Request):
    """Health check endpoint."""
    refresh_favorites_state()
    return {
        "status": "healthy",
        "movies_count": len(movies),
        "favorites_count": len(get_favorite_entries()),
        "csv_integration": _HAS_CSV_STATS
    }

# CSV statistics endpoint
@app.get("/api/statistics")
@limiter.limit("20/minute")
async def get_statistics(request: Request):
    """Get detailed statistics about the movie dataset."""
    try:
        refresh_favorites_state()
        stats = {
            "total_movies": len(movies),
            "favorites_count": len(get_favorite_entries()),
            "available_genres": len(get_available_genres()),
            "available_categories": len(get_available_categories())
        }
        
        # Add CSV statistics if available
        if _HAS_CSV_STATS:
            csv_stats = get_csv_statistics()
            if 'error' not in csv_stats:
                stats["csv_data"] = csv_stats
            else:
                stats["csv_error"] = csv_stats['error']
        else:
            stats["csv_note"] = "CSV statistics not available"
        
        return stats
        
    except Exception as e:
        logger.exception("Error getting statistics")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving statistics"
        )

# Movie details by name and year
@app.get("/api/movies/{name}/{year}", response_model=MovieResponse)
@limiter.limit("30/minute")
async def get_movie_details(request: Request, name: str, year: int):
    """Get detailed information about a specific movie."""
    try:
        for movie in movies:
            if movie.get('name', '').lower() == name.lower() and movie.get('year') == year:
                return MovieResponse(**movie)
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movie '{name} ({year})' not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting movie details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving movie details"
        )

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Resource not found"}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host=HOST, port=PORT, reload=RELOAD)
