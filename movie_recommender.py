# movie_recommender.py
# Core library for the movie recommendation system (importable, testable)

from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
import logging
import re
import json
import random
import argparse
import sys
from collections import defaultdict

# Optional fuzzy search support using RapidFuzz (fast, permissive fuzzy matching)
try:
    # import fuzz and try importing process (faster extraction); process may not exist in older installs
    from rapidfuzz import fuzz
    try:
        from rapidfuzz import process as rprocess
    except Exception:
        rprocess = None
    _HAS_RAPIDFUZZ = True
except Exception:
    fuzz = None
    rprocess = None
    _HAS_RAPIDFUZZ = False

DEFAULT_FUZZY_THRESHOLD = 70
FUZZY_MAX_CANDIDATES = 250

# Initialize logger at module level
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tracks the last save error message (if any) to help debugging failed saves
last_save_error: Optional[str] = None

# Global variables
movies: List[Dict[str, Any]] = []  # Main movie dataset
favorites: List[Dict[str, Any]] = []  # List of favorite movies
_favorites_set: Set[Tuple[str, int]] = set()  # For O(1) lookups

# Simple favorites persistence (stores movie references by name+year)
FAVORITES_FILE = 'favorites.json'

def get_last_save_error() -> Optional[str]:
    """Return the last error message recorded when saving movies (or None)."""
    return last_save_error

def load_favorites(path: str = FAVORITES_FILE) -> List[Dict[str, Any]]:
    """
    Load favorites from JSON file.
    
    Args:
        path: Path to the favorites JSON file.
        
    Returns:
        List of favorite movie entries, each with 'name' and 'year'.
    """
    global favorites, _favorites_set
    p = Path(path)
    
    if not p.exists():
        favorites = []
        _favorites_set = set()
        return favorites
    
    try:
        with p.open('r', encoding='utf-8') as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            logger.warning("Invalid favorites format: expected list, got %s", type(data).__name__)
            favorites = []
            _favorites_set = set()
            return favorites
            
        # Validate and clean entries
        valid = []
        for entry in data:
            if (isinstance(entry, dict) and 
                'name' in entry and 
                'year' in entry and 
                isinstance(entry['name'], str) and 
                isinstance(entry['year'], int)):
                valid.append({'name': entry['name'], 'year': entry['year']})
            else:
                logger.warning("Skipping invalid favorite entry: %r", entry)
                
        favorites = valid
        _favorites_set = {(f['name'].lower(), f['year']) for f in favorites}
        return favorites
        
    except Exception as e:
        logger.exception("Failed to load favorites from %s: %s", path, str(e))
        favorites = []
        _favorites_set = set()
        return favorites

def save_favorites(path: str = FAVORITES_FILE) -> bool:
    """
    Save favorites to JSON file.
    
    Args:
        path: Path to save the favorites file.
        
    Returns:
        bool: True if save was successful, False otherwise.
    """
    global last_save_error
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('w', encoding='utf-8') as f:
            json.dump(favorites, f, indent=2)
        last_save_error = None
        return True
    except Exception as e:
        error_msg = f"Failed to save favorites to {path}: {str(e)}"
        logger.exception(error_msg)
        last_save_error = error_msg
        return False

def add_favorite(name: str, year: int, path: str = FAVORITES_FILE) -> bool:
    """
    Add a movie to favorites if it exists in the dataset.
    
    Args:
        name: Name of the movie to add.
        year: Release year of the movie.
        path: Path to save favorites file.
        
    Returns:
        bool: True if added successfully, False otherwise.
    """
    global favorites, _favorites_set
    
    if not isinstance(name, str) or not isinstance(year, int):
        logger.warning("Invalid name or year type")
        return False
        
    # Normalize name for comparison
    name_lower = name.lower()
    
    # Check if already favorited
    if (name_lower, year) in _favorites_set:
        logger.info("Movie already in favorites: %s (%d)", name, year)
        return False
        
    # Check if movie exists in dataset
    movie_exists = any(
        m.get('name', '').lower() == name_lower 
        and m.get('year') == year 
        for m in movies
    )
    
    if not movie_exists:
        logger.warning("Movie not found in dataset: %s (%d)", name, year)
        return False
        
    # Add to favorites
    entry = {'name': name, 'year': year}
    favorites.append(entry)
    _favorites_set.add((name_lower, year))
    
    # Save to disk
    if not save_favorites(path):
        # Rollback on save failure
        favorites.remove(entry)
        _favorites_set.discard((name_lower, year))
        return False
        
    return True

def remove_favorite(name: str, year: int, path: str = FAVORITES_FILE) -> bool:
    """
    Remove a movie from favorites.
    
    Args:
        name: Name of the movie to remove.
        year: Release year of the movie.
        path: Path to save favorites file.
        
    Returns:
        bool: True if removed successfully, False otherwise.
    """
    global favorites, _favorites_set
    
    name_lower = name.lower()
    entry = {'name': name, 'year': year}
    
    if (name_lower, year) not in _favorites_set:
        return False
        
    # Remove from both data structures
    favorites = [f for f in favorites 
                if not (f['name'].lower() == name_lower and f['year'] == year)]
    _favorites_set.discard((name_lower, year))
    
    # Save changes
    return save_favorites(path)

def get_favorite_entries() -> List[Dict[str, Any]]:
    """
    Get a list of all favorite movie entries.
    
    Returns:
        List of favorite movie entries, each with 'name' and 'year'.
    """
    return favorites.copy()  # Return a copy to prevent external modification

def get_favorite_movies() -> List[Dict[str, Any]]:
    """
    Get full movie details for all favorites.
    
    Returns:
        List of full movie dictionaries for all favorites.
    """
    fav_movies = []
    for fav in favorites:
        for movie in movies:
            if (movie.get('name') == fav['name'] and 
                movie.get('year') == fav['year']):
                fav_movies.append(movie)
                break
    return fav_movies
movies = [
    {"name": "Superman", "year": 1978, "category": "Blockbuster", "genre": "Action", "box_office_millions": 134.2, "rating": 7.9},
    {"name": "The Avengers", "year": 2012, "category": "Blockbuster", "genre": "Action", "box_office_millions": 1518.8, "rating": 8.4},
    {"name": "Man From Toronto", "year": 2022, "category": "Streaming", "genre": "Action/Comedy", "box_office_millions": 12.3, "rating": 6.1},
    {"name": "Black Widow", "year": 2021, "category": "Blockbuster", "genre": "Action", "box_office_millions": 379.8, "rating": 6.8},
    {"name": "Shazam!", "year": 2019, "category": "Blockbuster", "genre": "Family/Fantasy", "box_office_millions": 364.6, "rating": 7.1},
    {"name": "John Wick", "year": 2014, "category": "Action Franchise", "genre": "Action/Thriller", "box_office_millions": 86.0, "rating": 7.4},
    {"name": "Spider-Man: No Way Home", "year": 2021, "category": "Blockbuster", "genre": "Action/Adventure", "box_office_millions": 1932.0, "rating": 8.1},
    {"name": "Inception", "year": 2010, "category": "Prestige", "genre": "Sci-Fi", "box_office_millions": 829.9, "rating": 8.8},
    {"name": "The Godfather", "year": 1972, "category": "Classic", "genre": "Crime/Drama", "box_office_millions": 246.1, "rating": 9.2},
    {"name": "Parasite", "year": 2019, "category": "Indie", "genre": "Thriller/Drama", "box_office_millions": 258.8, "rating": 8.6},
    {"name": "La La Land", "year": 2016, "category": "Musical", "genre": "Musical/Romance", "box_office_millions": 446.1, "rating": 8.0},
    {"name": "Toy Story", "year": 1995, "category": "Animation", "genre": "Family/Animation", "box_office_millions": 373.6, "rating": 8.3},
    {"name": "The Dark Knight", "year": 2008, "category": "Prestige", "genre": "Action/Crime", "box_office_millions": 1004.9, "rating": 9.0},
    {"name": "Forrest Gump", "year": 1994, "category": "Classic", "genre": "Drama/Romance", "box_office_millions": 678.2, "rating": 8.8},
    {"name": "The Shawshank Redemption", "year": 1994, "category": "Classic", "genre": "Drama", "box_office_millions": 58.3, "rating": 9.3},
    {"name": "Interstellar", "year": 2014, "category": "Prestige", "genre": "Sci-Fi/Drama", "box_office_millions": 677.5, "rating": 8.6},
    {"name": "Get Out", "year": 2017, "category": "Indie", "genre": "Horror/Thriller", "box_office_millions": 255.4, "rating": 7.7},
    {"name": "The Matrix", "year": 1999, "category": "Sci-Fi", "genre": "Action/Sci-Fi", "box_office_millions": 463.5, "rating": 8.7},
    {"name": "Titanic", "year": 1997, "category": "Romance/Blockbuster", "genre": "Romance/Drama", "box_office_millions": 2187.5, "rating": 7.8},
    {"name": "Spirited Away", "year": 2001, "category": "Animation", "genre": "Fantasy/Animation", "box_office_millions": 355.5, "rating": 8.6},
    {"name": "The Social Network", "year": 2010, "category": "Drama", "genre": "Drama/Biography", "box_office_millions": 224.9, "rating": 7.7},
    {"name": "Mad Max: Fury Road", "year": 2015, "category": "Action", "genre": "Action/Adventure", "box_office_millions": 378.9, "rating": 8.1},
    {"name": "City of God", "year": 2002, "category": "Indie", "genre": "Crime/Drama", "box_office_millions": 30.6, "rating": 8.6},
    {"name": "Coco", "year": 2017, "category": "Animation", "genre": "Family/Animation", "box_office_millions": 807.1, "rating": 8.4}
]


# Helper: format movie output including year
def format_movie(m: dict) -> str:
    return (f"{m['name']} ({m['year']}) | Genre: {m['genre']} | Category: {m['category']} | "
            f"Box Office: ${m['box_office_millions']:,}M | Rating: {m['rating']}/10")


# ---------- Validation, sanitization and persistence helpers ----------
def sanitize_query(q: str, max_length: int = 100) -> str:
    """Clean user input to a safe, normalized string for searching."""
    if not isinstance(q, str):
        raise TypeError("query must be a string")
    # remove non-printable/control characters and trim
    q = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', q).strip()
    if len(q) > max_length:
        q = q[:max_length]
    return q


def validate_movie_schema(movie: dict) -> bool:
    """Quick schema validation for movie dicts."""
    required = {'name', 'year', 'category', 'genre', 'box_office_millions', 'rating'}
    if not isinstance(movie, dict):
        return False
    if not required.issubset(movie.keys()):
        return False
    if not isinstance(movie['name'], str) or not movie['name']:
        return False
    if not isinstance(movie['year'], int):
        return False
    if not isinstance(movie['box_office_millions'], (int, float)):
        return False
    if not isinstance(movie['rating'], (int, float)):
        return False
    return True


def load_movies(path: str) -> List[dict]:
    """Load movies from a JSON file. Returns list of movie dicts."""
    p = Path(path)
    if not p.exists():
        logger.info("Movie file %s not found. Returning empty list.", path)
        return []
    try:
        with p.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            # basic validation
            valid = [m for m in data if validate_movie_schema(m)]
            for m in valid:
                ensure_search_fields(m)
            if len(valid) < len(data):
                logger.warning("Some entries in %s failed validation and were skipped.", path)
            return valid
        else:
            logger.warning("Unexpected format in %s — expected a list.", path)
            return []
    except Exception as e:
        logger.exception("Failed to load movies from %s: %s", path, e)
        return []


def save_movies(path: str, movie_list: List[dict]) -> bool:
    """Save movies to a JSON file. Returns True on success."""
    global last_save_error
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('w', encoding='utf-8') as f:
            # Use JSON-serializable representation to avoid issues with cached types (sets etc.)
            json.dump(serialize_movies(movie_list), f, indent=2)
        logger.info("Saved %d movies to %s", len(movie_list), path)
        # clear last error on success
        last_save_error = None
        return True
    except Exception as e:
        # record error for external inspection
        last_save_error = str(e)
        logger.exception("Failed to save movies to %s: %s", path, e)
        return False


def _serialize_movie(m: dict) -> dict:
    """Return a JSON-serializable shallow copy of a movie record (exclude internal cached fields)."""
    out = {}
    for k, v in m.items():
        if k.startswith('_'):
            continue
        # convert non-serializable types
        if isinstance(v, set):
            out[k] = list(v)
        else:
            out[k] = v
    return out


def serialize_movies(movie_list: List[dict]) -> List[dict]:
    return [_serialize_movie(m) for m in movie_list]


def get_available_genres() -> List[dict]:
    """Return list of {'genre': name, 'count': n} for genre tokens (split on '/') sorted by count desc then name."""
    from collections import Counter
    counter = Counter()
    for m in movies:
        g = m.get('genre')
        if not g:
            continue
        # split by slash and whitespace to get tokens like 'Animation' from 'Family/Animation'
        tokens = [t.strip() for t in re.split(r'[\s/]+', g) if t.strip()]
        for t in tokens:
            counter[t] += 1
    return [{'genre': name, 'count': counter[name]} for name in sorted(counter.keys(), key=lambda x: (-counter[x], x))]


def get_available_categories() -> List[dict]:
    """Return list of {'category': name, 'count': n} sorted by count desc then name."""
    from collections import Counter
    counter = Counter()
    for m in movies:
        c = m.get('category')
        if c:
            counter[c] += 1
    return [{'category': name, 'count': counter[name]} for name in sorted(counter.keys(), key=lambda x: (-counter[x], x))]


def add_movie(movie: dict) -> bool:
    """Add a single movie to in-memory list after validation. Returns True if added."""
    if not validate_movie_schema(movie):
        logger.warning("Invalid movie schema; not added.")
        return False
    # avoid duplicates by exact name+year
    existing = {(m['name'].lower(), m['year']) for m in movies}
    key = (movie['name'].lower(), movie['year'])
    if key in existing:
        logger.info("Movie %s (%s) already exists; skipping.", movie['name'], movie['year'])
        return False
    movies.append(movie)
    ensure_search_fields(movie)
    return True


# ...rest of file unchanged...


# ---------- Dataset expansion helpers ----------
GENRES = [
    "Action", "Comedy", "Drama", "Sci-Fi", "Horror", "Thriller", "Romance",
    "Animation", "Fantasy", "Documentary", "Biography", "Family", "Adventure"
]
CATEGORIES = ["Blockbuster", "Streaming", "Indie", "Prestige", "Franchise", "Animation", "Other"]

ADJECTIVES = ["Silent","Crimson","Golden","Hidden","Final","Broken","New","Last","First","Endless","Lonely","Electric","Shadow","Secret","Forgotten","Midnight","Distant","Red","Blue","Iron","Silver","Urban","Desert","Frozen","Burning"]
NOUNS = ["Dawn","Echo","Protocol","Empire","Promise","Memory","Reckoning","Code","Journey","Legacy","Labyrinth","River","Sky","Threshold","City","Island","Valley","Storm","Run","Game","Hour","Moment","Edge","Light"]


def _unique_title(existing):
    # generate a title combining adjective and noun; ensure uniqueness by adding suffix if needed
    for _ in range(1000):
        title = f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)}"
        if title not in existing:
            return title
    # fallback with random id
    return f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)} {random.randint(1000,9999)}"


def generate_synthetic_movies(target_count: int = 600, start_year: int = 2019, end_year: int = 2025) -> List[dict]:
    """Generate synthetic but realistic-looking movies to grow the dataset.
    All generated movies will have years between start_year and end_year inclusive.
    """
    existing_titles = {m['name'] for m in movies}
    generated = []
    random.seed(42)  # reproducible
    while len(movies) + len(generated) < target_count:
        name = _unique_title(existing_titles | {m['name'] for m in generated})
        year = random.randint(start_year, end_year)
        genre = random.choice(GENRES)
        category = random.choice(CATEGORIES)
        # box office depends on category
        if category == 'Blockbuster':
            box = round(random.uniform(50.0, 2000.0), 1)
        elif category == 'Franchise':
            box = round(random.uniform(20.0, 1000.0), 1)
        elif category == 'Streaming':
            box = round(random.uniform(0.0, 50.0), 1)
        elif category == 'Animation':
            box = round(random.uniform(10.0, 900.0), 1)
        else:
            box = round(random.uniform(0.1, 200.0), 1)
        # rating skewed: blockbusters and prestige tend to have higher ratings in this synthetic set
        if category in ('Prestige',):
            rating = round(random.uniform(7.0, 9.5), 1)
        elif category in ('Blockbuster','Franchise'):
            rating = round(random.uniform(6.0, 9.0), 1)
        else:
            rating = round(random.uniform(5.0, 8.5), 1)
        entry = {
            'name': name,
            'year': year,
            'category': category,
            'genre': genre,
            'box_office_millions': box,
            'rating': rating
        }
        ensure_search_fields(entry)
        generated.append(entry)
    return generated


def parse_filters(filter_text: str) -> dict:
    """Parse simple comma-separated filters like 'genre=Action,min-rating=7,year=2021'."""
    if not filter_text:
        return {}
    out = {}
    parts = [p.strip() for p in filter_text.split(',') if p.strip()]
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1)
        elif ':' in p:
            k, v = p.split(':', 1)
        else:
            continue
        k = k.strip().lower().replace('-', '_')
        v = v.strip()
        if k in ('min_rating', 'min-rating'):
            try:
                out['min_rating'] = float(v)
            except Exception:
                continue
        elif k in ('year',):
            try:
                out['year'] = int(v)
            except Exception:
                continue
        elif k in ('year_from','year-from'):
            try:
                out['year_from'] = int(v)
            except Exception:
                continue
        elif k in ('year_to','year-to'):
            try:
                out['year_to'] = int(v)
            except Exception:
                continue
        elif k in ('genre', 'category', 'sort_by', 'sort-by'):
            out[k.replace('-', '_')] = v
    return out


def find_matches(query_text: str = '', max_results: int = 50, enable_fuzzy: bool = True, fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
                 genre: Optional[str] = None, category: Optional[str] = None, min_rating: Optional[float] = None,
                 year: Optional[int] = None, year_from: Optional[int] = None, year_to: Optional[int] = None,
                 sort_by: Optional[str] = None) -> List[dict]:
    """Find matching movies for a query.

    Behavior improvements:
    - Preserves exact/fuzzy match priorities when ranking results.
    - Honors ``sort_by`` ("rating", "box_office", "year") if provided.

    Returns a list of movie dicts.
    """
    try:
        q = sanitize_query(query_text) if query_text is not None else ''
    except Exception:
        return []

    q_lower = q.lower() if q else ''

    # start with snapshot to avoid mutation issues
    movie_list = list(movies)

    # Apply filters first to limit search space
    if genre:
        genre_lower = genre.lower()
        movie_list = [m for m in movie_list if genre_lower in m.get('genre','').lower() or genre_lower in m.get('category','').lower()]
    if category:
        cat_lower = category.lower()
        movie_list = [m for m in movie_list if cat_lower in m.get('category','').lower() or cat_lower in m.get('genre','').lower()]
    if min_rating is not None:
        movie_list = [m for m in movie_list if isinstance(m.get('rating'), (int,float)) and m.get('rating') >= min_rating]
    if year is not None:
        movie_list = [m for m in movie_list if m.get('year') == year]
    if year_from is not None:
        movie_list = [m for m in movie_list if m.get('year') >= year_from]
    if year_to is not None:
        movie_list = [m for m in movie_list if m.get('year') <= year_to]

    # We'll collect (movie, priority) pairs where higher priority indicates a better match.
    matches_with_priority = []

    # If no query provided but filters exist, return filtered set (high priority)
    if not q_lower and (genre or category or min_rating is not None or year is not None or year_from is not None or year_to is not None):
        for m in movie_list:
            matches_with_priority.append((m, 1000))
    else:
        # Numeric query: match year exactly
        if q_lower.isdigit():
            y = int(q_lower)
            for m in movie_list:
                if m.get('year') == y:
                    matches_with_priority.append((m, 1000))
        else:
            tokens = [t for t in re.split(r'\s+|/|,', q_lower) if t]
            for m in movie_list:
                name = m.get('name','').lower()
                genre_v = m.get('genre','').lower()
                category_v = m.get('category','').lower()
                # exact substring match -> highest priority
                if any(t in name or t in genre_v or t in category_v for t in tokens):
                    matches_with_priority.append((m, 1000))
                    continue
                # startswith on name tokens -> high priority
                if any(name.startswith(t) for t in tokens):
                    matches_with_priority.append((m, 900))
                    continue
                # token-level match -> medium priority
                if any(t in name.split() for t in tokens):
                    matches_with_priority.append((m, 800))
                    continue

    # Fuzzy matching for remaining candidates
    if enable_fuzzy and _HAS_RAPIDFUZZ and q_lower:
        existing_keys = {(m.get('name'), m.get('year')) for m, _ in matches_with_priority}
        candidates = [m for m in movie_list if (m.get('name'), m.get('year')) not in existing_keys]
        scored = []
        # Cap the fuzzy candidate set by rating/box-office to reduce work
        candidates_sorted = sorted(candidates, key=lambda x: (x.get('rating',0), x.get('box_office_millions',0)), reverse=True)
        candidate_subset = candidates_sorted[:FUZZY_MAX_CANDIDATES]
        if rprocess is not None:
            choices = [m.get('_search_text', f"{m.get('name','')} {m.get('genre','')} {m.get('category','')}").lower() for m in candidate_subset]
            try:
                results = rprocess.extract(q_lower, choices, scorer=fuzz.partial_ratio, limit=len(choices))
            except Exception:
                logger.exception("RapidFuzz process.extract failed; skipping fuzzy matching")
                results = []
            for choice, score, idx in results:
                if score >= fuzzy_threshold:
                    scored.append((score, candidate_subset[idx]))
        else:
            for m in candidate_subset:
                search_text = m.get('_search_text', f"{m.get('name','')} {m.get('genre','')} {m.get('category','')}").lower()
                try:
                    score = fuzz.partial_ratio(q_lower, search_text)
                except Exception:
                    score = 0
                if score >= fuzzy_threshold:
                    scored.append((score, m))
        # sort by fuzzy score desc then rating/box office and append with priority equal to the score
        scored.sort(key=lambda x: (x[0], x[1].get('rating',0), x[1].get('box_office_millions',0)), reverse=True)
        for score, m in scored:
            matches_with_priority.append((m, int(score)))

    # Deduplicate: keep the highest-priority entry for each (name, year)
    best = {}
    for m, p in matches_with_priority:
        key = (m.get('name'), m.get('year'))
        if key not in best or p > best[key][0]:
            best[key] = (p, m)

    ordered = [v[1] for v in best.values()]

    # Sorting: either respect explicit sort_by requested by caller, or use (priority, rating, box_office)
    def _priority_of(movie):
        return best.get((movie.get('name'), movie.get('year')), (0, movie))[0]

    if sort_by:
        sb = sort_by.lower()
        if sb == 'rating':
            ordered.sort(key=lambda x: (x.get('rating',0), x.get('box_office_millions',0), _priority_of(x)), reverse=True)
        elif sb in ('box_office', 'box_office_millions'):
            ordered.sort(key=lambda x: (x.get('box_office_millions',0), x.get('rating',0), _priority_of(x)), reverse=True)
        elif sb == 'year':
            ordered.sort(key=lambda x: (x.get('year',0), x.get('rating',0), _priority_of(x)), reverse=True)
        else:
            # Unknown sort_by: fallback to priority-based sorting
            ordered.sort(key=lambda x: (_priority_of(x), x.get('rating',0), x.get('box_office_millions',0)), reverse=True)
    else:
        ordered.sort(key=lambda x: (_priority_of(x), x.get('rating',0), x.get('box_office_millions',0)), reverse=True)

    if max_results:
        return ordered[:max_results]
    return ordered

def show_top(n=5):
    top = sorted(movies, key=lambda x: x.get('rating',0), reverse=True)[:n]
    print(f"\nTop {n} rated movies:")
    for m in top:
        print("-", format_movie(m))


def expand_dataset_if_needed(min_total: int = 600, auto_save: bool = False, save_path: Optional[str] = None) -> bool:
    """Expand the in-memory dataset to at least min_total movies. Optionally save to disk.
    Returns True if expansion occurred (or already satisfied), False on failure.
    """
    if len(movies) >= min_total:
        logger.info("Dataset already has %d movies — no expansion needed.", len(movies))
        return True
    needed = min_total - len(movies)
    logger.info("Dataset has %d movies; generating %d synthetic movies (years 2019–2025)", len(movies), needed)
    generated = generate_synthetic_movies(target_count=min_total, start_year=2019, end_year=2025)
    movies.extend(generated)
    logger.info("Dataset expanded to %d movies.", len(movies))
    if auto_save:
        out = save_path or 'movies_expanded_2019_2025.json'
        success = save_movies(out, movies)
        if not success:
            logger.warning("Failed to auto-save expanded dataset to %s", out)
            return False
    return True


def ensure_search_fields(movie: dict) -> None:
    """Cache lowercased search text and token set to speed searches."""
    name = str(movie.get('name', '')).lower()
    genre = str(movie.get('genre', '')).lower()
    category = str(movie.get('category', '')).lower()
    search_text = f"{name} {genre} {category}".strip()
    movie['_search_text'] = search_text
    movie['_tokens'] = set(t for t in re.split(r'\s+|/|,', search_text) if t)


# Initialize cached search fields for built-in dataset (helps fuzzy search and avoids repeated fallbacks)
for m in movies:
    try:
        ensure_search_fields(m)
    except Exception:
        logger.exception("Failed to initialize search fields for movie: %s", m.get('name'))


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Movie Recommender — optional dataset expansion and save flags")
    p.add_argument('--expand', action='store_true', help='Generate synthetic movies to reach a minimum total')
    p.add_argument('--save', action='store_true', help="When used with --expand, save expanded dataset to disk")
    p.add_argument('--min-total', type=int, default=600, help='Minimum total movies after expansion (default: 600)')
    p.add_argument('--start-year', type=int, default=2019, help='Start year for synthetic movies (default: 2019)')
    p.add_argument('--end-year', type=int, default=2025, help='End year for synthetic movies (default: 2025)')
    p.add_argument('--output', type=str, default='movies_expanded_2019_2025.json', help='Output filename to save expanded dataset')

    # CLI query mode: non-interactive single query
    p.add_argument('--query', type=str, default=None, help='Run a single search query and exit')
    p.add_argument('--format', choices=['text', 'json'], default='text', help='Output format when using --query')
    p.add_argument('--load', type=str, default=None, help='JSON file to load movies from before running')
    p.add_argument('--fuzzy', action='store_true', help='Enable fuzzy matching (if optional dependency available)')
    p.add_argument('--fuzzy-threshold', type=int, default=DEFAULT_FUZZY_THRESHOLD, help='Fuzzy matching threshold (0-100)')

    # Filtering options
    p.add_argument('--genre', type=str, default=None, help='Filter by genre (substring match)')
    p.add_argument('--category', type=str, default=None, help='Filter by category (substring match)')
    p.add_argument('--min-rating', type=float, default=None, help='Filter by minimum rating (e.g., 7.5)')
    p.add_argument('--year', type=int, default=None, help='Filter by exact year (e.g., 2021)')
    p.add_argument('--year-from', type=int, default=None, help='Filter by year-from (inclusive)')
    p.add_argument('--year-to', type=int, default=None, help='Filter by year-to (inclusive)')
    p.add_argument('--sort-by', choices=['rating','box_office','year'], default=None, help='Sort results by this field')
    p.add_argument('--max-results', type=int, default=50, help='Maximum number of results to return')

    p.add_argument('--list-genres', action='store_true', help='List available genres and exit')
    p.add_argument('--list-categories', action='store_true', help='List available categories and exit')
    p.add_argument('--menu', action='store_true', help='Open the interactive user menu for searching and favorites')

    return p.parse_args(argv)


def main_loop():
    print("Movie Recommender — interactive mode")
    print("Type 'q' at any prompt to quit. Leave query blank to see top-rated movies.")

    while True:
        try:
            # allow the user to enter optional filters before a query
            filter_input = input('\nEnter filters (e.g. genre=Action,min-rating=7,year=2021) or leave blank: ').strip()
        except (KeyboardInterrupt, EOFError):
            print('Goodbye!')
            break
        if filter_input.lower() in ('list','l'):
            print('\nAvailable genres:')
            for g in get_available_genres():
                print(f" - {g['genre']} ({g['count']})")
            print('\nAvailable categories:')
            for c in get_available_categories():
                print(f" - {c['category']} ({c['count']})")
            continue
        filters = parse_filters(filter_input)

        try:
            query = input('\nEnter a movie name, genre, category, or year to base recommendations on (or leave blank to use filters): ').strip()
        except (KeyboardInterrupt, EOFError):
            print('Goodbye!')
            break

        if query.lower() == 'q':
            print('Goodbye!')
            break

        try:
            query = sanitize_query(query)
        except Exception:
            print('Invalid input; please try again.')
            continue

        if query or filters:
            matches = find_matches(query or '', max_results=20, genre=filters.get('genre'), category=filters.get('category'),
                                   min_rating=filters.get('min_rating'), year=filters.get('year'),
                                   year_from=filters.get('year_from'), year_to=filters.get('year_to'))
            if matches:
                print(f"\nFound {len(matches)} match(es). Top recommendations:")
                for m in matches[:10]:
                    print("-", format_movie(m))
            else:
                print("No matching results found. Here are the current top-rated movies:")
                show_top(5)
        else:
            show_top(5)

        # Ask whether to stay or quit
        while True:
            choice = input("\nEnter 'S' to search again or 'Q' to quit: ").strip().lower()
            if choice == 'q':
                print('Goodbye!')
                return
            elif choice == 's' or choice == '':
                break
            else:
                print("Invalid option. Enter 'S' to stay or 'Q' to quit.")


def user_menu(favorites_path: str = FAVORITES_FILE):
    """Interactive user menu allowing search, favorites management, and quick lists."""
    load_favorites(favorites_path)
    print("\nMovie Recommender — User Menu")
    while True:
        print("\nMenu:")
        print(" 1) Search for a movie")
        print(" 2) Show my favorites")
        print(" 3) Add a movie to favorites")
        print(" 4) Remove a movie from favorites")
        print(" 5) List genres")
        print(" 6) List categories")
        print(" 7) Show top rated movies")
        print(" Q) Quit")
        choice = input("Choose an option: ").strip().lower()
        if choice in ('q', 'quit'):
            print('Goodbye!')
            break
        if choice == '1':
            q = input('Enter movie name or part to search for: ').strip()
            if not q:
                continue
            q = sanitize_query(q)
            matches = find_matches(q, max_results=10, enable_fuzzy=True)
            if not matches:
                print('No matches found.')
                continue
            print('\nMatches:')
            for i, m in enumerate(matches, start=1):
                print(f" {i}) {format_movie(m)}")
            sel = input("Enter number to view details, 'a' to add to favorites, or blank to return: ").strip()
            if sel.lower() == 'a':
                num = input('Enter the number of the movie to add to favorites: ').strip()
                try:
                    idx = int(num) - 1
                    selm = matches[idx]
                    if add_favorite(selm['name'], selm['year'], path=favorites_path):
                        print('Added to favorites.')
                    else:
                        print('Already in favorites or not found.')
                except Exception:
                    print('Invalid selection.')
                continue
            if sel.isdigit():
                idx = int(sel) - 1
                if 0 <= idx < len(matches):
                    m = matches[idx]
                    print('\n' + format_movie(m))
                    sub = input('Add to favorites? [y/N]: ').strip().lower()
                    if sub in ('y', 'yes'):
                        if add_favorite(m['name'], m['year'], path=favorites_path):
                            print('Added to favorites.')
                        else:
                            print('Already in favorites or not found.')
                continue
        elif choice == '2':
            favs = get_favorite_movies()
            if not favs:
                print('No favorites yet.')
            else:
                print('\nYour favorites:')
                for i, m in enumerate(favs, start=1):
                    print(f" {i}) {format_movie(m)}")
            continue
        elif choice == '3':
            # alias to search + add
            q = input('Enter movie name or part to search for: ').strip()
            if not q:
                continue
            q = sanitize_query(q)
            matches = find_matches(q, max_results=10, enable_fuzzy=True)
            if not matches:
                print('No matches found.')
                continue
            print('\nMatches:')
            for i, m in enumerate(matches, start=1):
                print(f" {i}) {format_movie(m)}")
            num = input('Enter the number to add to favorites: ').strip()
            try:
                idx = int(num) - 1
                selm = matches[idx]
                if add_favorite(selm['name'], selm['year'], path=favorites_path):
                    print('Added to favorites.')
                else:
                    print('Already in favorites or not found.')
            except Exception:
                print('Invalid selection.')
            continue
        elif choice == '4':
            favs = get_favorite_entries()
            if not favs:
                print('No favorites to remove.')
                continue
            print('\nFavorites:')
            for i, e in enumerate(favs, start=1):
                print(f" {i}) {e['name']} ({e['year']})")
            num = input('Enter the number to remove: ').strip()
            try:
                idx = int(num) - 1
                e = favs[idx]
                if remove_favorite(e['name'], e['year'], path=favorites_path):
                    print('Removed from favorites.')
                else:
                    print('Failed to remove.')
            except Exception:
                print('Invalid selection.')
            continue
        elif choice == '5':
            print('\nAvailable genres:')
            for g in get_available_genres():
                print(f" - {g['genre']} ({g['count']})")
            continue
        elif choice == '6':
            print('\nAvailable categories:')
            for c in get_available_categories():
                print(f" - {c['category']} ({c['count']})")
            continue
        elif choice == '7':
            show_top(10)
            continue
        else:
            print('Unknown option; please choose from the menu.')
            continue


def main(argv=None):
    args = _parse_args(argv)

    if args.load:
        loaded = load_movies(args.load)
        for m in loaded:
            add_movie(m)

    # Handle simple listing flags early
    if args.list_genres:
        import json as _json
        print(_json.dumps(get_available_genres(), indent=2))
        return
    if args.list_categories:
        import json as _json
        print(_json.dumps(get_available_categories(), indent=2))
        return

    # If --menu requested, open the user menu
    if args.menu:
        user_menu()
        return

    # If no query/filters/expand/load/list flags provided and running interactively, open the user menu automatically
    if (not any([
        args.query, args.genre, args.category,
        args.min_rating is not None, args.year is not None,
        args.year_from is not None, args.year_to is not None,
        args.expand, args.load, args.list_genres, args.list_categories, args.save
    ]) and sys.stdin.isatty()):
        logger.info("No arguments provided and terminal is interactive: opening user menu.")
        user_menu()
        return

    if args.expand:
        ok = expand_dataset_if_needed(min_total=args.min_total, auto_save=args.save, save_path=args.output if args.save else None)
        if not ok:
            err = get_last_save_error() or 'unknown error'
            print(f"Failed to expand and save dataset: {err}")
            sys.exit(2)

    # Non-interactive query mode (triggered by query OR any filter)
    if args.query or any([args.genre, args.category, args.min_rating, args.year, args.year_from, args.year_to]):
        if args.fuzzy and not _HAS_RAPIDFUZZ:
            # Visible runtime warning instructing how to enable fuzzy matching
            logger.warning("Fuzzy search requested with --fuzzy, but RapidFuzz is not installed. Install with 'pip install rapidfuzz' to enable fuzzy matching.")
            print("Warning: --fuzzy requested but RapidFuzz is not installed. Install with 'pip install rapidfuzz' to enable fuzzy search.", file=sys.stderr)

        matches = find_matches(args.query or '', max_results=args.max_results, enable_fuzzy=bool(args.fuzzy), fuzzy_threshold=args.fuzzy_threshold,
                               genre=args.genre, category=args.category, min_rating=args.min_rating, year=args.year,
                               year_from=args.year_from, year_to=args.year_to, sort_by=args.sort_by)
        if args.format == 'json':
            print(json.dumps(serialize_movies(matches), indent=2))
        else:
            if matches:
                print(f"Found {len(matches)} match(es). Top recommendations:")
                for m in matches[:args.max_results]:
                    print("-", format_movie(m))
            else:
                print("No matching results found. Here are the current top-rated movies:")
                show_top(5)
        return

    # Interactive fallback
    try:
        choice = input("Dataset expansion: generate synthetic movies up to 600 items for years 2019-2025? [Y/n]: ").strip().lower()
    except Exception:
        choice = 'y'
    if choice in ('', 'y', 'yes'):
        expand_dataset_if_needed(min_total=600, auto_save=False)
        # offer to save
        try:
            save_choice = input(f"Save expanded dataset to '{args.output}' in this folder? [Y/n]: ").strip().lower()
        except Exception:
            save_choice = 'n'
        if save_choice in ('', 'y', 'yes'):
            if not save_movies(args.output, movies):
                    err = get_last_save_error() or 'unknown error'
                    print(f"Failed to save expanded dataset: {err}")


if __name__ == '__main__':
    main()
