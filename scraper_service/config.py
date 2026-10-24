"""
Configuration settings for Scraper Service.
"""

import os
import ipaddress
from urllib.parse import urlparse
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


def is_safe_external_url(value: str, allowed_hosts: set[str]) -> bool:
    """Allow only HTTPS URLs on explicitly approved public hostnames."""
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return False
        try:
            if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback:
                return False
        except ValueError:
            pass
        return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)
    except ValueError:
        return False
