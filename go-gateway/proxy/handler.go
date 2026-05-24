package proxy

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"

	"go-gateway/recommender"
)

// TTLs for different endpoints
const (
	defaultTTL  = 10 * time.Minute
	trendingTTL = 30 * time.Minute
)

// Handler holds our upstream URL, Redis client, and custom HTTP client
type Handler struct {
	upstream string
	rdb      *redis.Client
	client   *http.Client
}

// NewHandler creates a new proxy handler
func NewHandler(upstream string, rdb *redis.Client) *Handler {
	return &Handler{
		upstream: strings.TrimRight(upstream, "/"),
		rdb:      rdb,
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

// Plain proxies the request directly to FastAPI with no caching
func (h *Handler) Plain(w http.ResponseWriter, r *http.Request) {
	h.forward(w, r, false)
}

// Cached checks Redis first, forwards on miss, caches the response
func (h *Handler) Cached(w http.ResponseWriter, r *http.Request) {
	h.forward(w, r, true)
}

func (h *Handler) forward(w http.ResponseWriter, r *http.Request, useCache bool) {
	ctx := context.Background()
	cacheKey := buildCacheKey(r)

	if useCache {
		cached, err := h.rdb.Get(ctx, cacheKey).Bytes()
		if err == nil {
			log.Printf("[CACHE HIT]  %s", cacheKey)
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("X-Cache", "HIT")
			w.WriteHeader(http.StatusOK)
			w.Write(cached)
			return
		}
		log.Printf("[CACHE MISS] %s", cacheKey)
	}

	target, err := url.Parse(h.upstream + r.URL.RequestURI())
	if err != nil {
		http.Error(w, "bad upstream URL", http.StatusInternalServerError)
		return
	}

	outReq, err := http.NewRequestWithContext(ctx, r.Method, target.String(), r.Body)
	if err != nil {
		http.Error(w, "failed to create request", http.StatusInternalServerError)
		return
	}

	copyHeaders(outReq.Header, r.Header)
	outReq.Header.Set("X-Forwarded-For", r.RemoteAddr)
	outReq.Header.Set("X-Forwarded-Host", r.Host)

	resp, err := h.client.Do(outReq)
	if err != nil {
		log.Printf("[ERROR] upstream request failed: %v", err)
		http.Error(w, `{"error": "upstream unavailable"}`, http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		http.Error(w, "failed to read upstream response", http.StatusInternalServerError)
		return
	}

	if useCache && resp.StatusCode == http.StatusOK {
		ttl := getTTL(r.URL.Path)
		if setErr := h.rdb.Set(ctx, cacheKey, body, ttl).Err(); setErr != nil {
			log.Printf("[WARN] cache write failed for %s: %v", cacheKey, setErr)
		} else {
			log.Printf("[CACHED]     %s (ttl: %s)", cacheKey, ttl)
		}
	}

	for key, values := range resp.Header {
		for _, v := range values {
			w.Header().Add(key, v)
		}
	}
	w.Header().Set("X-Cache", "MISS")
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, bytes.NewReader(body))
}

// buildCacheKey creates a stable Redis key from path + sorted query params
func buildCacheKey(r *http.Request) string {
	return fmt.Sprintf("cache:%s?%s", r.URL.Path, r.URL.RawQuery)
}

// getTTL returns the appropriate cache TTL based on the endpoint
func getTTL(path string) time.Duration {
	if strings.Contains(path, "trending") || strings.Contains(path, "featured") {
		return trendingTTL
	}
	return defaultTTL
}

// copyHeaders copies headers from src to dst, skipping hop-by-hop headers
func copyHeaders(dst, src http.Header) {
	hopByHop := map[string]bool{
		"Connection":          true,
		"Keep-Alive":          true,
		"Proxy-Authenticate":  true,
		"Proxy-Authorization": true,
		"Te":                  true,
		"Trailers":            true,
		"Transfer-Encoding":   true,
		"Upgrade":             true,
	}
	for key, values := range src {
		if hopByHop[key] {
			continue
		}
		for _, v := range values {
			dst.Add(key, v)
		}
	}
}

// --- DIRECT GO ENDPOINT HANDLERS ---

// PingHandler responds with "pong" directly without forwarding to Python
func (h *Handler) PingHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("pong"))
}

// RootHandler handles "/" directly from Go
func (h *Handler) RootHandler(w http.ResponseWriter, r *http.Request) {
	recommender.LoadFavorites(recommender.FavoritesFile)
	favs := recommender.Favorites
	
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"message":         "Movie Recommender API (Go Gateway)",
		"version":         "1.0.0",
		"docs":            "/docs",
		"redoc":           "/redoc",
		"favorites_count": len(favs),
	})
}

// GetFavoritesHandler returns the user's favorites from Go's thread-safe in-memory dataset
func (h *Handler) GetFavoritesHandler(w http.ResponseWriter, r *http.Request) {
	recommender.LoadFavorites(recommender.FavoritesFile)
	favMovies := recommender.GetFavoriteMovies()
	
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(favMovies)
}

type FavoriteRequest struct {
	Name string `json:"name"`
	Year int    `json:"year"`
}

// AddFavoriteHandler forwards write to Python to sync IP caching, then reloads Go's local cache
func (h *Handler) AddFavoriteHandler(w http.ResponseWriter, r *http.Request) {
	// Read request body to parse favorite details
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed to read body", http.StatusBadRequest)
		return
	}
	// Restore body for proxying
	r.Body = io.NopCloser(bytes.NewReader(bodyBytes))

	var favReq FavoriteRequest
	if err := json.Unmarshal(bodyBytes, &favReq); err != nil {
		http.Error(w, "invalid request JSON", http.StatusBadRequest)
		return
	}

	// Validate movie exists in Go memory dataset first
	nameLower := strings.ToLower(favReq.Name)
	recommender.Mutex.RLock()
	movieExists := false
	for _, m := range recommender.Movies {
		if strings.ToLower(m.Name) == nameLower && m.Year == favReq.Year {
			movieExists = true
			break
		}
	}
	recommender.Mutex.RUnlock()

	if !movieExists {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(`{"detail": "Not found or already in favorites"}`))
		return
	}

	// 1. Forward/Proxy write to Python so it updates Python's diskcache/personalization states
	target, err := url.Parse(h.upstream + r.URL.RequestURI())
	if err != nil {
		http.Error(w, "bad upstream URL", http.StatusInternalServerError)
		return
	}
	
	// Create outgoing request
	outReq, err := http.NewRequestWithContext(r.Context(), r.Method, target.String(), bytes.NewReader(bodyBytes))
	if err != nil {
		http.Error(w, "failed to create proxy request", http.StatusInternalServerError)
		return
	}
	copyHeaders(outReq.Header, r.Header)
	outReq.Header.Set("X-Forwarded-For", r.RemoteAddr)
	outReq.Header.Set("X-Forwarded-Host", r.Host)

	resp, err := h.client.Do(outReq)
	if err != nil {
		log.Printf("[ERROR] AddFavorite proxy request failed: %v", err)
		http.Error(w, `{"error": "upstream unavailable"}`, http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		http.Error(w, "failed to read upstream response", http.StatusInternalServerError)
		return
	}

	// 2. If python write succeeded, force Go's favorites in-memory state to refresh from favorites.json
	if resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusCreated {
		recommender.LoadFavorites(recommender.FavoritesFile)
		log.Printf("[SYNC] Added to favorites: %s (%d), reloading favorites list", favReq.Name, favReq.Year)
	}

	// 3. Return upstream response headers and body
	for key, values := range resp.Header {
		for _, v := range values {
			w.Header().Add(key, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	w.Write(respBody)
}

// RemoveFavoriteHandler forwards write to Python to sync IP caching, then reloads Go's local cache
func (h *Handler) RemoveFavoriteHandler(w http.ResponseWriter, r *http.Request) {
	// Read request body to parse favorite details
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed to read body", http.StatusBadRequest)
		return
	}
	// Restore body for proxying
	r.Body = io.NopCloser(bytes.NewReader(bodyBytes))

	var favReq FavoriteRequest
	if err := json.Unmarshal(bodyBytes, &favReq); err != nil {
		http.Error(w, "invalid request JSON", http.StatusBadRequest)
		return
	}

	// 1. Forward/Proxy write to Python so it updates Python's diskcache/personalization states
	target, err := url.Parse(h.upstream + r.URL.RequestURI())
	if err != nil {
		http.Error(w, "bad upstream URL", http.StatusInternalServerError)
		return
	}
	
	// Create outgoing request
	outReq, err := http.NewRequestWithContext(r.Context(), r.Method, target.String(), bytes.NewReader(bodyBytes))
	if err != nil {
		http.Error(w, "failed to create proxy request", http.StatusInternalServerError)
		return
	}
	copyHeaders(outReq.Header, r.Header)
	outReq.Header.Set("X-Forwarded-For", r.RemoteAddr)
	outReq.Header.Set("X-Forwarded-Host", r.Host)

	resp, err := h.client.Do(outReq)
	if err != nil {
		log.Printf("[ERROR] RemoveFavorite proxy request failed: %v", err)
		http.Error(w, `{"error": "upstream unavailable"}`, http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		http.Error(w, "failed to read upstream response", http.StatusInternalServerError)
		return
	}

	// 2. If python delete succeeded, force Go's favorites in-memory state to refresh from favorites.json
	if resp.StatusCode == http.StatusOK {
		recommender.LoadFavorites(recommender.FavoritesFile)
		log.Printf("[SYNC] Removed from favorites: %s (%d), reloading favorites list", favReq.Name, favReq.Year)
	}

	// 3. Return upstream response headers and body
	for key, values := range resp.Header {
		for _, v := range values {
			w.Header().Add(key, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	w.Write(respBody)
}
