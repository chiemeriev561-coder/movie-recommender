package middleware

import (
	"fmt"
	"math/rand"
	"net"
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
			ctx := r.Context()
			ip := getIP(r)
			key := fmt.Sprintf("rl:%s", ip)

			now := time.Now().UnixMilli()
			windowStart := now - (windowSecs * 1000)

			// Count-and-add must be one atomic operation. A normal pipeline can
			// interleave two requests between ZCARD and ZADD and let both through.
			lua := redis.NewScript(`
				redis.call('ZREMRANGEBYSCORE', KEYS[1], '0', ARGV[1])
				local count = redis.call('ZCARD', KEYS[1])
				if count >= tonumber(ARGV[2]) then
					redis.call('EXPIRE', KEYS[1], ARGV[3])
					return count
				end
				redis.call('ZADD', KEYS[1], ARGV[4], ARGV[5])
				redis.call('EXPIRE', KEYS[1], ARGV[3])
				return count
			`)
			countValue, err := lua.Run(ctx, rdb, []string{key},
				windowStart, maxRequests, windowSecs,
				now, fmt.Sprintf("%d-%f", now, rand.Float64()),
			).Int64()
			if err != nil {
				// Redis down — fail open (let request through) rather than
				// killing the whole service. Log it though.
				next.ServeHTTP(w, r)
				return
			}

			count := countValue
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
	// Do not trust client-controlled forwarding headers. If the gateway is
	// deployed behind a trusted load balancer, normalize its address before
	// this middleware or add an explicit trusted-proxy implementation.
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil {
		return host
	}
	return r.RemoteAddr
}
