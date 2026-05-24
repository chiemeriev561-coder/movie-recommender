package middleware

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/redis/go-redis/v9"
)

// RateLimit returns a sliding window rate limiter middleware.
// maxRequests: how many requests allowed
// windowSecs:  the time window in seconds
//
// This is the same algorithm you built in FastAPI/Redis —
// just Go this time. A sorted set stores request timestamps.
// On each request we:
//  1. Remove timestamps older than the window
//  2. Count remaining entries
//  3. Reject if over limit, otherwise add current timestamp
func RateLimit(rdb *redis.Client, maxRequests int, windowSecs int64) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx := context.Background()
			ip := getIP(r)
			key := fmt.Sprintf("rl:%s", ip)

			now := time.Now().UnixMilli()
			windowStart := now - (windowSecs * 1000)

			pipe := rdb.Pipeline()

			// Remove timestamps outside the current window
			pipe.ZRemRangeByScore(ctx, key, "0", fmt.Sprintf("%d", windowStart))

			// Count requests in current window
			countCmd := pipe.ZCard(ctx, key)

			// Add current request timestamp
			pipe.ZAdd(ctx, key, redis.Z{
				Score:  float64(now),
				Member: fmt.Sprintf("%d", now),
			})

			// Set key expiry to window size so Redis auto-cleans
			pipe.Expire(ctx, key, time.Duration(windowSecs)*time.Second)

			_, err := pipe.Exec(ctx)
			if err != nil {
				// Redis down — fail open (let request through) rather than
				// killing the whole service. Log it though.
				next.ServeHTTP(w, r)
				return
			}

			count := countCmd.Val()
			if count >= int64(maxRequests) {
				w.Header().Set("Content-Type", "application/json")
				w.Header().Set("X-RateLimit-Limit", fmt.Sprintf("%d", maxRequests))
				w.Header().Set("X-RateLimit-Remaining", "0")
				w.WriteHeader(http.StatusTooManyRequests)
				w.Write([]byte(`{"error": "rate limit exceeded", "retry_after_seconds": 60}`))
				return
			}

			// Attach remaining count to response headers — useful for debugging
			w.Header().Set("X-RateLimit-Limit", fmt.Sprintf("%d", maxRequests))
			w.Header().Set("X-RateLimit-Remaining", fmt.Sprintf("%d", int64(maxRequests)-count-1))

			next.ServeHTTP(w, r)
		})
	}
}

// getIP extracts the real client IP, respecting proxy headers
func getIP(r *http.Request) string {
	// Check X-Forwarded-For first (set by Render, Nginx, etc)
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		return xff
	}
	if xri := r.Header.Get("X-Real-IP"); xri != "" {
		return xri
	}
	return r.RemoteAddr
}
