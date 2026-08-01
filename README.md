 Movie Recommender System
========================

A production-ready web application for movie discovery with advanced search, personalized recommendations, and streaming integration.

Table of Contents
-----------------
- Overview
- System Architecture
- Data Flow
- Features
- Technology Stack
- Project Structure
- Installation & Setup
- Configuration
- Running the Application
- API Reference (summary)
- Frontend Integration
- Testing
- Deployment
- Troubleshooting
- Contributing
- License
- Acknowledgments
- Support & Links
- Status & Metadata

Overview
--------
The Movie Recommender System is a full-stack application composed of a FastAPI backend, a Go gateway as a performance layer, and a frontend hosted on Lovable. The application provides advanced filtering, personalized recommendations, streaming embeds, persistent favorites, and detailed movie metadata.

System Architecture (ASCII)
---------------------------
High-level architecture:

+-------------------------------------------------------------------------------------------+
|                                 Client (Browser)                                         |
|  Frontend (Lovable)                                                                       |
|  - Search Panel    - Player (iframe)    - Favorites Manager    - Recommendations Display  |
+-------------------------------------------------------------------------------------------+
                                      |
                                      | HTTPS
                                      v
+-----------------------------+     +-----------------------------+     +-----------------------------+
|        Go Gateway           |---->|       FastAPI Backend       |---->|     External Services       |
|  Rate limiting (Redis)      |     |  Core API Endpoints         |     |  TMDB  VidLink  YouTube     |
|  Request caching            |     |  TMDB async client          |     |  Redis (cache, rate limits) |
|  Request/response transform |     |  Recommendation engine      |     |                             |
|  Favorites handling         |     |  diskcache, slowapi         |     |                             |
+-----------------------------+     +-----------------------------+     +-----------------------------+
                                      ^           ^         ^
                                      |           |         |
                                      +-----------+---------+

Notes
- The Go gateway provides performance features and forwards requests to the FastAPI backend.
- Redis supports gateway caching and rate-limit storage.
- The backend queries TMDB for movie data and YouTube for trailers; VidLink provides streaming embeds.

Data Flow (ASCII)
-----------------

Search flow:
User input -> Advanced Search endpoint -> Check cache
  - Cache hit -> Return cached results
  - Cache miss -> Query TMDB /discover/movie -> Identify top match TMDB ID -> Fetch TMDB recommendations -> Return results + recommendations

ASCII diagram:
User
  |
  v
[Advanced Search Endpoint]
  |
  v
[Check Cache] ---- yes ----> [Return cached results]
  |
  no
  |
  v
[Query TMDB /discover/movie]
  |
  v
[Identify top match TMDB ID]
  |
  v
[Fetch TMDB recommendations]
  |
  v
[Return results + recommendations]

Streaming flow:
User request -> Backend resolves streaming URL -> Return stream_url -> Frontend embeds stream_url in iframe

ASCII diagram:
User
  |
  v
[GET /api/movies/{id}/stream]
  |
  v
[Resolve streaming URL]
  |
  v
[Return stream_url]
  |
  v
[Frontend embeds stream_url in iframe]

Favorites flow:
Frontend -> Favorites API -> Read/update favorites.json -> Return updated favorites -> Recommendation engine receives update

ASCII diagram:
Frontend
  |
  v
[Favorites API]
  |        \
  v         v
[favorites.json]   [Recommendation Engine]

Features
--------
- Advanced search with filters: title, genre, year range, rating range, cast, director, sort options.
- Personalized recommendations based on search results and user preferences.
- Embedded streaming via VidLink.
- Persistent favorites stored in favorites.json or configured storage.
- Detailed movie pages: posters, backdrops, trailers, cast, crew, watch providers, user ratings.
- Multi-level caching and asynchronous I/O for performance.
- Rate limiting across endpoints.

Technology Stack
----------------
Backend
- Python 3.12+
- FastAPI (async web framework)
- Uvicorn (ASGI server)
- Gunicorn (production process manager)
- httpx (async HTTP client)
- Pydantic (data validation)
- diskcache (persistent cache)
- slowapi (rate limiting)
- python-dotenv (environment configuration)

Frontend
- React
- Tailwind CSS
- Lovable (hosting)
- iframe for streaming embeds

Infrastructure
- Go (gateway)
- Redis (cache and rate-limit store)
- Render.com (backend deployment)
- Lovable (frontend hosting)

External APIs
- TMDB: movie metadata, posters, trailers, recommendations
- VidLink: streaming embed provider
- YouTube: trailer hosting

Project Structure
-----------------
movie-recommender/
- api.py                     # FastAPI application
- movie_recommender.py       # Core recommendation engine
- run_api.py                 # API runner
- csv_loader.py              # CSV data utilities
- requirements.txt           # Python dependencies
- .env.template              # Environment configuration template
- Procfile                   # Production startup config
- README.md                  # Project documentation
- API_DOCUMENTATION.md       # Detailed API reference
- go-gateway/
  - main.go
  - go.mod
- tests/
  - test_api.py
  - test_recommender.py
- .api_cache/                # Disk cache directory (auto-generated)
- favorites.json             # Favorites persistence
- .venv/                     # Virtual environment (local development)

Installation & Setup
--------------------
Prerequisites
- Python 3.12+
- TMDB API Key (register at TMDB)
- Go 1.21+ for gateway deployment
- Redis for distributed caching and rate limits when the gateway is deployed

Steps
1. Clone the repository
   git clone https://github.com/yourusername/movie-recommender.git
   cd movie-recommender

2. Create a virtual environment
   python -m venv .venv
   source .venv/bin/activate    # Windows: .venv\Scripts\activate

3. Install dependencies
   pip install -r requirements.txt

4. Configure environment
   cp .env.template .env
   Edit .env with required values

Running the Application
-----------------------
Development
- python run_api.py

Production (example with Gunicorn)
- gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT

API Endpoints
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/api/health

Configuration
-------------
Environment variables

Required
- TMDB_API_KEY: TMDB API key
- PORT: server port (default 8000)
- HOST: server host (default 0.0.0.0)

Additional
- FAVORITES_FILE: defaults to favorites.json
- LOG_LEVEL: defaults to info
- RELOAD: defaults to false
- ALLOWED_ORIGINS: comma-separated origins for CORS
- ALLOWED_ORIGIN_REGEX: origin regex for CORS
- MOVIES_CSV_PATH: path to movies CSV
- RATINGS_CSV_PATH: path to ratings CSV

Rate Limits (applied)
- / : 60 / minute
- /api/movies/trending : 20 / minute
- /api/movies/search : 30 / minute
- /api/movies/advanced-search : 20 / minute
- /api/movies/featured : 30 / minute
- /api/movies/{id}/stream : 30 / minute
- /api/recommend/* : 30 / minute
- /api/favorites : 30 / minute

API Reference (summary)
-----------------------
Main endpoints
- GET /api/movies/trending — Trending movies
- GET /api/movies/search — Basic search
- GET /api/movies/advanced-search — Advanced search with filters
- GET /api/movies/{id} — Movie details
- GET /api/movies/{id}/trailer — Movie trailer
- GET /api/movies/{id}/stream — Streaming URL
- GET /api/movies/{id}/recommendations — Recommendations
- GET /api/favorites — Get favorites
- POST /api/favorites — Add favorite
- DELETE /api/favorites — Remove favorite

Advanced search example
GET /api/movies/advanced-search?query=matrix&genres=Action,Sci-Fi&year_min=1995&year_max=2005&rating_min=7.0&cast=Keanu+Reeves&director=Lana+Wachowski&sort_by=popularity.desc

Response format (JSON)
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
  "recommendations": [ /* similar objects */ ],
  "filters_used": { "genres": ["Action","Sci-Fi"], "rating_min": 7.0 },
  "total_results": 20,
  "source": "TMDB"
}

Frontend Integration
--------------------
Frontend repository (hosted on Lovable)
- Live: https://cine-craft-box.lovable.app

API base URL used by the frontend
- Development: http://localhost:8000
- Production: https://movie-recommender-7zqv.onrender.com

Frontend environment example (.env)
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT=10000

Example frontend calls
- Advanced search (JS)
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

- Get streaming URL (JS)
async function getStreamUrl(movieId) {
  const response = await fetch(`/api/movies/${movieId}/stream`);
  const data = await response.json();
  return data.stream_url;
}

- Embed iframe (JSX)
<div className="relative w-full pt-[56.25%]">
  <iframe
    src={streamUrl}
    className="absolute top-0 left-0 w-full h-full"
    allowFullScreen
    allow="encrypted-media; autoplay"
  />
</div>

Testing
-------
Run all tests
PYTHONPATH=. python -m pytest

Run a specific test file
PYTHONPATH=. python -m pytest tests/test_api.py

Run tests with coverage
PYTHONPATH=. python -m pytest --cov=. --cov-report=html

Testing layout
- tests/
  - test_api.py
  - test_recommender.py
  - test_csv_loader.py
  - test_models.py
  - conftest.py

Deployment
----------
Backend (Render)
1. Create a Render account
2. Connect repository
3. Create a Web Service
4. Build command: pip install -r requirements.txt
5. Start command: gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
6. Add environment variables: TMDB_API_KEY, PORT, ALLOWED_ORIGINS

Frontend (Lovable)
1. Connect frontend repository
2. Build command: npm run build
3. Output directory: dist
4. Set VITE_API_BASE_URL to production API URL

Go Gateway
1. Build binary in go-gateway:
   cd go-gateway
   GOOS=linux GOARCH=amd64 go build -o gateway
2. Configure:
   export UPSTREAM_URL=http://fastapi:8000
   export PORT=8080
   export REDIS_ADDR=redis:6379
3. Run: ./gateway

Troubleshooting
---------------
1. Streaming does not load in Firefox
- Adjust iframe sandbox attributes. Example:
<iframe
  src={streamUrl}
  className="w-full h-full"
  allowFullScreen
  allow="encrypted-media; autoplay"
  sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals"
/>

2. 404 responses from VidLink
- Use the streaming URL format:
stream_url = f"https://vidlink.pro/movie/{movie_id}"

3. CORS errors
- Update ALLOWED_ORIGINS in .env with frontend origin(s)

4. Rate limiting (429)
- Implement exponential backoff in the frontend
- Reduce request frequency
- Adjust rate limits in api.py

5. Invalid or missing TMDB API key
- Register at TMDB and add TMDB API key to .env

Contributing
------------
Guidelines
1. Fork the repository
2. Create a feature branch:
   git checkout -b feature/your-feature
3. Commit changes:
   git commit -m "Add feature description"
4. Push branch:
   git push origin feature/your-feature
5. Open a Pull Request

Code standards
- Follow PEP 8 for Python
- Use type hints
- Use Google-style docstrings
- Include tests for new functionality

Development workflow
- Setup: python -m venv .venv && source .venv/bin/activate
- Install: pip install -r requirements.txt
- Run tests: PYTHONPATH=. python -m pytest
- Run API: python run_api.py
- Lint: flake8 api.py

License
-------
This project is licensed under the MIT License. See the LICENSE file for details.

Acknowledgments
---------------
- TMDB for providing movie data
- FastAPI for the framework
- Lovable for frontend hosting
- Contributors to the project

Support & Links
---------------
- Live demo: https://cine-craft-box.lovable.app
- API docs: https://movie-recommender-7zqv.onrender.com/docs
- ReDoc: https://movie-recommender-7zqv.onrender.com/redoc
- GitHub: https://github.com/yourusername/movie-recommender
- Issues: use GitHub Issues
- Discussions: use GitHub Discussions
- Contact: your-email@example.com

Status & Metadata
-----------------
- Built by the Movie Recommender Team
- Last updated: August 2026

Prepared by GitHub Copilot Chat Assistant