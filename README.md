 Movie Recommender System
A full-stack movie discovery platform with intelligent search, personalized recommendations, and seamless streaming capabilities.

📋 Table of Contents
Overview

System Architecture

Features

Technology Stack

Project Structure

Installation & Setup

Configuration

Running the Application

API Documentation

Frontend Integration

Testing

Deployment

Troubleshooting

Contributing

License

🚀 Overview
The Movie Recommender System is a production-ready web application that combines a FastAPI backend, a Go gateway for performance optimization, and a modern frontend (via Lovable). Users can:

Search movies using advanced filters (genre, year, rating, cast, director)

Get personalized recommendations based on their preferences

Stream movies through embedded video players

Save favorites and track watch history

View detailed movie information including trailers, ratings, and watch providers

🏗️ System Architecture
High-Level Architecture
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT (Browser)                                │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                      Frontend (Lovable)                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────────┐ │   │
│  │  │  Search  │ │  Player  │ │ Favorites│ │ Recommendations     │ │   │
│  │  │  Panel   │ │  (iframe)│ │  Manager │ │  Display            │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GO GATEWAY (Optional)                              │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │  • Rate Limiting (Redis-backed)                                  │   │
│  │  • Request Caching                                               │   │
│  │  • Favorites Management (local)                                  │   │
│  │  • Request/Response Transformation                                │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI BACKEND                                   │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │   │
│  │  │   Core API   │  │  TMDB Client │  │   Recommendation       │ │   │
│  │  │  Endpoints   │  │  (Async)     │  │   Engine               │ │   │
│  │  └──────────────┘  └──────────────┘  └────────────────────────┘ │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │   │
│  │  │    Cache     │  │ Rate Limiting│  │   Favorites            │ │   │
│  │  │  (diskcache) │  │   (SlowAPI)  │  │   Management           │ │   │
│  │  └──────────────┘  └──────────────┘  └────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                  │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │   │
│  │  │  TMDB API    │  │  VidLink     │  │  Redis (for Go         │ │   │
│  │  │  (Movies,    │  │  (Streaming  │  │  Gateway if used)      │ │   │
│  │  │  Trailers,   │  │  Provider)   │  │                        │ │   │
│  │  │  Providers)  │  │              │  │                        │ │   │
│  │  └──────────────┘  └──────────────┘  └────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘



Data Flow Diagram

┌──────────────────────────────────────────────────────────────────┐
│                        SEARCH FLOW                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   User Input ─────► Advanced Search Endpoint                    │
│   (Filters)               │                                     │
│                           ▼                                     │
│                    ┌──────────────────┐                         │
│                    │  Check Cache     │─── Cache Hit ──► Return │
│                    └──────────────────┘                         │
│                           │                                     │
│                           ▼                                     │
│                    ┌──────────────────┐                         │
│                    │  Query TMDB API  │                         │
│                    │  /discover/movie │                         │
│                    └──────────────────┘                         │
│                           │                                     │
│                           ▼                                     │
│                    ┌──────────────────┐                         │
│                    │  Get Top Match   │                         │
│                    │  TMDB ID         │                         │
│                    └──────────────────┘                         │
│                           │                                     │
│                           ▼                                     │
│                    ┌──────────────────┐                         │
│                    │  Fetch TMDB      │                         │
│                    │  Recommendations │                         │
│                    └──────────────────┘                         │
│                           │                                     │
│                           ▼                                     │
│                    ┌──────────────────┐                         │
│                    │  Return Results  │                         │
│                    │  +               │                         │
│                    │  Recommendations │                         │
│                    └──────────────────┘                         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

 Features
🔍 Advanced Search
Multi-filter search by title, genre, year range, rating range, cast, and director

TMDB Discovery API integration for powerful filtering

Automatic recommendations based on the top search result

Natural language search support (coming soon)

🎥 Streaming
Embedded player via VidLink provider

Cross-browser compatible (Chrome, Firefox, Safari)

Responsive design with 16:9 aspect ratio

Error handling with graceful fallbacks

📊 Recommendations
TMDB-based recommendations from the official API

Similar movies recommendations

Personalized suggestions based on user preferences

Trending movies from TMDB

❤️ Favorites
Persistent storage in favorites.json

User-specific favorites (IP-based)

CRUD operations (add, remove, list)

Integration with recommendation engine

🎬 Movie Details
Posters and backdrops from TMDB

YouTube trailers from TMDB

Watch providers with affiliate links

Cast and crew information

User ratings and reviews

⚡ Performance
Multi-level caching (diskcache, Redis)

Rate limiting (30-60 requests per minute)

Async operations for I/O-bound tasks

CDN integration for media assets

🛠️ Technology Stack
Backend
Technology	Purpose
Python 3.12+	Core programming language
FastAPI	Web framework (async, OpenAPI)
Uvicorn	ASGI server
Gunicorn	Production WSGI server
httpx	Async HTTP client for TMDB
Pydantic	Data validation and serialization
diskcache	Persistent disk caching
slowapi	Rate limiting
python-dotenv	Environment configuration
Frontend
Technology	Purpose
React	UI framework
Tailwind CSS	Styling
Lovable	Frontend deployment/hosting
iframe	Embed streaming player
Infrastructure
Technology	Purpose
Go	Gateway (proxy, caching, rate limiting)
Redis	Cache and rate limit storage (optional)
Render.com	Backend deployment
Lovable	Frontend hosting
External APIs
API	Purpose
TMDB	Movie data, posters, trailers, recommendations
VidLink	Streaming embed provider
YouTube	Trailer hosting
📁 Project Structure
movie-recommender/
├── api.py                      # FastAPI application
├── movie_recommender.py        # Core recommendation engine
├── run_api.py                  # API runner script
├── csv_loader.py               # CSV data loading utilities
├── requirements.txt            # Python dependencies
├── .env.template               # Environment configuration template
├── Procfile                    # Production deployment config
├── README.md                   # This file
├── API_DOCUMENTATION.md        # Detailed API reference
│
├── go-gateway/                 # Go gateway (optional)
│   ├── main.go
│   ├── go.mod
│   └── go.sum
│
├── tests/                      # Test suite
│   ├── test_api.py
│   ├── test_recommender.py
│   └── ...
│
├── .api_cache/                 # Disk cache directory (auto-generated)
├── favorites.json              # Favorites persistence
└── .venv/                      # Virtual environment (local development)

Installation & Setup
Prerequisites
Python 3.12+

TMDB API Key (Get one here)

(Optional) Go 1.21+ for gateway

(Optional) Redis for gateway

Step 1: Clone the Repository
git clone https://github.com/yourusername/movie-recommender.git
cd movie-recommender

Step 2: Create Virtual Environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

Step 3: Install Dependencies
pip install -r requirements.txt

Step 4: Configure Environment
cp .env.template .env

Edit .env with your configuration

# Required
TMDB_API_KEY=your_tmdb_api_key_here
PORT=8000
HOST=0.0.0.0

# Optional
FAVORITES_FILE=favorites.json
LOG_LEVEL=info
RELOAD=false
ALLOWED_ORIGINS=http://localhost:3000,https://cine-craft-box.lovable.app
ALLOWED_ORIGIN_REGEX=https?://(.*\.)?lovable(app|project)\.com

Step 5: Run the application
python run_api.py


The API will be available at:

Swagger UI: http://localhost:8000/docs

ReDoc: http://localhost:8000/redoc

Health Check: http://localhost:8000/api/health

⚙️ Configuration
Environment Variables
Variable	Required	Default	Description
TMDB_API_KEY	✅	-	TMDB API key for movie data
PORT	❌	8000	Server port
HOST	❌	0.0.0.0	Server host
RELOAD	❌	false	Auto-reload on code changes
LOG_LEVEL	❌	info	Logging level (debug, info, warning, error)
FAVORITES_FILE	❌	favorites.json	Favorites storage file
ALLOWED_ORIGINS	❌	-	CORS allowed origins (comma-separated)
ALLOWED_ORIGIN_REGEX	❌	-	CORS allowed origin regex
MOVIES_CSV_PATH	❌	-	Path to movies CSV (optional)
RATINGS_CSV_PATH	❌	-	Path to ratings CSV (optional)
Rate Limiting
Endpoint	Rate Limit	Purpose
/	60/minute	Root endpoint
/api/movies/trending	20/minute	Trending movies
/api/movies/search	30/minute	Search
/api/movies/advanced-search	20/minute	Advanced search
/api/movies/featured	30/minute	Featured movies
/api/movies/{id}/stream	30/minute	Streaming URL
/api/recommend/*	30/minute	Recommendations
/api/favorites	30/minute	Favorites management


API Documentation
Main Endpoints
Method	Endpoint	Description
GET	/api/movies/trending	Trending movies
GET	/api/movies/search	Basic search
GET	/api/movies/advanced-search	Advanced search with filters
GET	/api/movies/featured	Featured movies
GET	/api/movies/top	Top-rated movies
GET	/api/movies/{id}	Movie details
GET	/api/movies/{id}/trailer	Movie trailer
GET	/api/movies/{id}/stream	Streaming URL
GET	/api/movies/{id}/recommendations	Basic recommendations
GET	/api/movies/{id}/recommendations-enhanced	Enhanced recommendations
GET	/api/movies/{id}/watch-providers	Watch providers
GET	/api/favorites	Get favorites
POST	/api/favorites	Add favorite
DELETE	/api/favorites	Remove favorite
GET	/api/genres	List genres
GET	/api/categories	List categories
GET	/api/statistics	Statistics
GET	/api/recommend/by-title	Title-based recommendations
GET	/api/recommendations	Personalized recommendations
GET	/api/recommendations/discovery	Discovery recommendations
Advanced Search Parameters
http
GET /api/movies/advanced-search?query=matrix&genres=Action,Sci-Fi&year_min=1995&year_max=2005&rating_min=7.0&cast=Keanu+Reeves&director=Lana+Wachowski&sort_by=popularity.desc
Parameter	Type	Description
query	string	Movie title or keywords
genres	string	Comma-separated genre names (e.g., Action,Sci-Fi)
year_min	integer	Minimum release year
year_max	integer	Maximum release year
rating_min	float	Minimum rating (0-10)
rating_max	float	Maximum rating (0-10)
cast	string	Actor name
director	string	Director name
sort_by	string	Sort order (popularity.desc, vote_average.desc, release_date.desc, revenue.desc)
Response Format
json
{
  "search_results": [
    {
      "id": 603,
      "name": "The Matrix",
      "year": 1999,
      "category": "Action",
      "genre": "Action, Sci-Fi",
      "description": "A computer hacker learns the truth about reality...",
      "rating": 8.7,
      "poster_url": "https://image.tmdb.org/t/p/w500/..."
    }
  ],
  "recommendations": [
    // Similar format as above
  ],
  "filters_used": {
    "genres": ["Action", "Sci-Fi"],
    "rating_min": 7.0
  },
  "total_results": 20,
  "source": "TMDB"
}
🎨 Frontend Integration
Frontend Repository
The frontend is hosted on Lovable at:
🔗 https://cine-craft-box.lovable.app

API Base URL
The frontend should call the backend API at:

Development: http://localhost:8000

Production: https://movie-recommender-7zqv.onrender.com

Environment Configuration in Frontend
Create a .env file in your frontend project:

env
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT=10000
Example API Calls
Search with Filters:

javascript
async function advancedSearch(filters) {
  const params = new URLSearchParams();
  if (filters.query) params.append('query', filters.query);
  if (filters.genres) params.append('genres', filters.genres.join(','));
  if (filters.yearMin) params.append('year_min', filters.yearMin);
  if (filters.yearMax) params.append('year_max', filters.yearMax);
  if (filters.ratingMin) params.append('rating_min', filters.ratingMin);
  if (filters.cast) params.append('cast', filters.cast);
  if (filters.director) params.append('director', filters.director);
  
  const response = await fetch(`/api/movies/advanced-search?${params}`);
  return response.json();
}
Get Streaming URL:

javascript
async function getStreamUrl(movieId) {
  const response = await fetch(`/api/movies/${movieId}/stream`);
  const data = await response.json();
  return data.stream_url; // https://vidlink.pro/movie/603
}
Render iframe:

jsx
<div className="relative w-full pt-[56.25%]">
  <iframe
    src={streamUrl}
    className="absolute top-0 left-0 w-full h-full"
    allowFullScreen
    allow="encrypted-media; autoplay"
  />
</div>
🧪 Testing
Run All Tests
bash
PYTHONPATH=. python -m pytest
Run Specific Test File
bash
PYTHONPATH=. python -m pytest tests/test_api.py
Run with Coverage
bash
PYTHONPATH=. python -m pytest --cov=. --cov-report=html
Test Structure
text
tests/
├── test_api.py              # API endpoint tests
├── test_recommender.py      # Recommendation engine tests
├── test_csv_loader.py       # CSV loading tests
├── test_models.py           # Pydantic model tests
└── conftest.py              # Test fixtures
🚀 Deployment
Backend Deployment (Render.com)
Create a Render account at render.com

Connect your GitHub repository

Create a new Web Service

Configure:

Environment: Python

Build Command: pip install -r requirements.txt

Start Command: gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT

Add environment variables:

TMDB_API_KEY: Your TMDB API key

PORT: 10000 (Render default)

ALLOWED_ORIGINS: Your frontend URL

Deploy

Frontend Deployment (Lovable)
Connect your frontend repository to Lovable

Configure build settings:

Build Command: npm run build

Output Directory: dist

Add environment variables:

VITE_API_BASE_URL: https://movie-recommender-7zqv.onrender.com

Deploy

Go Gateway Deployment
Build the Go binary:

bash
cd go-gateway
GOOS=linux GOARCH=amd64 go build -o gateway
Deploy to a server with Redis

Configure environment variables:

bash
export UPSTREAM_URL=http://fastapi:8000
export PORT=8080
export REDIS_ADDR=redis:6379
Run the gateway: ./gateway

🔧 Troubleshooting
Common Issues
1. Streaming Not Working in Firefox
Problem: Firefox shows "disabled sandbox" or doesn't load the player.

Solution:

jsx
// Remove or modify sandbox attribute
<iframe
  src={streamUrl}
  className="w-full h-full"
  allowFullScreen
  allow="encrypted-media; autoplay"
  // Remove sandbox or add allow-modals
  sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals"
/>
2. 404 Errors from VidLink
Problem: VidLink returns 404 when using /embed/ in the URL.

Solution: Use the correct format:

python
# ❌ Wrong
stream_url = f"https://vidlink.pro/embed/movie/{movie_id}"

# ✅ Correct
stream_url = f"https://vidlink.pro/movie/{movie_id}"
3. CORS Errors
Problem: Frontend cannot access the API due to CORS.

Solution: Update ALLOWED_ORIGINS in .env:

env
ALLOWED_ORIGINS=http://localhost:3000,https://cine-craft-box.lovable.app
4. Rate Limiting Issues
Problem: Too many requests (429 errors).

Solution:

Implement exponential backoff in frontend

Reduce request frequency

Adjust rate limits in api.py

5. TMDB API Key Issues
Problem: Missing or invalid TMDB API key.

Solution:

Sign up at TMDB

Request an API key

Add to .env: TMDB_API_KEY=your_key_here

🤝 Contributing
Guidelines
Fork the repository

Create a feature branch:

bash
git checkout -b feature/amazing-feature
Commit your changes:

bash
git commit -m 'Add some amazing feature'
Push to the branch:

bash
git push origin feature/amazing-feature
Open a Pull Request

Code Style
Python: PEP 8 compliant

Type hints: Use Python type hints

Docstrings: Google style docstrings

Tests: Include tests for new features

Development Workflow
Setup: python -m venv .venv && source .venv/bin/activate

Install: pip install -r requirements.txt

Run tests: PYTHONPATH=. python -m pytest

Run API: python run_api.py

Check linting: flake8 api.py

📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

🙏 Acknowledgments
TMDB for providing movie data

FastAPI for the excellent web framework

Lovable for frontend hosting

All contributors who helped build this project

📞 Support
Issues: GitHub Issues

Discussions: GitHub Discussions

Email: your-email@example.com

🔗 Links
Live Demo: https://cine-craft-box.lovable.app

API Docs: https://movie-recommender-7zqv.onrender.com/docs

ReDoc: https://movie-recommender-7zqv.onrender.com/redoc

GitHub: https://github.com/yourusername/movie-recommender

📊 Status Badges
https://img.shields.io/badge/build-passing-brightgreen
https://img.shields.io/badge/coverage-85%2525-green
https://img.shields.io/badge/python-3.12%252B-blue
https://img.shields.io/badge/FastAPI-0.100%252B-green
https://img.shields.io/badge/license-MIT-blue

Built with ❤️ by the Movie Recommender Team

Last Updated: August 2026

