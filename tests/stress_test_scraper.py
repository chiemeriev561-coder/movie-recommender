"""
Stress testing and isolation verification script for Scraper Microservice (Port 8001).
Tests concurrency, throughput, error resilience, and confirms service stays up under load.
"""

import sys
import time
import asyncio
from pathlib import Path

# Add paths
snap_dist_packages = "/home/victor/snap/antigravity-cli/common/local/lib/python3.14/dist-packages"
if Path(snap_dist_packages).is_dir() and snap_dist_packages not in sys.path:
    sys.path.insert(0, snap_dist_packages)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

BASE_URL = "http://127.0.0.1:8001"


async def worker(client: httpx.AsyncClient, worker_id: int, requests_per_worker: int, results: list):
    endpoints = [
        ("GET", "/health", None),
        ("GET", "/", None),
        ("POST", "/api/v1/scraper/search", {"query": f"Movie {worker_id}", "limit": 5}),
        ("POST", "/api/v1/scraper/options", {"url": f"https://thenkiri.com/movie-{worker_id}"}),
        ("GET", "/api/v1/scraper/stats", None),
    ]

    for i in range(requests_per_worker):
        method, path, body = endpoints[i % len(endpoints)]
        start = time.perf_counter()
        try:
            if method == "GET":
                resp = await client.get(f"{BASE_URL}{path}")
            else:
                resp = await client.post(f"{BASE_URL}{path}", json=body)
            duration_ms = (time.perf_counter() - start) * 1000.0
            results.append({
                "status_code": resp.status_code,
                "duration_ms": duration_ms,
                "success": resp.status_code == 200,
                "error": None
            })
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000.0
            results.append({
                "status_code": 0,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e)
            })


async def run_stress_test(concurrency: int = 20, requests_per_worker: int = 25):
    total_expected = concurrency * requests_per_worker
    print(f"\n--- Starting Stress Test: {total_expected} requests ({concurrency} workers x {requests_per_worker}) ---")
    
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    timeout = httpx.Timeout(10.0, connect=5.0)
    
    results = []
    start_total = time.perf_counter()
    
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        tasks = [
            asyncio.create_task(worker(client, wid, requests_per_worker, results))
            for wid in range(concurrency)
        ]
        await asyncio.gather(*tasks)
        
    total_time = time.perf_counter() - start_total
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    latencies = sorted([r["duration_ms"] for r in successful]) if successful else []
    
    rps = len(results) / total_time if total_time > 0 else 0
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
    mean_lat = sum(latencies) / len(latencies) if latencies else 0

    print(f"Total Requests:      {len(results)}")
    print(f"Successful:          {len(successful)} ({len(successful)/len(results)*100:.1f}%)")
    print(f"Failed:              {len(failed)}")
    print(f"Total Time Taken:    {total_time:.3f} s")
    print(f"Throughput:          {rps:.1f} req/sec")
    print(f"Latency Mean:        {mean_lat:.2f} ms")
    print(f"Latency P50:         {p50:.2f} ms")
    print(f"Latency P95:         {p95:.2f} ms")
    print(f"Latency P99:         {p99:.2f} ms")
    
    if failed:
        print("\nSample failures:")
        for f in failed[:5]:
            print("  ", f)

    assert len(failed) == 0, f"Stress test encountered {len(failed)} failures"
    print("\n Stress test passed successfully!")


if __name__ == "__main__":
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    reqs_per_worker = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    asyncio.run(run_stress_test(concurrency, reqs_per_worker))
