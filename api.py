"""
Movie Recommender API
FastAPI application exposing movie recommendation functionality as REST endpoints
"""

import os
import logging
import asyncio
import hashlib
import json
import httpx
import math
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any, Set

from fastapi import FastAPI, HTTPException, Query, status, Response
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv

import diskcache
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
    add_favorite, remove_favorite, get_favorite_movies, get_favorite_entries,
    load_favorites, save_favorites, format_movie, serialize_movies,
    expand_dataset_if_needed, compute_weighted_score, get_content_recommendations,
    get_personalized_content_recommendations, ensure_search_fields
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

# Reverse mapping: genre name -> TMDB ID
GENRE_NAME_TO_ID = {name.lower(): id for id, name in TMDB_GENRES.items()}

def get_genre_ids_from_names(genre_names: List[str]) -> List[int]:
    """Convert genre names to TMDB genre IDs"""
    genre_ids = []
    for name in genre_names:
        genre_id = GENRE_NAME_TO_ID.get(name.lower())
        if genre_id:
            genre_ids.append(genre_id)
    return genre_ids

# Persistent Disk Cache for TMDB responses and user state
cache = diskcache.Cache("./.api_cache")
CACHE_INDEX_PREFIX = "cache-index:v1:"
_background_tasks: Set[asyncio.Task] = set()
_scheduled_recommendations: Dict[tuple[int, int], asyncio.Task] = {}


def indexed_cache_key(namespace: str, values: Dict[str, Any]) -> str:
    """Build a compact, deterministic cache key and record it in an index.

    DiskCache indexes its SQLite keys, but keeping a namespace index lets us
    inspect/expire related entries without scanning the whole cache and avoids
    expensive, process-dependent Python hashes in hot paths.
    """
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()
    key = f"{namespace}:v1:{digest}"
    index_key = f"{CACHE_INDEX_PREFIX}{namespace}"
    keys = cache.get(index_key, set())
    if key not in keys:
        keys.add(key)
        cache.set(index_key, keys, expire=86400 * 30)
    return key


def schedule_background(coro) -> asyncio.Task:
    """Schedule cache warming work without delaying an HTTP response."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
    return task


def schedule_recommendation_warm(tmdb_id: int, top_n: int = 10) -> asyncio.Task:
    marker = (tmdb_id, top_n)
    existing = _scheduled_recommendations.get(marker)
    if existing is not None and not existing.done():
        return existing

    async def warm() -> List[Dict[str, Any]]:
        try:
            return await tmdb_get_recommendations(tmdb_id, top_n=top_n)
        finally:
            _scheduled_recommendations.pop(marker, None)

    task = schedule_background(warm())
    _scheduled_recommendations[marker] = task
    return task


async def prewarm_popular_searches() -> None:
    if not TMDB_API_KEY:
        return
    titles = ["Inception", "Interstellar", "The Dark Knight", "The Avengers"]
    await asyncio.gather(*(tmdb_search_movie(title, limit=5) for title in titles), return_exceptions=True)

def get_user_genres_set(user_ip: str) -> Set[str]:
    """Get unique genres searched/filtered by a specific user IP."""
    return cache.get(f"genres_{user_ip}", set())

def add_user_genre(user_ip: str, genre: str) -> None:
    """Track a unique genre for a specific user IP."""
    genres = get_user_genres_set(user_ip)
    if genre.lower() not in genres:
        genres.add(genre.lower())
        cache.set(f"genres_{user_ip}", genres, expire=86400 * 7)

def get_user_favorite_keys(user_ip: str) -> Set[tuple[str, int]]:
    """Get favorite movie keys associated with a specific user IP."""
    return cache.get(f"fav_keys_{user_ip}", set())

def add_user_favorite_key(user_ip: str, name: str, year: int) -> None:
    """Add a favorite movie key for a specific user IP."""
    keys = get_user_favorite_keys(user_ip)
    keys.add((name, year))
    cache.set(f"fav_keys_{user_ip}", keys, expire=86400 * 30)

def remove_user_favorite_key(user_ip: str, name: str, year: int) -> None:
    """Remove a favorite movie key for a specific user IP."""
    keys = get_user_favorite_keys(user_ip)
    keys.discard((name, year))
    cache.set(f"fav_keys_{user_ip}", keys, expire=86400 * 30)

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
    if TMDB_API_KEY:
        schedule_background(prewarm_popular_searches())
        logger.info("Scheduled TMDB cache pre-warming for popular searches")
    logger.info("API ready")
    yield
    for task in list(_background_tasks):
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
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
from pydantic import AliasChoices

class MovieResponse(BaseModel):
    id: Optional[int] = Field(None, validation_alias=AliasChoices("id", "movieId"))
    name: str
    year: int
    category: str
    genre: str
    description: Optional[str] = None
    box_office_millions: Optional[float] = None
    rating: float
    poster_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

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

class StreamResponse(BaseModel):
    movie_id: str
    stream_url: str
    provider: str

class TMDBRecommendationItem(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    poster_url: Optional[str] = None
    year: str
    rating: Optional[float] = None

class TMDBRecommendationsResponse(BaseModel):
    movies: List[TMDBRecommendationItem]

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

class WatchProviderItem(BaseModel):
    provider_id: int
    provider_name: str
    logo_url: str
    link: str
    type: str  # "stream", "rent", or "buy"

class WatchProvidersResponse(BaseModel):
    movie_id: int
    movie_title: str = "movies"
    country: str
    providers: List[WatchProviderItem]

# --- ADVANCED SEARCH MODELS ---
class AdvancedSearchFilters(BaseModel):
    """All possible search filters"""
    query: Optional[str] = Field(None, description="Movie title or keywords")
    genres: Optional[List[str]] = Field(None, description="Genre names (e.g., ['Action', 'Sci-Fi'])")
    year_min: Optional[int] = Field(None, description="Minimum release year")
    year_max: Optional[int] = Field(None, description="Maximum release year")
    rating_min: Optional[float] = Field(None, description="Minimum rating (0-10)")
    rating_max: Optional[float] = Field(None, description="Maximum rating (0-10)")
    cast: Optional[str] = Field(None, description="Actor name (e.g., 'Tom Hanks')")
    director: Optional[str] = Field(None, description="Director name (e.g., 'Christopher Nolan')")
    language: Optional[str] = Field(None, description="Original language (e.g., 'en', 'fr')")
    sort_by: Optional[str] = Field(
        "popularity.desc",
        description="Sort order: popularity.desc, vote_average.desc, release_date.desc, revenue.desc"
    )
    include_adult: bool = Field(False, description="Include adult content")
    region: Optional[str] = Field(None, description="ISO 3166-1 country code for release date filtering")

class AdvancedSearchResponse(BaseModel):
    """Response for advanced search"""
    search_results: List[MovieResponse]
    recommendations: List[MovieResponse]
    filters_used: AdvancedSearchFilters
    total_results: int
    source: str = "TMDB"

class SmartSearchRequest(BaseModel):
    """Request model for smart search endpoint"""
    search_query: str

# --- AFFILIATE LINKS CONFIGURATION ---
# Map TMDB provider IDs to your affiliate URLs.
# You can find provider IDs in the TMDB response (e.g., 9 = Amazon Prime, 350 = Apple TV)
AFFILIATE_LINKS = {
    9: "https://www.amazon.com/s?k=prime+video&tag=YOUR_AMAZON_TAG",       # Amazon Prime
    350: "https://tv.apple.com/?at=YOUR_APPLE_TAG",                        # Apple TV
    337: "https://www.disneyplus.com?cid=YOUR_DISNEY_AFFILIATE_ID",        # Disney Plus
    # Add more as you get accepted into affiliate programs!
}

async def fetch_trending_from_tmdb(pages: int = 3) -> List[Dict[str, Any]]:
    """Helper to fetch multiple pages of trending/popular movies from TMDB."""
    cache_key = f"trending_pages_{pages}"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        logger.info(f"Returning cached trending results for {pages} pages")
        return cached_result

    if not TMDB_API_KEY:
        # TMDB is required for trending data; return empty list when API key not configured
        return []

    all_results = []
    async with httpx.AsyncClient(timeout=7.0) as client:
        # Fetch multiple pages concurrently to avoid sequential HTTP wait
        tasks = [
            client.get(f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&page={page}")
            for page in range(1, pages + 1)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for response in responses:
            if isinstance(response, httpx.Response) and response.status_code == 200:
                try:
                    data = response.json()
                    all_results.extend(data.get("results", []))
                except Exception as e:
                    logger.warning(f"Failed to parse TMDB page response: {e}")
    
    if not all_results:
        # No TMDB results available for trending; return empty list
        return []

    # Deduplicate by TMDB ID
    unique_results = {r['id']: r for r in all_results}.values()
    
    formatted = []
    for m in unique_results:
        genre_ids = m.get("genre_ids", [])
        genre_names = [TMDB_GENRES.get(gid, "Unknown") for gid in genre_ids]
        formatted.append({
            "id": m.get("id"),
            "name": m.get("title"),
            "year": int(m.get("release_date", "0000")[:4]) if m.get("release_date") else 0,
            "description": m.get("overview"),
            "rating": round(m.get("vote_average", 0), 1),
            "poster_url": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else None,
            "genre": ", ".join(genre_names) if genre_names else "Movie",
            "category": "Trending",
            "box_office_millions": None
        })
    
    # Cache the formatted results for 24 hours
    cache.set(cache_key, formatted, expire=86400)
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


# --- TMDB helper utilities for TMDB-only recommendations ---
async def tmdb_search_movie(title: str, year: Optional[int] = None, limit: int = 5, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """Search TMDB for movies matching title (optionally year). Returns list of TMDB movie dicts."""
    if not TMDB_API_KEY:
        return []

    cache_key = indexed_cache_key("tmdb-search", {
        "title": title.strip().casefold(), "year": year, "limit": limit
    })
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params = {"api_key": TMDB_API_KEY, "query": title, "page": 1}
    if year:
        params["primary_release_year"] = year

    async def _fetch(c):
        try:
            resp = await c.get("https://api.themoviedb.org/3/search/movie", params=params)
            if resp.status_code != 200:
                logger.warning("TMDB search returned status %s for title=%s", resp.status_code, title)
                return []
            results = resp.json().get("results", [])[:limit]
            cache.set(cache_key, results, expire=86400)
            return results
        except Exception:
            logger.exception("TMDB search request failed for title=%s year=%s", title, year)
            return []

    if client:
        return await _fetch(client)
    else:
        async with httpx.AsyncClient(timeout=8.0) as client:
            return await _fetch(client)


async def tmdb_get_recommendations(tmdb_id: int, top_n: int = 10, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """Get TMDB recommendations for a TMDB movie ID and return formatted movie dicts."""
    if not TMDB_API_KEY:
        return []
    cache_key = indexed_cache_key("tmdb-recommendations", {"tmdb_id": tmdb_id, "top_n": top_n})
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    async def _fetch(c):
        try:
            resp = await c.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/recommendations", params={"api_key": TMDB_API_KEY, "page": 1})
            if resp.status_code != 200:
                logger.warning("TMDB recommendations returned status %s for id=%s", resp.status_code, tmdb_id)
                return []
            raw = resp.json().get("results", [])[:top_n]
            formatted = []
            for r in raw:
                formatted.append({
                    "id": r.get("id"),
                    "name": r.get("title"),
                    "year": int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
                    "category": "TMDB",
                    "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in r.get("genre_ids", [])]) if r.get("genre_ids") else "Movie",
                    "box_office_millions": None,
                    "rating": round(r.get("vote_average", 0), 1),
                    "description": r.get("overview"),
                    "poster_url": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None
                })
            cache.set(cache_key, formatted, expire=86400)
            return formatted
        except Exception:
            logger.exception("Failed to fetch TMDB recommendations for id=%s", tmdb_id)
            return []

    if client:
        return await _fetch(client)
    else:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await _fetch(client)


async def tmdb_get_similar(tmdb_id: int, top_n: int = 10, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """Get TMDB similar movies for a TMDB movie ID and return formatted movie dicts."""
    if not TMDB_API_KEY:
        return []
    cache_key = indexed_cache_key("tmdb-similar", {"tmdb_id": tmdb_id, "top_n": top_n})
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    async def _fetch(c):
        try:
            resp = await c.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/similar", params={"api_key": TMDB_API_KEY, "page": 1})
            if resp.status_code != 200:
                logger.warning("TMDB similar returned status %s for id=%s", resp.status_code, tmdb_id)
                return []
            raw = resp.json().get("results", [])[:top_n]
            formatted = []
            for r in raw:
                formatted.append({
                    "id": r.get("id"),
                    "name": r.get("title"),
                    "year": int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
                    "category": "TMDB",
                    "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in r.get("genre_ids", [])]) if r.get("genre_ids") else "Movie",
                    "box_office_millions": None,
                    "rating": round(r.get("vote_average", 0), 1),
                    "description": r.get("overview"),
                    "poster_url": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None
                })
            cache.set(cache_key, formatted, expire=86400)
            return formatted
        except Exception:
            logger.exception("Failed to fetch TMDB similar for id=%s", tmdb_id)
            return []

    if client:
        return await _fetch(client)
    else:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await _fetch(client)


async def tmdb_discover(
    genre_ids: Optional[List[int]] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    rating_min: Optional[float] = None,
    sort_by: str = "popularity.desc",
    page: int = 1,
    limit: int = 20,
    client: Optional[httpx.AsyncClient] = None
) -> List[Dict[str, Any]]:
    """Discover movies using TMDB discover endpoint with filters."""
    if not TMDB_API_KEY:
        return []
    
    params: Dict[str, Any] = {
        "api_key": TMDB_API_KEY,
        "page": page,
        "sort_by": sort_by,
    }
    
    if genre_ids:
        params["with_genres"] = ",".join(map(str, genre_ids))
    if year_min:
        params["primary_release_date.gte"] = f"{year_min}-01-01"
    if year_max:
        params["primary_release_date.lte"] = f"{year_max}-12-31"
    if rating_min is not None:
        params["vote_average.gte"] = rating_min
    
    cache_key = indexed_cache_key("tmdb-discover", params)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[:limit]

    async def _fetch(c):
        try:
            resp = await c.get("https://api.themoviedb.org/3/discover/movie", params=params)
            if resp.status_code != 200:
                logger.warning("TMDB discover returned status %s", resp.status_code)
                return []
            raw = resp.json().get("results", [])[:limit]
            formatted = []
            for r in raw:
                formatted.append({
                    "id": r.get("id"),
                    "name": r.get("title"),
                    "year": int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
                    "category": "TMDB",
                    "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in r.get("genre_ids", [])]) if r.get("genre_ids") else "Movie",
                    "box_office_millions": None,
                    "rating": round(r.get("vote_average", 0), 1),
                    "description": r.get("overview"),
                    "poster_url": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None,
                    "tmdb_popularity": r.get("popularity", 0.0),
                    "tmdb_rank": r.get("vote_count", 0)
                })
            cache.set(cache_key, formatted, expire=86400)
            return formatted
        except Exception:
            logger.exception("Failed to fetch TMDB discover")
            return []

    if client:
        return await _fetch(client)
    else:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await _fetch(client)


def convert_tmdb_to_content_format(tmdb_movie: Dict[str, Any]) -> Dict[str, Any]:
    """Convert TMDB movie format to the format expected by content functions."""
    genre_str = tmdb_movie.get("genre", "Movie")
    all_genres = [g.strip() for g in genre_str.split(",") if g.strip()]
    
    converted = {
        "name": tmdb_movie.get("name", ""),
        "year": tmdb_movie.get("year", 0),
        "category": tmdb_movie.get("category", "TMDB"),
        "genre": genre_str,
        "all_genres": all_genres,
        "box_office_millions": tmdb_movie.get("box_office_millions") or 0.0,
        "rating": tmdb_movie.get("rating", 0.0),
        "description": tmdb_movie.get("description"),
        "poster_url": tmdb_movie.get("poster_url"),
        "id": tmdb_movie.get("id"),
        "tmdb_popularity": tmdb_movie.get("tmdb_popularity", 0.0),
        "tmdb_rank": tmdb_movie.get("tmdb_rank", 0)
    }
    
    ensure_search_fields(converted)
    return converted


async def get_hybrid_recommendations(
    tmdb_id: Optional[int] = None,
    favorite_movies: Optional[List[Dict[str, Any]]] = None,
    genre_ids: Optional[List[int]] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    rating_min: Optional[float] = None,
    limit: int = 20,
    tmdb_weight: float = 0.4,
    content_weight: float = 0.6
) -> List[Dict[str, Any]]:
    """
    Get hybrid recommendations combining TMDB data with content-based scoring.
    
    Strategy:
    1. Fetch strong candidate pool from TMDB (recommendations/similar/discover)
    2. Convert candidates to content function format
    3. Score with content-based functions
    4. Blend TMDB rank/popularity with content score
    5. Return re-ranked list
    
    Args:
        tmdb_id: Optional TMDB movie ID to base recommendations on
        favorite_movies: Optional list of user's favorite movies for personalization
        genre_ids: Optional genre IDs for discover endpoint
        year_min: Optional minimum year filter
        year_max: Optional maximum year filter
        rating_min: Optional minimum rating filter
        limit: Maximum number of recommendations to return
        tmdb_weight: Weight for TMDB popularity/rank (0.0-1.0)
        content_weight: Weight for content-based score (0.0-1.0)
        
    Returns:
        List of movie dicts with hybrid_score, tmdb_score, and content_score added
    """
    if not TMDB_API_KEY:
        logger.warning("TMDB API key not configured, returning empty hybrid recommendations")
        return []
    
    candidates = []
    
    # 1. Fetch candidate pool from TMDB
    async with httpx.AsyncClient(timeout=15.0) as client:
        # If tmdb_id provided, get recommendations and similar movies
        if tmdb_id:
            recs = await tmdb_get_recommendations(tmdb_id, top_n=15, client=client)
            similar = await tmdb_get_similar(tmdb_id, top_n=15, client=client)
            candidates.extend(recs)
            candidates.extend(similar)
        
        # Always supplement with discover results for diversity
        discover_results = await tmdb_discover(
            genre_ids=genre_ids,
            year_min=year_min,
            year_max=year_max,
            rating_min=rating_min,
            sort_by="popularity.desc",
            page=1,
            limit=30,
            client=client
        )
        candidates.extend(discover_results)
    
    # Deduplicate by TMDB ID
    unique_candidates = {c.get("id"): c for c in candidates if c.get("id")}.values()
    candidates_list = list(unique_candidates)
    
    if not candidates_list:
        return []
    
    # 2. Convert to content function format
    content_candidates = [convert_tmdb_to_content_format(c) for c in candidates_list]
    
    # 3. Score with content-based functions
    if favorite_movies:
        # Personalized scoring based on favorites
        scored = get_personalized_content_recommendations(
            favorite_movies=favorite_movies,
            candidate_movies=content_candidates,
            metric="weighted",
            limit=len(content_candidates)
        )
    elif tmdb_id:
        # Find the target movie in candidates for similarity scoring
        target_movie = next((c for c in content_candidates if c.get("id") == tmdb_id), None)
        if target_movie:
            scored = get_content_recommendations(
                target_movie=target_movie,
                candidate_movies=content_candidates,
                metric="weighted",
                limit=len(content_candidates)
            )
        else:
            # Fallback: score all candidates against each other
            scored = []
            for c in content_candidates:
                # Use average similarity against other candidates
                other_candidates = [m for m in content_candidates if m.get("id") != c.get("id")]
                if other_candidates:
                    avg_score = sum(compute_weighted_score(c, m) for m in other_candidates[:10]) / min(10, len(other_candidates))
                else:
                    avg_score = 0.5
                c_copy = c.copy()
                c_copy['similarity_score'] = round(avg_score, 4)
                c_copy['match_reason'] = "Content-based similarity"
                scored.append(c_copy)
    else:
        # No target, use popularity-based content scoring
        scored = []
        for c in content_candidates:
            c_copy = c.copy()
            # Use rating and genre diversity as content signals
            c_copy['similarity_score'] = round(c.get('rating', 0) / 10.0, 4)
            c_copy['match_reason'] = "Rating-based content score"
            scored.append(c_copy)
    
    # 4. Blend TMDB rank/popularity with content score
    final_results = []
    for movie in scored:
        tmdb_score = 0.0
        
        # Normalize TMDB popularity (log scale to handle outliers)
        popularity = movie.get("tmdb_popularity", 0.0)
        if popularity > 0:
            tmdb_score = min(1.0, math.log(popularity + 1) / math.log(1000))
        
        # Normalize TMDB vote count
        vote_count = movie.get("tmdb_rank", 0)
        if vote_count > 0:
            rank_score = min(1.0, math.log(vote_count + 1) / math.log(10000))
            tmdb_score = (tmdb_score + rank_score) / 2
        
        content_score = movie.get("similarity_score", 0.0)
        
        # Blend scores
        hybrid_score = (tmdb_score * tmdb_weight) + (content_score * content_weight)
        
        movie_copy = movie.copy()
        movie_copy['hybrid_score'] = round(hybrid_score, 4)
        movie_copy['tmdb_score'] = round(tmdb_score, 4)
        movie_copy['content_score'] = round(content_score, 4)
        final_results.append(movie_copy)
    
    # 5. Sort by hybrid score and return
    final_results.sort(
        key=lambda x: (x['hybrid_score'], x.get('rating', 0.0), x.get('tmdb_popularity', 0.0)),
        reverse=True
    )
    
    return final_results[:limit]

async def get_person_id(name: str) -> Optional[int]:
    """Get TMDB person ID from name"""
    cache_key = f"person_id_{name.lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    
    if not TMDB_API_KEY:
        return None
    
    async with httpx.AsyncClient(timeout=7.0) as client:
        try:
            response = await client.get(
                "https://api.themoviedb.org/3/search/person",
                params={"api_key": TMDB_API_KEY, "query": name}
            )
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    person_id = results[0].get("id")
                    cache.set(cache_key, person_id, expire=86400 * 7)  # Cache for 7 days
                    return person_id
        except Exception as e:
            logger.warning(f"Failed to get person ID for {name}: {e}")
    
    return None

def extract_filters_from_text(text: str) -> Dict[str, Any]:
    """Simple rule-based filter extraction from text"""
    filters: Dict[str, Any] = {}
    if not text:
        return filters
        
    text_lower = text.lower()
    
    # Extract genres
    genre_keywords = {name.lower(): name for name in TMDB_GENRES.values()}
    genre_keywords["sci-fi"] = "Sci-Fi"
    genre_keywords["scifi"] = "Sci-Fi"
    genre_keywords["science fiction"] = "Sci-Fi"
    
    genres = []
    for keyword, genre_name in genre_keywords.items():
        if keyword in text_lower:
            if genre_name not in genres:
                genres.append(genre_name)
    
    if genres:
        filters["genres"] = genres
    
    # Extract years
    import re
    year_pattern = r'\b(19[0-9]{2}|20[0-9]{2})\b'
    years = re.findall(year_pattern, text)
    if years:
        years_int = [int(y) for y in years]
        if len(years_int) == 1:
            filters["year_min"] = years_int[0]
            filters["year_max"] = years_int[0]
        else:
            filters["year_min"] = min(years_int)
            filters["year_max"] = max(years_int)
    
    # Extract rating
    rating_pattern = r'rating\s*(?:above|over|>|>=)\s*([0-9.]+)'
    rating_match = re.search(rating_pattern, text_lower)
    if rating_match:
        filters["rating_min"] = float(rating_match.group(1))
    
    # Extract cast / director mentions
    cast_match = re.search(r'(?:starring|with|featuring)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
    if cast_match:
        filters["cast"] = cast_match.group(1)
        
    director_match = re.search(r'(?:directed by|director)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text, re.IGNORECASE)
    if director_match:
        filters["director"] = director_match.group(1)
    
    return filters

def get_user_preferences(user_ip: str) -> Dict[str, Any]:
    """Get or initialize user preferences for content-based filtering."""
    prefs = cache.get(f"prefs_{user_ip}")
    if prefs is None:
        prefs = {
            "viewed_movies": set(),  # (name, year) tuples
            "liked_genres": set(),
            "liked_categories": set(),
            "rating_preference": 7.0,  # Default preference
            "year_range": {"min": 1980, "max": 2024},
            "favorite_movies": [],  # List of movie dicts
        }
    return prefs

def save_user_preferences(user_ip: str, prefs: Dict[str, Any]) -> None:
    """Save user preferences to disk cache."""
    cache.set(f"prefs_{user_ip}", prefs, expire=86400 * 30)

def update_user_preferences_from_favorites(user_ip: str) -> None:
    """Update user preferences based on their favorite movies."""
    prefs = get_user_preferences(user_ip)
    fav_keys = get_user_favorite_keys(user_ip)
    prefs["viewed_movies"] = {(name, year) for name, year in fav_keys}
    save_user_preferences(user_ip, prefs)






@app.api_route("/ping", methods=["GET", "HEAD"])
async def ping():
    """Ultra-lightweight endpoint for keep-alive services."""
    return "pong"

# Root endpoint
@app.api_route("/", methods=["GET", "HEAD"])
@limiter.limit("60/minute")
async def root(request: Request):
    """API root endpoint with basic information."""
    refresh_favorites_state()
    return {
        "message": "Movie Recommender API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "favorites_count": len(get_favorite_entries())
    }

@app.get("/sitemap.xml")
async def generate_sitemap():
    """
    Dynamically generates a sitemap.xml for Google to crawl.
    """
    # Frontend base URL (from allowed origins config)
    base_url = "https://cine-craft-box.lovable.app"
    
    # Popular movie IDs to seed the sitemap
    # In production, query your database for all movie IDs
    movie_ids = [550, 157336, 27205, 299536, 634649]  # Fight Club, Interstellar, Inception, Avengers, Dune
    
    # Build the XML structure
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    # Add homepage
    xml += f'  <url>\n    <loc>{base_url}/</loc>\n    <priority>1.0</priority>\n  </url>\n'
    
    # Add movie pages
    # Update the path if your frontend uses a different structure (e.g., /movies/{id} or /details/{id})
    for movie_id in movie_ids:
        xml += f'  <url>\n    <loc>{base_url}/movie/{movie_id}</loc>\n    <priority>0.8</priority>\n  </url>\n'
    
    xml += '</urlset>'
    
    # Return as XML
    return Response(content=xml, media_type="application/xml")

@app.get("/api/movies/trending")
@limiter.limit("20/minute")
async def get_trending_movies(request: Request, genre: Optional[str] = Query(None)):
    """Fetch trending movies. Returns 10 by default, or filtered results, with caching"""
    user_ip = request.client.host if request.client else "unknown"
    
    if genre:
        add_user_genre(user_ip, genre)

    cache_key = f"trending_v1"
    cached = cache.get(cache_key)
    if cached is not None:
        trending_data = cached
    else:
        trending_data = await fetch_trending_from_tmdb()
        if trending_data:
            # Cache for 30 minutes
            cache.set(cache_key, trending_data, expire=1800)

    # Fall back to local dataset if TMDB returns no data
    if not trending_data:
        from movie_recommender import movies as local_movies
        if genre:
            g_lower = genre.lower()
            fallback_data = [
                m for m in local_movies
                if g_lower in m.get('genre', '').lower() or any(g_lower in ag.lower() for ag in m.get('all_genres', []))
            ]
        else:
            fallback_data = local_movies
        # Sort local movies by rating descending and return up to 20
        fallback_data = sorted(fallback_data, key=lambda x: x.get('rating', 0.0), reverse=True)[:20]
        return [MovieResponse(**m) for m in fallback_data]

    # Filter by genre if provided
    if genre:
        g_lower = genre.lower()
        trending_data = [m for m in trending_data if g_lower in (m.get('genre') or '').lower()]
    else:
        # Initial view: show only top 10
        trending_data = trending_data[:10]

    # Return simple list for frontend compatibility
    return [MovieResponse(**m) for m in trending_data]

@app.get("/api/movies/search")
@limiter.limit("30/minute")
async def search_movies(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    genre: Optional[str] = Query(None),
    year: Optional[int] = Query(None, description="Release year to filter"),
    max_results: int = Query(60, ge=1, le=200)
):
    """
    Unified Search Endpoint:
    - Locked: Searches only live TMDB trending data (Name & Genre).
    - Unlocked: Searches BOTH live TMDB and Classic Vault (CSV).
    """
    user_ip = request.client.host if request.client else "unknown"
    
    if genre:
        add_user_genre(user_ip, genre)
    
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
        year_match = (year is None) or (m.get('year') == year)

        if (name_match or q_genre_match) and genre_match and year_match:
            tmdb_matches.append(m)

    # Return TMDB-only matches, creating Pydantic objects only for requested slice
    return [MovieResponse(**m) for m in tmdb_matches[:max_results]]

@app.get("/api/movies/advanced-search", response_model=AdvancedSearchResponse)
@limiter.limit("20/minute")
async def advanced_search(
    request: Request,
    query: Optional[str] = Query(None, description="Movie title or keywords"),
    keywords: Optional[str] = Query(None, description="Keyword or phrase to search for"),
    genres: Optional[str] = Query(None, description="Comma-separated genre names (e.g., 'Action,Sci-Fi')"),
    year_min: Optional[int] = Query(None, description="Minimum release year"),
    year_max: Optional[int] = Query(None, description="Maximum release year"),
    rating_min: Optional[float] = Query(None, description="Minimum rating (0-10)"),
    rating_max: Optional[float] = Query(None, description="Maximum rating (0-10)"),
    cast: Optional[str] = Query(None, description="Actor name"),
    director: Optional[str] = Query(None, description="Director name"),
    language: Optional[str] = Query(None, description="Original language code (e.g. en)"),
    region: Optional[str] = Query(None, description="ISO 3166-1 country code"),
    include_adult: bool = Query(False, description="Include adult content"),
    sort_by: str = Query("popularity.desc", description="Sort order"),
    page: int = Query(1, ge=1, le=10, description="Page number for pagination"),
    limit: int = Query(20, ge=1, le=50, description="Results per page"),
):
    """
    Advanced search with multiple filters and automatic recommendations.
    
    Examples:
    - /api/movies/advanced-search?genres=Action,Sci-Fi&year_min=2010&rating_min=7.0
    - /api/movies/advanced-search?query=space&year_max=2000
    - /api/movies/advanced-search?cast=Tom+Hanks&director=Steven+Spielberg
    - /api/movies/advanced-search?genres=Comedy&sort_by=revenue.desc
    """
    user_ip = request.client.host if request.client else "unknown"
    
    # FastAPI Query objects are exposed when this handler is called directly
    # (the smart-search endpoint does that), so unwrap their defaults first.
    def _default(value):
        return getattr(value, "default", value)

    query, keywords, genres = _default(query), _default(keywords), _default(genres)
    year_min, year_max = _default(year_min), _default(year_max)
    rating_min, rating_max = _default(rating_min), _default(rating_max)
    cast, director = _default(cast), _default(director)
    language, region = _default(language), _default(region)
    include_adult = _default(include_adult)

    # Treat keywords as a convenient alias for the text query.  This keeps the
    # public API expressive while TMDB still receives one text constraint.
    query = query or keywords

    # Normalize parameters if Query defaults are passed during programmatic calls
    if not isinstance(sort_by, str):
        sort_by = getattr(sort_by, "default", "popularity.desc")
    if not isinstance(page, int):
        page = getattr(page, "default", 1)
    if not isinstance(limit, int):
        limit = getattr(limit, "default", 20)

    # 1. Parse genres if provided
    genre_list = [g.strip() for g in genres.split(',')] if genres else []
    genre_ids = get_genre_ids_from_names(genre_list) if genre_list else []
    
    # Track user preferences for personalization
    for genre in genre_list:
        if genre:
            add_user_genre(user_ip, genre)
    
    if year_min is not None and year_max is not None and year_min > year_max:
        raise HTTPException(status_code=422, detail="year_min cannot be greater than year_max")
    if rating_min is not None and rating_max is not None and rating_min > rating_max:
        raise HTTPException(status_code=422, detail="rating_min cannot be greater than rating_max")
    if rating_min is not None and not 0 <= rating_min <= 10:
        raise HTTPException(status_code=422, detail="rating_min must be between 0 and 10")
    if rating_max is not None and not 0 <= rating_max <= 10:
        raise HTTPException(status_code=422, detail="rating_max must be between 0 and 10")

    # TMDB's discover endpoint supports the complete filter set, including
    # text, cast, and crew.  Use search only for a plain title lookup because
    # /search/movie silently ignores the other filters.
    has_discovery_filters = any((genre_ids, year_min, year_max, rating_min is not None,
                                 rating_max is not None, cast, director, language, region,
                                 include_adult))
    use_discover = not query or has_discovery_filters
    params: Dict[str, Any] = {
        "api_key": TMDB_API_KEY,
        "page": page,
        "sort_by": sort_by,
        "include_adult": include_adult,
    }

    if region:
        params["region"] = region.upper()
    if language:
        params["with_original_language"] = language.lower()
    
    if cast:
        cast_id = await get_person_id(cast)
        if cast_id:
            params["with_cast"] = cast_id
    if director:
        director_id = await get_person_id(director)
        if director_id:
            params["with_crew"] = director_id

    if use_discover:
        if query:
            params["with_text_query"] = query
        if genre_ids:
            params["with_genres"] = ",".join(map(str, genre_ids))
        if year_min:
            params["primary_release_date.gte"] = f"{year_min}-01-01"
        if year_max:
            params["primary_release_date.lte"] = f"{year_max}-12-31"
        if rating_min is not None:
            params["vote_average.gte"] = rating_min
        if rating_max is not None:
            params["vote_average.lte"] = rating_max
    else:
        params["query"] = query

    # 3. Generate cache key
    # Keep disabled-mode responses separate from live TMDB responses.  This
    # matters when a process starts without a key and is later configured (and
    # also prevents a cached empty response masking a healthy TMDB result).
    cache_params = {key: value for key, value in params.items() if key != "api_key"}
    cache_key = indexed_cache_key(
        "advanced-search-tmdb" if TMDB_API_KEY else "advanced-search-local",
        cache_params,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info(f"Returning cached advanced search for {query or 'filters'}")
        return AdvancedSearchResponse.model_validate(cached) if isinstance(cached, dict) else cached

    # 4. Execute TMDB API call
    search_results = []
    total_results = 0
    if TMDB_API_KEY:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                url = ("https://api.themoviedb.org/3/discover/movie" if use_discover
                       else "https://api.themoviedb.org/3/search/movie")
                
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    raw_results = data.get("results", [])
                    total_results = int(data.get("total_results", len(raw_results)))
                    
                    # Format results
                    for r in raw_results[:limit]:
                        genre_names = [TMDB_GENRES.get(gid, "Unknown") for gid in r.get("genre_ids", [])]
                        search_results.append(MovieResponse(
                            id=r.get("id"),
                            name=r.get("title", ""),
                            year=int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
                            category="Search Result",
                            genre=", ".join(genre_names) if genre_names else "Movie",
                            description=r.get("overview"),
                            rating=round(r.get("vote_average", 0.0), 1),
                            poster_url=f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get("poster_path") else None,
                            box_office_millions=None
                        ))
                else:
                    logger.warning(f"TMDB API returned {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error in advanced search: {e}")
                raise HTTPException(status_code=500, detail="Search failed")

    # 5. Reuse warm recommendations; otherwise populate them in the
    # background so the search response is not held up by a second TMDB call.
    recommendations = []
    if search_results:
        top_match_id = search_results[0].id
        if top_match_id:
            rec_cache_key = indexed_cache_key(
                "tmdb-recommendations", {"tmdb_id": top_match_id, "top_n": 10}
            )
            cached_recs = cache.get(rec_cache_key)
            if cached_recs is not None:
                recommendations = [MovieResponse(**r) for r in cached_recs]
            elif TMDB_API_KEY:
                recommendation_task = schedule_recommendation_warm(top_match_id, top_n=10)
                # A mocked/already-local task can finish in the same event
                # loop turn; real network work continues after the response.
                await asyncio.sleep(0)
                if recommendation_task.done() and not recommendation_task.cancelled():
                    recs = recommendation_task.result()
                    recommendations = [MovieResponse(**r) for r in recs]
    
    # 6. Build response
    filters = AdvancedSearchFilters(
        query=query,
        genres=genre_list if genre_list else None,
        year_min=year_min,
        year_max=year_max,
        rating_min=rating_min,
        rating_max=rating_max,
        cast=cast,
        director=director,
        language=language,
        region=region.upper() if region else None,
        include_adult=include_adult,
        sort_by=sort_by
    )
    
    response = AdvancedSearchResponse(
        search_results=search_results,
        recommendations=recommendations,
        filters_used=filters,
        total_results=total_results,
        source="TMDB"
    )
    
    # Cache for 1 hour
    cache.set(cache_key, response.model_dump(), expire=3600)
    
    return response

@app.post("/api/movies/smart-search", response_model=AdvancedSearchResponse)
@limiter.limit("15/minute")
async def smart_search(
    request: Request,
    search_query: Optional[str] = Query(None, description="Natural language search query"),
    body: Optional[SmartSearchRequest] = None
):
    """
    Natural language search that parses the query and applies filters.
    Example: "sci-fi action movies from 2015 to 2020 with rating above 7"
    """
    query_text = (body.search_query if body and body.search_query else search_query) or ""
    
    filters = extract_filters_from_text(query_text)
    
    return await advanced_search(
        request=request,
        query=filters.get("query"),
        genres=",".join(filters.get("genres", [])) if filters.get("genres") else None,
        year_min=filters.get("year_min"),
        year_max=filters.get("year_max"),
        rating_min=filters.get("rating_min"),
        rating_max=filters.get("rating_max"),
        cast=filters.get("cast"),
        director=filters.get("director")
    )

@app.get("/api/movies/featured", response_model=FeaturedResponse)
@limiter.limit("20/minute")
async def get_featured_movies(request: Request):
    """Featured: TMDB popular (latest) and top rated (old favorites) with caching"""
    if not TMDB_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="TMDB integration is not configured")

    cache_key = "featured_popular_top_v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return FeaturedResponse(latest_movies=[MovieResponse(**m) for m in cached.get("latest", [])], old_movies=[MovieResponse(**m) for m in cached.get("old", [])])

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            pop_resp = await client.get("https://api.themoviedb.org/3/movie/popular", params={"api_key": TMDB_API_KEY, "page": 1})
            top_resp = await client.get("https://api.themoviedb.org/3/movie/top_rated", params={"api_key": TMDB_API_KEY, "page": 1})
        except Exception:
            logger.exception("Failed to fetch TMDB for featured/top")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch TMDB data")

    if pop_resp.status_code != 200 or top_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="TMDB returned error")

    try:
        pop_results = pop_resp.json().get("results", [])[:10]
        top_results = top_resp.json().get("results", [])[:10]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid TMDB response")

    latest_movies = []
    old_movies = []
    for r in pop_results:
        latest_movies.append({
            "id": r.get("id"),
            "name": r.get("title"),
            "year": int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
            "description": r.get("overview"),
            "category": "Trending",
            "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in r.get("genre_ids", [])]) if r.get("genre_ids") else "Movie",
            "box_office_millions": None,
            "rating": round(r.get("vote_average", 0), 1),
            "poster_url": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None
        })
    for r in top_results:
        old_movies.append({
            "id": r.get("id"),
            "name": r.get("title"),
            "year": int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
            "description": r.get("overview"),
            "category": "Top",
            "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in r.get("genre_ids", [])]) if r.get("genre_ids") else "Movie",
            "box_office_millions": None,
            "rating": round(r.get("vote_average", 0), 1),
            "poster_url": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None
        })

    # Cache for 1 hour
    cache.set(cache_key, {"latest": latest_movies, "old": old_movies}, expire=3600)

    return FeaturedResponse(latest_movies=[MovieResponse(**m) for m in latest_movies], old_movies=[MovieResponse(**m) for m in old_movies])

@app.get("/api/movies/top", response_model=List[MovieResponse])
@limiter.limit("20/minute")
async def get_top_movies(request: Request, limit: int = Query(10, ge=1, le=50)):
    if not TMDB_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="TMDB integration is not configured")

    cache_key = f"top_rated_{limit}_v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return [MovieResponse(**m) for m in cached]

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.get("https://api.themoviedb.org/3/movie/top_rated", params={"api_key": TMDB_API_KEY, "page": 1})
        except Exception:
            logger.exception("Failed to fetch TMDB top movies")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch TMDB data")

    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="TMDB returned error")

    try:
        raw = resp.json().get("results", [])[:limit]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid TMDB response")

    top_movies = []
    for r in raw:
        top_movies.append({
            "id": r.get("id"),
            "name": r.get("title"),
            "year": int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
            "description": r.get("overview"),
            "category": "Top",
            "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in r.get("genre_ids", [])]) if r.get("genre_ids") else "Movie",
            "box_office_millions": None,
            "rating": round(r.get("vote_average", 0), 1),
            "poster_url": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None
        })

    # Cache for 1 hour
    cache.set(cache_key, top_movies, expire=3600)

    return [MovieResponse(**m) for m in top_movies]

@app.get("/api/movies/{movie_id}/trailer", response_model=TrailerResponse)
@limiter.limit("20/minute")
async def get_movie_trailer(request: Request, movie_id: int):
    if not TMDB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TMDB integration is not configured"
        )

    cache_key = f"trailer_{movie_id}"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return TrailerResponse(youtube_key=cached_result)

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

    cache.set(cache_key, trailer["key"], expire=86400 * 7)  # Cache trailers for 7 days
    return TrailerResponse(youtube_key=trailer["key"])

@app.get("/api/movies/{movie_id}/stream", response_model=StreamResponse)
@limiter.limit("30/minute")
async def get_movie_stream_url(request: Request, movie_id: str):
    """
    Returns the high-speed streaming embed URL for a given TMDB ID.
    This bypasses the need to host video files locally.
    """
    clean_id = str(movie_id).strip()
    
    # Clean, low-ad developer endpoint
    stream_url = f"https://vidlink.pro/movie/{clean_id}"
    
    return StreamResponse(
        movie_id=clean_id,
        stream_url=stream_url,
        provider="Phlox Premium Secure Stream"
    )

@app.get("/api/movies/{movie_id}/recommendations", response_model=TMDBRecommendationsResponse)
@limiter.limit("20/minute")
async def get_movie_recommendations(request: Request, movie_id: int):
    if not TMDB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TMDB integration is not configured"
        )

    clean_id = str(movie_id).strip()
    cache_key = f"tmdb_rec_{clean_id}"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return TMDBRecommendationsResponse(movies=cached_result)

    url = f"https://api.themoviedb.org/3/movie/{clean_id}/recommendations"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params={"api_key": TMDB_API_KEY})
    except httpx.RequestError:
        logger.exception("Failed to reach TMDB recommendations endpoint for movie_id=%s", clean_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch recommendations from TMDB"
        )

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Movie not found on TMDB")

    if response.status_code != status.HTTP_200_OK:
        logger.warning(
            "TMDB recommendations lookup failed for movie_id=%s with status=%s",
            clean_id,
            response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch recommendations from TMDB"
        )

    try:
        raw_results = response.json().get("results", [])
    except ValueError:
        logger.warning("TMDB returned invalid JSON for movie_id=%s recommendations lookup", clean_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid recommendations response from TMDB"
        )

    recommendations = [
        TMDBRecommendationItem(
            id=m.get("id"),
            name=m.get("title"),
            poster_url=f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else None,
            year=(m.get("release_date") or "0000")[:4],
            rating=m.get("vote_average"),
        )
        for m in raw_results[:10]
    ]

    cache.set(cache_key, recommendations, expire=86400)  # Cache recommendations for 24 hours
    return TMDBRecommendationsResponse(movies=recommendations)

@app.get("/api/genres", response_model=List[GenreResponse])
@limiter.limit("20/minute")
async def get_genres(request: Request):
    try:
        # Return TMDB-known genres (counts not tracked locally)
        return [GenreResponse(genre=name, count=0) for _id, name in TMDB_GENRES.items()]
    except Exception as e:
        logger.exception("Error getting genres")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/categories", response_model=List[CategoryResponse])
@limiter.limit("20/minute")
async def get_categories(request: Request):
    try:
        # No local categories available when using TMDB-only mode
        return []
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
            add_user_favorite_key(user_ip, favorite.name, favorite.year)
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
            remove_user_favorite_key(user_ip, favorite.name, favorite.year)
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
        "movies_count": None,
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
            "total_movies": None,
            "favorites_count": len(get_favorite_entries()),
            "available_genres": len(TMDB_GENRES),
            "available_categories": 0
        }
        if _HAS_CSV_STATS:
            csv_stats = get_csv_statistics()
            stats["csv_data"] = csv_stats
        return stats
    except Exception as e:
        logger.exception("Error getting statistics")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/movies/{movie_id}/watch-providers", response_model=WatchProvidersResponse)
@limiter.limit("30/minute")
async def get_watch_providers(
    request: Request,
    movie_id: int, 
    country_code: str = Query(default="US", description="ISO 3166-1 country code (e.g., US, GB, NG)")
):
    """
    Fetches where a movie is streaming, renting, or buying, and injects affiliate links.
    """
    if not TMDB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TMDB integration is not configured"
        )
    
    clean_id = str(movie_id).strip()
    cache_key = f"watch_providers_{clean_id}_{country_code}"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    # 1. Fetch Movie Details (to get the title) AND Watch Providers at the same time
    import asyncio
    async with httpx.AsyncClient(timeout=10.0) as client:
        details_task = client.get(
            f"https://api.themoviedb.org/3/movie/{clean_id}", 
            params={"api_key": TMDB_API_KEY}
        )
        providers_task = client.get(
            f"https://api.themoviedb.org/3/movie/{clean_id}/watch/providers", 
            params={"api_key": TMDB_API_KEY}
        )
        try:
            details_response, providers_response = await asyncio.gather(details_task, providers_task)
        except httpx.RequestError:
            logger.exception("Failed to reach TMDB endpoints for movie_id=%s", clean_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch data from TMDB"
            )
            
    if details_response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="Movie not found on TMDB")
        
    if details_response.status_code != 200 or providers_response.status_code != 200:
        logger.warning(
            "TMDB fetch failed for movie_id=%s. Details status=%s, Providers status=%s",
            clean_id,
            details_response.status_code,
            providers_response.status_code
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch data from TMDB"
        )
        
    movie_data = details_response.json()
    providers_data = providers_response.json()
    
    # Get the movie title and clean it for a URL (replace spaces with +)
    movie_title = movie_data.get("title", "movies")
    search_query = movie_title.replace(" ", "+")
    
    # 2. Create your dynamic Amazon Affiliate Link 💰
    AMAZON_TAG = "phloxmovies20-20"
    amazon_link = f"https://www.amazon.com/s?k={search_query}&tag={AMAZON_TAG}"
    
    # 3. Process the providers
    results = providers_data.get("results", {})
    country_data = results.get(country_code, {})
    
    providers_list = []
    categories = {"flatrate": "stream", "rent": "rent", "buy": "buy"}
    
    for tmdb_category, our_type in categories.items():
        if tmdb_category in country_data:
            for provider in country_data[tmdb_category]:
                prov_id = provider["provider_id"]
                
                # If it's Amazon Video (ID 10), use your dynamic affiliate link!
                # Otherwise, use the default TMDB link.
                if prov_id == 10: 
                    final_link = amazon_link
                else:
                    final_link = country_data.get("link", "#")
                
                providers_list.append(WatchProviderItem(
                    provider_id=prov_id,
                    provider_name=provider["provider_name"],
                    logo_url=f"https://image.tmdb.org/t/p/original{provider['logo_path']}",
                    link=final_link,
                    type=our_type
                ))

    result = WatchProvidersResponse(
        movie_id=int(clean_id),
        movie_title=movie_title,
        country=country_code,
        providers=providers_list
    )
    
    # Cache for 24 hours
    cache.set(cache_key, result, expire=86400)
    
    return result

@app.get("/api/movies/{name}/{year}", response_model=MovieResponse)
@limiter.limit("30/minute")
async def get_movie_details(request: Request, name: str, year: int):
    try:
        if not TMDB_API_KEY:
            raise HTTPException(status_code=503, detail="TMDB integration is not configured")
        results = await tmdb_search_movie(name, year=year, limit=5)
        if not results:
            raise HTTPException(status_code=404, detail="Movie not found on TMDB")
        m = results[0]
        movie = {
            "id": m.get("id"),
            "name": m.get("title"),
            "year": int((m.get("release_date") or "0000")[:4]) if m.get("release_date") else 0,
            "description": m.get("overview"),
            "category": "TMDB",
            "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in m.get("genre_ids", [])]) if m.get("genre_ids") else "Movie",
            "box_office_millions": None,
            "rating": round(m.get("vote_average", 0), 1),
            "poster_url": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get('poster_path') else None
        }
        return MovieResponse(**movie)
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
    TMDB-based similar movies endpoint. Does not use the local dataset.
    Searches TMDB for the given title+year, then returns TMDB's recommendations for that movie.
    """
    try:
        if not TMDB_API_KEY:
            raise HTTPException(status_code=503, detail="TMDB integration is not configured")

        # Search TMDB for the movie title and narrow by year
        results = await tmdb_search_movie(name, year=year, limit=5)
        if not results:
            raise HTTPException(status_code=404, detail="Movie not found on TMDB")

        tmdb_movie = results[0]
        tmdb_id = tmdb_movie.get("id")

        recs = await tmdb_get_recommendations(tmdb_id, top_n=limit)

        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**m),
                similarity_score=m.get('rating') or 0.0,
                match_reason="TMDB recommendation"
            )
            for m in recs
        ]

        return RecommendationsResponse(
            recommendations=recommendations,
            based_on={
                "query": name,
                "matched_title": tmdb_movie.get("title"),
                "matched_year": int((tmdb_movie.get("release_date") or "0000")[:4]) if tmdb_movie.get("release_date") else year,
                "source": "tmdb"
            },
            total_available=len(recommendations)
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting similar movies from TMDB")
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/api/recommend/by-title", response_model=RecommendationsResponse)
@limiter.limit("30/minute")
async def recommend_by_title(
    request: Request,
    title: str = Query(..., description="Movie title to base recommendations on"),
    top_n: int = Query(8, ge=1, le=50)
):
    """
    Recommend movies based on a provided movie title. This endpoint is resilient:
    - Attempts to match the title against the local dataset (fast, offline).
    - If no local match is found and TMDB is configured, falls back to TMDB search
      and uses TMDB's recommendations for that title.
    """
    try:
        if not title or not title.strip():
            raise HTTPException(status_code=400, detail="Title is required")

        # Search TMDB for the title (caching is handled inside tmdb_search_movie)
        results = await tmdb_search_movie(title, limit=5)
        if not results:
            raise HTTPException(status_code=404, detail="Movie not found on TMDB")

        movie0 = results[0]
        tmdb_id = movie0.get("id")

        # Fetch TMDB recommendations (caching is handled inside tmdb_get_recommendations)
        recs = await tmdb_get_recommendations(tmdb_id, top_n=top_n)

        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**m),
                similarity_score=m.get('rating') or 0.0,
                match_reason="TMDB recommendation"
            )
            for m in recs
        ]

        return RecommendationsResponse(
            recommendations=recommendations,
            based_on={"query": title, "matched_title": movie0.get("title"), "source": "tmdb"},
            total_available=len(recommendations)
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in recommend_by_title endpoint")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/recommend/content/by-title", response_model=RecommendationsResponse)
@limiter.limit("30/minute")
async def recommend_content_by_title(
    request: Request,
    title: str = Query(..., description="Movie title to base recommendations on"),
    metric: str = Query("weighted", description="Similarity metric: weighted, jaccard, cosine"),
    top_n: int = Query(8, ge=1, le=50)
):
    """
    Content-based recommendations using the local dataset (falls back to TMDB for title matching).
    """
    try:
        import movie_recommender as mr

        # 1) Try local dataset match first
        local_matches = mr.find_matches(title, max_results=5)
        if local_matches:
            target = local_matches[0]
            source = "local"
        else:
            # 2) Fallback to TMDB lookup to construct a target movie
            results = await tmdb_search_movie(title, limit=5)
            if not results:
                raise HTTPException(status_code=404, detail="Movie not found (local or TMDB)")
            m = results[0]
            target = {
                "name": m.get("title"),
                "year": int((m.get("release_date") or "0000")[:4]) if m.get("release_date") else 0,
                "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in m.get("genre_ids", [])]) if m.get("genre_ids") else "Movie",
                "box_office_millions": None,
                "rating": round(m.get("vote_average", 0.0), 1),
                "category": "TMDB"
            }
            mr.ensure_search_fields(target)
            source = "tmdb"

        # 3) Candidates: use local dataset (movie_recommender.movies)
        candidates = list(mr.movies)
        recommendations_raw = mr.get_content_recommendations(target, candidates, metric=metric, limit=top_n)

        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**{k: v for k, v in r.items() if k in {
                    'id','name','year','category','genre','description','box_office_millions','rating','poster_url'
                }}),
                similarity_score=r.get('similarity_score', 0.0),
                match_reason=r.get('match_reason', '')
            )
            for r in recommendations_raw
        ]

        return RecommendationsResponse(
            recommendations=recommendations,
            based_on={"query": title, "matched_source": source, "metric": metric},
            total_available=len(recommendations)
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in content-based recommend_by_title endpoint")
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/api/recommend/content/personalized", response_model=RecommendationsResponse)
@limiter.limit("30/minute")
async def personalized_content_recommendations(
    request: Request,
    metric: str = Query("weighted", description="Similarity metric: weighted, jaccard, cosine"),
    top_n: int = Query(10, ge=1, le=50),
    include_viewed: bool = Query(False, description="Include movies already in user's favorites")
):
    """
    Personalized content-based recommendations using the user's favorites and the local dataset.
    """
    user_ip = request.client.host if request.client else "unknown"
    try:
        import movie_recommender as mr

        # Load favorites from disk and map to full movie dicts (local favorites only)
        refresh_favorites_state()
        favorite_movies = get_favorite_movies()
        if not favorite_movies:
            # If no local favorites exist, fall back to TMDB-based personalized recommendations
            raise HTTPException(status_code=404, detail="No favorites found for user; add favorites first")

        candidates = list(mr.movies)

        recommendations_raw = mr.get_personalized_content_recommendations(favorite_movies, candidates, metric=metric, limit=top_n)

        # Optionally filter out viewed/favorited movies
        fav_keys = {(f['name'].lower(), f['year']) for f in favorite_movies}
        filtered = []
        for r in recommendations_raw:
            key = (r.get('name', '').lower(), r.get('year'))
            if not include_viewed and key in fav_keys:
                continue
            filtered.append(r)

        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**{k: v for k, v in r.items() if k in {
                    'id','name','year','category','genre','description','box_office_millions','rating','poster_url'
                }}),
                similarity_score=r.get('similarity_score', 0.0),
                match_reason=r.get('match_reason', '')
            )
            for r in filtered
        ]

        return RecommendationsResponse(
            recommendations=recommendations,
            based_on={"source": "local_favorites", "favorites_count": len(favorite_movies), "metric": metric},
            total_available=len(recommendations)
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in personalized_content_recommendations endpoint")
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
        if not TMDB_API_KEY:
            raise HTTPException(status_code=503, detail="TMDB integration is not configured")

        # Update preferences from search history
        prefs = get_user_preferences(user_ip)
        user_genres_set = get_user_genres_set(user_ip)
        if user_genres_set:
            prefs["liked_genres"].update(user_genres_set)
            save_user_preferences(user_ip, prefs)

        # Gather user's favorite movies (name, year) and map to TMDB IDs
        fav_keys = get_user_favorite_keys(user_ip)
        tmdb_recs = []
        seen_ids = set()

        import asyncio

        async def get_recs_for_favorite(name, year, client):
            # Search TMDB (caching is handled inside tmdb_search_movie)
            search_results = await tmdb_search_movie(name, year=year, limit=5, client=client)
            if not search_results:
                return []
            tmdb_id = search_results[0].get("id")
            if not tmdb_id:
                return []
            # Get recommendations (caching is handled inside tmdb_get_recommendations)
            return await tmdb_get_recommendations(tmdb_id, top_n=limit, client=client)

        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = [get_recs_for_favorite(name, year, client) for name, year in list(fav_keys)[:5]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception) or not res:
                    continue
                for r in res:
                    if r.get('id') in seen_ids:
                        continue
                    seen_ids.add(r.get('id'))
                    tmdb_recs.append(r)

        # If no favorites or no TMDB recs, fallback to TMDB popular/top rated
        if not tmdb_recs:
            # Use TMDB discover/popular endpoint
            async with httpx.AsyncClient(timeout=8.0) as client:
                try:
                    resp = await client.get("https://api.themoviedb.org/3/movie/top_rated", params={"api_key": TMDB_API_KEY, "page": 1})
                except Exception:
                    logger.exception("Failed to fetch TMDB top_rated")
                    raise HTTPException(status_code=502, detail="Failed to fetch TMDB data")
                if resp.status_code != 200:
                    raise HTTPException(status_code=502, detail="TMDB top_rated failed")
                try:
                    raw = resp.json().get("results", [])[:limit]
                except ValueError:
                    raise HTTPException(status_code=502, detail="Invalid TMDB response")
                tmdb_recs = []
                for r in raw:
                    tmdb_recs.append({
                        "id": r.get("id"),
                        "name": r.get("title"),
                        "year": int((r.get("release_date") or "0000")[:4]) if r.get("release_date") else 0,
                        "category": "TMDB",
                        "genre": ", ".join([TMDB_GENRES.get(g, "Movie") for g in r.get("genre_ids", [])]) if r.get("genre_ids") else "Movie",
                        "box_office_millions": None,
                        "rating": round(r.get("vote_average", 0), 1),
                        "description": r.get("overview"),
                        "poster_url": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None
                    })

        # Build recommendations response (deduplicate and limit)
        fav_names_years = {(name.lower(), year) for name, year in fav_keys}
        filtered_recs = []
        for m in tmdb_recs:
            if not include_viewed:
                m_name = m.get('name', '')
                m_year = m.get('year', 0)
                if (m_name.lower(), m_year) in fav_names_years:
                    continue
            filtered_recs.append(m)

        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**m),
                similarity_score=m.get('rating') or 0.0,
                match_reason="TMDB recommendation"
            )
            for m in filtered_recs[:limit]
        ]

        based_on = {
            "source": "tmdb",
            "favorites_count": len(get_user_favorite_keys(user_ip))
        }

        return RecommendationsResponse(
            recommendations=recommendations,
            based_on=based_on,
            total_available=len(recommendations)
        )
        
    except Exception as e:
        logger.exception("Error generating TMDB-based personalized recommendations")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/api/recommendations/hybrid", response_model=RecommendationsResponse)
@limiter.limit("20/minute")
async def get_hybrid_recommendations_endpoint(
    request: Request,
    tmdb_id: Optional[int] = Query(None, description="TMDB movie ID to base recommendations on"),
    genres: Optional[str] = Query(None, description="Comma-separated genre names"),
    year_min: Optional[int] = Query(None, description="Minimum release year"),
    year_max: Optional[int] = Query(None, description="Maximum release year"),
    rating_min: Optional[float] = Query(None, description="Minimum rating"),
    limit: int = Query(20, ge=1, le=50),
    tmdb_weight: float = Query(0.4, ge=0.0, le=1.0, description="Weight for TMDB popularity (0.0-1.0)"),
    content_weight: float = Query(0.6, ge=0.0, le=1.0, description="Weight for content score (0.0-1.0)")
):
    """
    Hybrid recommendations combining TMDB data with content-based scoring.
    
    This endpoint:
    1. Fetches candidates from TMDB (recommendations/similar/discover)
    2. Converts to content function format
    3. Scores with content-based functions
    4. Blends TMDB rank + content score
    5. Returns re-ranked list
    
    Examples:
    - /api/recommendations/hybrid?tmdb_id=550 (based on Fight Club)
    - /api/recommendations/hybrid?genres=Action,Sci-Fi&year_min=2010
    - /api/recommendations/hybrid?tmdb_weight=0.3&content_weight=0.7
    """
    user_ip = request.client.host if request.client else "unknown"
    
    if not TMDB_API_KEY:
        raise HTTPException(status_code=503, detail="TMDB integration is not configured")
    
    try:
        # Parse genres if provided
        genre_list = [g.strip() for g in genres.split(',')] if genres else []
        genre_ids = get_genre_ids_from_names(genre_list) if genre_list else []
        
        # Get user's favorite movies for personalization
        fav_keys = get_user_favorite_keys(user_ip)
        favorite_movies = []
        if fav_keys:
            from movie_recommender import movies as local_movies
            from movie_recommender import _movies_map
            movie_recommender._update_movies_map_if_needed()
            for name, year in fav_keys:
                key = (name.lower(), year)
                if key in _movies_map:
                    favorite_movies.append(_movies_map[key])
        
        # Get hybrid recommendations
        hybrid_recs = await get_hybrid_recommendations(
            tmdb_id=tmdb_id,
            favorite_movies=favorite_movies if favorite_movies else None,
            genre_ids=genre_ids if genre_ids else None,
            year_min=year_min,
            year_max=year_max,
            rating_min=rating_min,
            limit=limit,
            tmdb_weight=tmdb_weight,
            content_weight=content_weight
        )
        
        # Convert to RecommendationsResponse format
        recommendations = []
        for rec in hybrid_recs:
            recommendations.append({
                "movie": {
                    "id": rec.get("id"),
                    "name": rec.get("name"),
                    "year": rec.get("year"),
                    "category": rec.get("category"),
                    "genre": rec.get("genre"),
                    "description": rec.get("description"),
                    "box_office_millions": rec.get("box_office_millions"),
                    "rating": rec.get("rating"),
                    "poster_url": rec.get("poster_url")
                },
                "similarity_score": rec.get("hybrid_score", 0.0),
                "match_reason": f"Hybrid: TMDB score {rec.get('tmdb_score', 0.0):.2f} + Content score {rec.get('content_score', 0.0):.2f}"
            })
        
        based_on = {
            "tmdb_id": tmdb_id,
            "genres": genre_list,
            "year_range": {"min": year_min, "max": year_max},
            "rating_min": rating_min,
            "weights": {"tmdb": tmdb_weight, "content": content_weight},
            "favorites_count": len(favorite_movies)
        }
        
        return RecommendationsResponse(
            recommendations=recommendations,
            based_on=based_on,
            total_available=len(hybrid_recs)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in hybrid recommendations endpoint")
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
        if not TMDB_API_KEY:
            raise HTTPException(status_code=503, detail="TMDB integration is not configured")

        prefs = get_user_preferences(user_ip)
        liked_genres = prefs.get("liked_genres", set())
        viewed = prefs.get("viewed_movies", set())

        # Use TMDB discover endpoint to find high-rated movies outside user's liked genres
        params = {"api_key": TMDB_API_KEY, "sort_by": "vote_average.desc", "vote_count.gte": 200, "page": 1}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get("https://api.themoviedb.org/3/discover/movie", params=params)
            except Exception:
                logger.exception("Failed to fetch TMDB discover")
                raise HTTPException(status_code=502, detail="Failed to reach TMDB")
        if resp.status_code != 200:
            logger.warning("TMDB discover failed with status %s", resp.status_code)
            raise HTTPException(status_code=502, detail="TMDB discover failed")
        try:
            raw = resp.json().get("results", [])
        except ValueError:
            raise HTTPException(status_code=502, detail="Invalid TMDB response")

        candidates = []
        for r in raw:
            movie_key = (r.get('title'), int((r.get('release_date') or '0000')[:4]) if r.get('release_date') else 0)
            if movie_key in viewed:
                continue
            # encourage different genres
            genres = set(TMDB_GENRES.get(g, '').lower() for g in r.get('genre_ids', []) if TMDB_GENRES.get(g))
            overlap = len(genres & liked_genres)
            # compute discovery score
            score = 0
            reasons = []
            rating = r.get('vote_average', 0)
            if rating >= 8.0:
                score += 40
                reasons.append('Critically acclaimed')
            elif rating >= 7.5:
                score += 25
            if liked_genres:
                if overlap == 0:
                    score += 20
                    reasons.append('New genre for you')
                elif overlap == 1:
                    score += 10
            box_office = 0
            if rating >= 7.5 and box_office < 50:
                score += 10
                reasons.append('Hidden gem')
            if score >= 30:
                reason_str = reasons[0] if reasons else 'Discovery pick'
                candidates.append({
                    'movie': {
                        'id': r.get('id'),
                        'name': r.get('title'),
                        'year': int((r.get('release_date') or '0000')[:4]) if r.get('release_date') else 0,
                        'category': 'TMDB',
                        'genre': ", ".join([TMDB_GENRES.get(g, 'Movie') for g in r.get('genre_ids', [])]) if r.get('genre_ids') else 'Movie',
                        'box_office_millions': None,
                        'rating': round(r.get('vote_average', 0), 1),
                        'description': r.get('overview'),
                        'poster_url': f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}" if r.get('poster_path') else None
                    },

                    'score': min(score, 100),
                    'reason': reason_str
                })
        candidates.sort(key=lambda x: x['score'], reverse=True)
        recommendations = [
            RecommendationResponse(
                movie=MovieResponse(**item['movie']),
                similarity_score=item['score'],
                match_reason=item['reason']
            )
            for item in candidates[:limit]
        ]
        return RecommendationsResponse(
            recommendations=recommendations,
            based_on={'mode': 'tmdb_discovery'},
            total_available=len(recommendations)
        )
    except Exception as e:
        logger.exception("Error generating TMDB discovery recommendations")
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
