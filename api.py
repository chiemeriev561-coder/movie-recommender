"""
Movie Recommender API
FastAPI application exposing movie recommendation functionality as REST endpoints
"""

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
from pathlib import Path

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

# Initialize FastAPI app
app = FastAPI(
    title="Movie Recommender API",
    description="A REST API for movie recommendations with search, filtering, and favorites management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for request/response
class MovieResponse(BaseModel):
    name: str
    year: int
    category: str
    genre: str
    box_office_millions: float
    rating: float

    class Config:
        from_attributes = True

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

# Startup event to initialize favorites
@app.on_event("startup")
async def startup_event():
    """Initialize the API by loading favorites and expanding dataset if needed."""
    logger.info("Starting Movie Recommender API")
    
    # Load favorites from file
    load_favorites()
    logger.info(f"Loaded {len(get_favorite_entries())} favorites")
    
    # Expand dataset if needed (optional - can be disabled for production)
    # expand_dataset_if_needed(min_total=100, auto_save=False)
    logger.info(f"API ready with {len(movies)} movies in dataset")

# Root endpoint
@app.get("/")
async def root():
    """API root endpoint with basic information."""
    return {
        "message": "Movie Recommender API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "total_movies": len(movies),
        "favorites_count": len(get_favorite_entries())
    }

# Movie search endpoint
@app.get("/api/movies/search", response_model=List[MovieResponse])
async def search_movies(
    q: Optional[str] = Query(None, description="Search query (movie name, genre, etc.)"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_rating: Optional[float] = Query(None, ge=0, le=10, description="Minimum rating"),
    year: Optional[int] = Query(None, ge=1900, le=2030, description="Filter by year"),
    year_from: Optional[int] = Query(None, ge=1900, le=2030, description="Year from"),
    year_to: Optional[int] = Query(None, ge=1900, le=2030, description="Year to"),
    sort_by: Optional[str] = Query(None, regex="^(rating|box_office|year)$", description="Sort by field"),
    fuzzy: bool = Query(True, description="Enable fuzzy matching"),
    max_results: int = Query(50, ge=1, le=200, description="Maximum results to return")
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
async def get_top_movies(
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
async def get_genres():
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
async def get_categories():
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
async def get_favorites():
    """Get all favorite movies with full details."""
    try:
        fav_movies = get_favorite_movies()
        return [MovieResponse(**movie) for movie in fav_movies]
    except Exception as e:
        logger.exception("Error getting favorites")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving favorites"
        )

@app.post("/api/favorites", response_model=Dict[str, str])
async def add_to_favorites(favorite: FavoriteRequest):
    """Add a movie to favorites."""
    try:
        success = add_favorite(favorite.name, favorite.year)
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
async def remove_from_favorites(favorite: FavoriteRequest):
    """Remove a movie from favorites."""
    try:
        success = remove_favorite(favorite.name, favorite.year)
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
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "movies_count": len(movies),
        "favorites_count": len(get_favorite_entries()),
        "csv_integration": _HAS_CSV_STATS
    }

# CSV statistics endpoint
@app.get("/api/statistics")
async def get_statistics():
    """Get detailed statistics about the movie dataset."""
    try:
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
async def get_movie_details(name: str, year: int):
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
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
