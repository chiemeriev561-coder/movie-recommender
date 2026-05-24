package main

import (
	"log"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"
	"github.com/redis/go-redis/v9"

	"go-gateway/middleware"
	"go-gateway/proxy"
	"go-gateway/recommender"
)

func main() {
	// Upstream FastAPI on Render or local
	upstream := getEnv("UPSTREAM_URL", "http://localhost:8000")

	// Connect to Redis
	rdb := redis.NewClient(&redis.Options{
		Addr:     getEnv("REDIS_ADDR", "localhost:6379"),
		Password: getEnv("REDIS_PASSWORD", ""),
		DB:       0,
	})

	// Initialize local movie dataset and load current favorites
	log.Println("Initializing movie dataset...")
	recommender.InitializeMovieDataset()
	log.Println("Loading favorites dataset...")
	recommender.LoadFavorites(recommender.FavoritesFile)
	log.Printf("Loaded %d favorites", len(recommender.Favorites))

	// Router
	r := chi.NewRouter()

	// Global middleware
	r.Use(chimiddleware.Logger)    // logs every request with latency
	r.Use(chimiddleware.Recoverer) // recovers from panics, returns 500

	// Rate limiter: 30 requests/minute per IP (sliding window via Redis)
	r.Use(middleware.RateLimit(rdb, 30, 60))

	// Proxy & direct handler
	h := proxy.NewHandler(upstream, rdb)

	// --- Direct/Local endpoints (no upstream/Python hit) ---
	r.Get("/ping", h.PingHandler)
	r.Head("/ping", h.PingHandler)
	r.Get("/", h.RootHandler)
	r.Head("/", h.RootHandler)

	// Favorites (GET is local from memory cache, POST/DELETE are proxied and synced)
	r.Get("/api/favorites", h.GetFavoritesHandler)
	r.Post("/api/favorites", h.AddFavoriteHandler)
	r.Delete("/api/favorites", h.RemoveFavoriteHandler)

	// --- Cached proxy endpoints (TMDB responses are expensive, cache them) ---
	r.Get("/api/movies/trending", h.Cached)
	r.Get("/api/movies/search", h.Cached)
	r.Get("/api/movies/featured", h.Cached)

	// --- Catch-all proxy endpoint (forward everything else to Python) ---
	r.HandleFunc("/*", h.Plain)

	port := getEnv("PORT", "8080")
	log.Printf("Go gateway running on :%s → %s", port, upstream)
	log.Fatal(http.ListenAndServe(":"+port, r))
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}
