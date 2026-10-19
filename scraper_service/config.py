"""
Configuration settings for Scraper Service.
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

SCRAPER_HOST: str = os.getenv("SCRAPER_HOST", "0.0.0.0")
SCRAPER_PORT: int = int(os.getenv("SCRAPER_PORT", "8001"))
SCRAPER_RELOAD: bool = os.getenv("SCRAPER_RELOAD", "false").lower() == "true"
SCRAPER_LOG_LEVEL: str = os.getenv("SCRAPER_LOG_LEVEL", "info").lower()

# Request timeouts
SCRAPER_HTTP_TIMEOUT: float = float(os.getenv("SCRAPER_HTTP_TIMEOUT", "15.0"))
SCRAPER_MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))

# Target site configurations (configurable via environment variables)
THENKIRI_BASE_URL: str = os.getenv("THENKIRI_BASE_URL", "https://thenkiri.com").rstrip("/")
DOWNLOADWELLA_BASE_URL: str = os.getenv("DOWNLOADWELLA_BASE_URL", "https://downloadwella.com").rstrip("/")

# Default desktop browser user agent for scraper
DEFAULT_USER_AGENT: str = os.getenv(
    "SCRAPER_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# CORS
ALLOWED_ORIGINS: List[str] = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if origin.strip()
]
