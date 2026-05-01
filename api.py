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
from fastapi.exceptions import HTTPException as FastAPIHTTPException
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
    id: Optional[int] = None
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

class TrailerResponse(BaseModel):
    youtube_key: str

class RecommendationResponse(BaseModel):
    movie: MovieResponse
    similarity_score: float
    match_reason: str

class RecommendationsResponse(BaseModel):
    recommendations: List[RecommendationResponse]
    based_on: Dict[str, Any]
    total_available: int

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

async def fetch_trending_from_tmdb(pages: int = 3) -> List[Dict[str, Any]]:
    """Helper to fetch multiple pages of trending/popular movies from TMDB."""
    if not TMDB_API_KEY:
        return sorted(movies, key=lambda x: x.get("year", 0), reverse=True)[:50]

    all_results = []
    async with httpx.AsyncClient(timeout=7.0) as client:
        # Fetch multiple pages to get a larger pool (approx 60-100 movies)
        for page in range(1, pages + 1):
            try:
                # Use popular for a diverse set
                url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&page={page}"
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    all_results.extend(data.get("results", []))
            except Exception as e:
                logger.warning(f"Failed to fetch TMDB page {page}: {e}")
                break
    
    if not all_results:
        return sorted(movies, key=lambda x: x.get("year", 0), reverse=True)[:50]

    # Deduplicate by TMDB ID
    unique_results = {r['id']: r for r in all_results}.values()
    
    formatted = []
    for m in unique_results:
        genre_ids = m.get("genre_ids", [])
        genre_names = [TMDB_GENRES.get(gid, "Movie") for gid in genre_ids]
        formatted.append({
            "id": m.get("id"),
            "name": m.get("title"),
            "year": int(m.get("release_date", "0000")[:4]) if m.get("release_date") else 0,
            "rating": round(m.get("vote_average", 0), 1),
            "poster_url": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else None,
            "genre": ", ".join(genre_names) if genre_names else "Movie",
            "category": "Trending",
            "box_office_millions": None
        })
    return formatted

def select_tmdb_trailer(videos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick the best available YouTube trailer from a TMDB video list."""
    youtube_videos = [
        video for video in videos
        if video.get("site") == "YouTube" and video.get("key")
    ]
    if not youtube_videos:
        return None

    official_trailer = next(
        (
            video for video in youtube_videos
            if video.get("type") == "Trailer" and video.get("official") is True
        ),
        None,
    )
    if official_trailer:
        return official_trailer

    trailer = next(
        (video for video in youtube_videos if video.get("type") == "Trailer"),
        None,
    )
    if trailer:
        return trailer

    return youtube_videos[0]

# User preference tracking for content-based recommendations
user_preferences: Dict[str, Dict[str, Any]] = {}
user_favorite_keys: Dict[str, Set[tuple[str, int]]] = {}

def get_user_preferences(user_ip: str) -> Dict[str, Any]:
    """Get or initialize user preferences for content-based filtering."""
    if user_ip not in user_preferences:
        user_preferences[user_ip] = {
            "viewed_movies": set(),  # (name, year) tuples
            "liked_genres": set(),
            "liked_categories": set(),
            "rating_preference": 7.0,  # Default preference
            "year_range": {"min": 1980, "max": 2024},
            "favorite_movies": [],  # List of movie dicts
        }
    return user_preferences[user_ip]


def get_user_favorite_movies(user_ip: str) -> List[Dict[str, Any]]:
    """Return favorite movie records associated with a specific user."""
    favorite_keys = user_favorite_keys.get(user_ip, set())
    if not favorite_keys:
        return []

    movie_lookup = {
        (movie.get("name"), movie.get("year")): movie
        for movie in movies
    }
    return [
        movie_lookup[key]
        for key in favorite_keys
        if key in movie_lookup
    ]

def calculate_content_similarity(
    movie: Dict[str, Any],
    user_prefs: Dict[str, Any]
) -> tuple[float, str]:
    """
    Calculate content-based similarity score between a movie and user preferences.
    Returns (score, reason) tuple.
    """
    score = 0.0
    reasons = []
    
    # Genre similarity (0-40 points)
    movie_genres = set()
    if movie.get("genre"):
        movie_genres.update(g.strip().lower() for g in movie["genre"].split("/"))
    if movie.get("all_genres"):
        movie_genres.update(g.strip().lower() for g in movie.get("all_genres", []))
    
    liked_genres = user_prefs.get("liked_genres", set())
    if liked_genres and movie_genres:
        genre_overlap = len(movie_genres & liked_genres)
        genre_score = min(genre_overlap * 15, 40)
        if genre_score > 0:
            score += genre_score
            top_genre = list(movie_genres & liked_genres)[0].title() if (movie_genres & liked_genres) else ""
            reasons.append(f"Matches your taste in {top_genre}")
    
    # Category similarity (0-20 points)
    movie_category = movie.get("category", "").lower()
    liked_categories = user_prefs.get("liked_categories", set())
    if liked_categories and movie_category in liked_categories:
        score += 20
        reasons.append(f"{movie.get('category', 'Similar')} film")
    
    # Rating alignment (0-20 points)
    movie_rating = movie.get("rating", 0)
    preferred_rating = user_prefs.get("rating_preference", 7.0)
    if movie_rating > 0:
        rating_diff = abs(movie_rating - preferred_rating)
        if rating_diff < 1.0:
            score += 20
            reasons.append("Highly rated")
        elif rating_diff < 2.0:
            score += 10
    
    # Year/decade alignment (0-15 points)
    movie_year = movie.get("year", 2000)
    year_range = user_prefs.get("year_range", {"min": 1980, "max": 2024})
    if year_range["min"] <= movie_year <= year_range["max"]:
        score += 15
    elif abs(movie_year - (year_range["min"] + year_range["max"]) // 2) < 15:
        score += 8
    
    # Box office bonus (0-5 points) - popularity signal
    box_office = movie.get("box_office_millions", 0) or 0
    if box_office > 500:
        score += 5
        if not any("rated" in r for r in reasons):
            reasons.append("Popular hit")
    elif box_office > 100:
        score += 2
    
    # Normalize score to 0-100
    final_score = min(round(score), 100)
    
    # Build concise match reason
    if reasons:
        match_reason = reasons[0]
        if len(reasons) > 1:
            match_reason += f" • {reasons[1]}"
    else:
        match_reason = "Recommended for you"
    
    return final_score, match_reason

def update_user_preferences_from_favorites(user_ip: str) -> None:
    """Update user preferences based on their favorite movies."""
    prefs = get_user_preferences(user_ip)
    fav_movies = get_user_favorite_movies(user_ip)
    prefs["favorite_movies"] = fav_movies

    prefs["viewed_movies"] = set()
    prefs["liked_genres"] = set()
    prefs["liked_categories"] = set()
    prefs["rating_preference"] = 7.0
    prefs["year_range"] = {"min": 1980, "max": 2024}
    
    if not fav_movies:
        return
    
    # Extract genres from favorites
    all_genres = set()
    all_categories = set()
    ratings = []
    years = []
    
    for movie in fav_movies:
        # Genres
        if movie.get("genre"):
            all_genres.update(g.strip().lower() for g in movie["genre"].split("/"))
        if movie.get("all_genres"):
            all_genres.update(g.strip().lower() for g in movie.get("all_genres", []))
        
        # Categories
        if movie.get("category"):
            all_categories.add(movie["category"].lower())
        
        # Ratings and years for averaging
        if movie.get("rating"):
            ratings.append(movie["rating"])
        if movie.get("year"):
            years.append(movie["year"])
        
        # Track viewed movies
        prefs["viewed_movies"].add((movie.get("name"), movie.get("year")))
    
    prefs["liked_genres"] = all_genres
    prefs["liked_categories"] = all_categories
    
    if ratings:
        prefs["rating_preference"] = sum(ratings) / len(ratings)
    
    if years:
        avg_year = sum(years) / len(years)
        prefs["year_range"] = {
            "min": int(avg_year - 20),
            "max": int(avg_year + 10)
        }

def get_content_recommendations(
    user_ip: str,
    limit: int = 10,
    exclude_viewed: bool = True
) -> List[Dict[str, Any]]:
    """Generate content-based recommendations for a user."""
    prefs = get_user_preferences(user_ip)
    
    # Refresh from favorites
    update_user_preferences_from_favorites(user_ip)
    
    # Get candidate movies (combine local and TMDB if available)
    candidates = movies.copy()
    
    scored_movies = []
    for movie in candidates:
        # Skip already viewed movies if requested
        if exclude_viewed:
            movie_key = (movie.get("name"), movie.get("year"))
            if movie_key in prefs["viewed_movies"]:
                continue
        
        score, reason = calculate_content_similarity(movie, prefs)
        if score > 0:
            scored_movies.append({
                "movie": movie,
                "score": score,
                "reason": reason
            })
    
    # Sort by score descending
    scored_movies.sort(key=lambda x: x["score"], reverse=True)
    
    return scored_movies[:limit]

def get_similar_movies(
    target_movie: Dict[str, Any],
    limit: int = 8,
    exclude_same: bool = True
) -> List[Dict[str, Any]]:
    """Find movies similar to a target movie based on content features."""
    target_genres = set()
    if target_movie.get("genre"):
        target_genres.update(g.strip().lower() for g in target_movie["genre"].split("/"))
    if target_movie.get("all_genres"):
        target_genres.update(g.strip().lower() for g in target_movie.get("all_genres", []))
    
    target_category = target_movie.get("category", "").lower()
    target_year = target_movie.get("year", 2000)
    target_rating = target_movie.get("rating", 0)
    
    scored = []
    for movie in movies:
        # Skip the same movie
        if exclude_same:
            if (movie.get("name") == target_movie.get("name") and 
                movie.get("year") == target_year):
                continue
        
        score = 0
        reasons = []
        
        # Genre overlap (most important)
        movie_genres = set()
        if movie.get("genre"):
            movie_genres.update(g.strip().lower() for g in movie["genre"].split("/"))
        if movie.get("all_genres"):
            movie_genres.update(g.strip().lower() for g in movie.get("all_genres", []))
        
        genre_overlap = len(target_genres & movie_genres)
        if genre_overlap > 0:
            score += genre_overlap * 25
            common = list(target_genres & movie_genres)[0].title()
            reasons.append(f"{common}")
        
        # Same category
        if movie.get("category", "").lower() == target_category:
            score += 20
            reasons.append(f"{target_movie.get('category', 'Same category')}")
        
        # Year proximity
        year_diff = abs(movie.get("year", 2000) - target_year)
        if year_diff <= 5:
            score += 15
        elif year_diff <= 10:
            score += 8
        
        # Rating proximity
        rating_diff = abs(movie.get("rating", 0) - target_rating)
        if rating_diff < 1.0:
            score += 15
            reasons.append("Similar rating")
        elif rating_diff < 2.0:
            score += 8
        
        if score > 10:  # Minimum threshold
            reason_str = f"Because you liked {target_movie.get('name')} • {', '.join(reasons[:2])}"
            scored.append({
                "movie": movie,
                "score": min(score, 100),
                "reason": reason_str
            })
    
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

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

@app.get("/api/movies/trending")
@limiter.limit("20/minute")
async def get_trending_movies(request: Request, genre: Optional[str] = Query(None)):
    """Fetch trending movies. Returns 10 by default, or filtered results."""
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
    else:
        # Initial view: show only top 10
        trending_data = trending_data[:10]
        
    engagement_count = len(user_genres[user_ip])
    is_unlocked = engagement_count >= 5

    # Return simple list for frontend compatibility
    return [MovieResponse(**m) for m in trending_data]

@app.get("/api/movies/search")
@limiter.limit("30/minute")
async def search_movies(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    genre: Optional[str] = Query(None),
    max_results: int = Query(60, ge=1, le=200)
):
    """
    Unified Search Endpoint:
    - Locked: Searches only live TMDB trending data (Name & Genre).
    - Unlocked: Searches BOTH live TMDB and Classic Vault (CSV).
    """
    user_ip = request.client.host if request.client else "unknown"
    if user_ip not in user_genres:
        user_genres[user_ip] = set()
    
    if genre:
        user_genres[user_ip].add(genre.lower())
    
    engagement_count = len(user_genres.get(user_ip, set()))
    is_unlocked = engagement_count >= 5
    
    if not q and not genre:
        return []

    trending = await fetch_trending_from_tmdb()
    q_lower = q.lower() if q else ""
    g_lower = genre.lower() if genre else ""

    tmdb_matches = []
    for m in trending:
        name_match = not q_lower or q_lower in m.get('name', '').lower()
        genre_match = not g_lower or g_lower in m.get('genre', '').lower()
        q_genre_match = q_lower and q_lower in m.get('genre', '').lower()
        
        if (name_match or q_genre_match) and genre_match:
            tmdb_matches.append(MovieResponse(**m))

    if not is_unlocked:
        return tmdb_matches[:max_results]
    else:
        # Search the Classic Vault (CSV)
        csv_matches = find_matches(
            query_text=q or "",
            max_results=max_results,
            genre=genre
        )
        csv_formatted = [MovieResponse(**m) for m in csv_matches]
        
        # Merge results
        seen = {(m.name, m.year) for m in tmdb_matches}
        unique_csv = [m for m in csv_formatted if (m.name, m.year) not in seen]
        
        return (tmdb_matches + unique_csv)[:max_results]

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

@app.get("/api/movies/{movie_id}/trailer", response_model=TrailerResponse)
@limiter.limit("20/minute")
async def get_movie_trailer(request: Request, movie_id: int):
    if not TMDB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TMDB integration is not configured"
        )

    url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos"

    try:
        async with httpx.AsyncClient(timeout=7.0) as client:
            response = await client.get(url, params={"api_key": TMDB_API_KEY})
    except httpx.RequestError:
        logger.exception("Failed to reach TMDB trailer endpoint for movie_id=%s", movie_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch trailer from TMDB"
        )

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Movie not found on TMDB")

    if response.status_code != status.HTTP_200_OK:
        logger.warning(
            "TMDB trailer lookup failed for movie_id=%s with status=%s",
            movie_id,
            response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch trailer from TMDB"
        )

    try:
        videos = response.json().get("results", [])
    except ValueError:
        logger.warning("TMDB returned invalid JSON for movie_id=%s trailer lookup", movie_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid trailer response from TMDB"
        )

    trailer = select_tmdb_trailer(videos)
    if not trailer:
        raise HTTPException(status_code=404, detail="No YouTube trailer found")

    return TrailerResponse(youtube_key=trailer["key"])

@app.get("/api/genres", response_model=List[GenreResponse])
@limiter.limit("20/minute")
async def get_genres(request: Request):
    try:
        return [GenreResponse(**genre) for genre in get_available_genres()]
    except Exception as e:
        logger.exception("Error getting genres")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/categories", response_model=List[CategoryResponse])
@limiter.limit("20/minute")
async def get_categories(request: Request):
    try:
        return [CategoryResponse(**category) for category in get_available_categories()]
    except Exception as e:
        logger.exception("Error getting categories")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/favorites", response_model=List[MovieResponse])
@limiter.limit("20/minute")
async def get_favorites(request: Request):
    try:
        refresh_favorites_state()
        fav_movies = get_favorite_movies()
        return [MovieResponse(**movie) for movie in fav_movies]
    except Exception as e:
        logger.exception("Error getting favorites")
        raise HTTPException(status_code=500, detail="Internal error")

@app.post("/api/favorites", response_model=Dict[str, str])
@limiter.limit("5/minute")
async def add_to_favorites(request: Request, favorite: FavoriteRequest):
    try:
        success = add_favorite(favorite.name, favorite.year, FAVORITES_FILE)
        if success:
            # Update user preferences for better recommendations
            user_ip = request.client.host if request.client else "unknown"
            user_favorite_keys.setdefault(user_ip, set()).add((favorite.name, favorite.year))
            update_user_preferences_from_favorites(user_ip)
            return {"message": "Added to favorites"}
        else:
            raise HTTPException(status_code=400, detail="Not found or already in favorites")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error adding to favorites")
        raise HTTPException(status_code=500, detail="Internal error")

@app.delete("/api/favorites", response_model=Dict[str, str])
@limiter.limit("5/minute")
async def remove_from_favorites(request: Request, favorite: FavoriteRequest):
    try:
        success = remove_favorite(favorite.name, favorite.year, FAVORITES_FILE)
        if success:
            user_ip = request.client.host if request.client else "unknown"
            user_favorite_keys.setdefault(user_ip, set()).discard((favorite.name, favorite.year))
            update_user_preferences_from_favorites(user_ip)
            return {"message": "Removed from favorites"}
        else:
            raise HTTPException(status_code=404, detail="Not found in favorites")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error removing from favorites")
        raise HTTPException(status_code=500, detail="Internal error")

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
            stats["csv_data"] = csv_stats
        return stats
    except Exception as e:
        logger.exception("Error getting statistics")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/movies/{name}/{year}", response_model=MovieResponse)
@limiter.limit("30/minute")
async def get_movie_details(request: Request, name: str, year: int):
    try:
        for movie in movies:
            if movie.get('name', '').lower() == name.lower() and movie.get('year') == year:
                return MovieResponse(**movie)
        raise HTTPException(status_code=404, detail="Movie not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting movie details")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/movies/{name}/{year}/similar", response_model=RecommendationsResponse)
@limiter.limit("30/minute")
async def get_similar_movies_endpoint(
    request: Request,
    name: str,
    year: int,
    limit: int = Query(8, ge=1, le=20)
):
    """
    Get movies similar to a specific movie based on content features.
    Uses genre overlap, category, year proximity, and rating similarity.
    """
    try:
        # Find the target movie
        target_movie = None
        for movie in movies:
            if movie.get('name', '').lower() == name.lower() and movie.get('year') == year:
                target_movie = movie
                break
        
        if not target_movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        
        # Get similar movies
        similar = get_similar_movies(target_movie, limit=limit)
        
        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**item["movie"]),
                similarity_score=item["score"],
                match_reason=item["reason"]
            )
            for item in similar
        ]
        
        return RecommendationsResponse(
            recommendations=recommendations,
            based_on={
                "movie": target_movie.get("name"),
                "year": target_movie.get("year"),
                "genre": target_movie.get("genre"),
                "category": target_movie.get("category")
            },
            total_available=len(similar)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting similar movies")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/recommendations", response_model=RecommendationsResponse)
@limiter.limit("30/minute")
async def get_personalized_recommendations(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    include_viewed: bool = Query(False, description="Include movies user has already favorited")
):
    """
    Get personalized movie recommendations based on content-based filtering.
    
    Analyzes user's favorite movies and search history to recommend similar content.
    Factors considered:
    - Genre preferences from favorites and searches
    - Category alignment (Blockbuster, Indie, Classic, etc.)
    - Rating preferences
    - Year/decade preferences
    - Popularity signals
    """
    user_ip = request.client.host if request.client else "unknown"
    
    try:
        # Update preferences from search history
        prefs = get_user_preferences(user_ip)
        if user_ip in user_genres:
            prefs["liked_genres"].update(user_genres[user_ip])
        
        # Get recommendations
        scored_movies = get_content_recommendations(
            user_ip=user_ip,
            limit=limit,
            exclude_viewed=not include_viewed
        )
        
        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**item["movie"]),
                similarity_score=item["score"],
                match_reason=item["reason"]
            )
            for item in scored_movies
        ]
        
        # Build "based_on" info for transparency
        based_on = {
            "liked_genres": list(prefs.get("liked_genres", set()))[:5],
            "liked_categories": list(prefs.get("liked_categories", set()))[:3],
            "preferred_rating": round(prefs.get("rating_preference", 7.0), 1),
            "year_range": prefs.get("year_range", {"min": 1980, "max": 2024}),
            "favorites_count": len(prefs.get("favorite_movies", []))
        }
        
        return RecommendationsResponse(
            recommendations=recommendations,
            based_on=based_on,
            total_available=len(recommendations)
        )
        
    except Exception as e:
        logger.exception("Error generating recommendations")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/recommendations/discovery", response_model=RecommendationsResponse)
@limiter.limit("20/minute")
async def get_discovery_recommendations(
    request: Request,
    limit: int = Query(10, ge=1, le=30)
):
    """
    Get "Discovery" recommendations - movies outside usual preferences but highly rated.
    Surprises the user with hidden gems they might not have found otherwise.
    """
    user_ip = request.client.host if request.client else "unknown"
    
    try:
        prefs = get_user_preferences(user_ip)
        liked_genres = prefs.get("liked_genres", set())
        
        candidates = []
        for movie in movies:
            movie_key = (movie.get("name"), movie.get("year"))
            if movie_key in prefs.get("viewed_movies", set()):
                continue
            
            # Look for movies with different genres but high ratings
            movie_genres = set()
            if movie.get("genre"):
                movie_genres.update(g.strip().lower() for g in movie["genre"].split("/"))
            
            # Score based on discovery potential
            score = 0
            reasons = []
            
            # High rating is key for discovery
            rating = movie.get("rating", 0)
            if rating >= 8.0:
                score += 40
                reasons.append("Critically acclaimed")
            elif rating >= 7.5:
                score += 25
            
            # Slight genre overlap (not too similar, not too different)
            overlap = len(movie_genres & liked_genres) if liked_genres else 0
            if liked_genres:
                if overlap == 1:  # One genre in common
                    score += 20
                elif overlap == 0:  # Completely different
                    score += 10
                    reasons.append("New genre for you")
            
            # Underrated factor (high rating, lower box office)
            box_office = movie.get("box_office_millions", 0) or 0
            if rating >= 7.5 and box_office < 50:
                score += 20
                reasons.append("Hidden gem")
            
            # Older classics the user might have missed
            year = movie.get("year", 2000)
            if year < 1990 and rating >= 8.0:
                score += 15
                reasons.append("Classic")
            
            if score >= 35:
                reason_str = reasons[0] if reasons else "Discovery pick"
                if len(reasons) > 1:
                    reason_str += f" • {reasons[1]}"
                
                candidates.append({
                    "movie": movie,
                    "score": min(score, 100),
                    "reason": reason_str
                })
        
        # Sort by discovery score and shuffle slightly for variety
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**item["movie"]),
                similarity_score=item["score"],
                match_reason=item["reason"]
            )
            for item in candidates[:limit]
        ]
        
        return RecommendationsResponse(
            recommendations=recommendations,
            based_on={"mode": "discovery", "focus": "hidden gems and acclaimed films"},
            total_available=len(recommendations)
        )
        
    except Exception as e:
        logger.exception("Error generating discovery recommendations")
        raise HTTPException(status_code=500, detail="Internal error")

@app.exception_handler(404)
async def not_found_handler(request, exc):
    if isinstance(exc, FastAPIHTTPException) and exc.detail:
        return JSONResponse(status_code=404, content={"detail": exc.detail})
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host=HOST, port=PORT, reload=RELOAD)
