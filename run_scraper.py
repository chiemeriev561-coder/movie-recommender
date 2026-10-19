#!/usr/bin/env python3
"""
Startup script for the Movie Scraper Microservice (Port 8001).
Runs independently from the primary Movie Recommender API (Port 8000).
"""

import os
import sys
from pathlib import Path
# Ensure local site packages / snap packages are discoverable
snap_dist_packages = "/home/victor/snap/antigravity-cli/common/local/lib/python3.14/dist-packages"
if os.path.isdir(snap_dist_packages) and snap_dist_packages not in sys.path:
    sys.path.insert(0, snap_dist_packages)

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from scraper_service.config import (
    SCRAPER_HOST,
    SCRAPER_PORT,
    SCRAPER_RELOAD,
    SCRAPER_LOG_LEVEL
)


def main():
    print(f"============================================================")
    print(f"Starting Movie Scraper Service on {SCRAPER_HOST}:{SCRAPER_PORT}")
    print(f"Health Check: http://{SCRAPER_HOST if SCRAPER_HOST != '0.0.0.0' else 'localhost'}:{SCRAPER_PORT}/health")
    print(f"API Docs:     http://{SCRAPER_HOST if SCRAPER_HOST != '0.0.0.0' else 'localhost'}:{SCRAPER_PORT}/docs")
    print(f"Isolated from main API (Port 8000)")
    print(f"============================================================")
    print("Press Ctrl+C to stop the scraper service\n")

    uvicorn.run(
        "scraper_service.main:app",
        host=SCRAPER_HOST,
        port=SCRAPER_PORT,
        reload=SCRAPER_RELOAD,
        log_level=SCRAPER_LOG_LEVEL
    )


if __name__ == "__main__":
    main()
