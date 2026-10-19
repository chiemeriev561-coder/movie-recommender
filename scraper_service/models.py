"""
Pydantic schemas for Scraper Service endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Service health status")
    service: str = Field("scraper-service", description="Service name")
    version: str = Field("1.0.0", description="Service version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    port: int = Field(8001, description="Listening port")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Movie title or keywords to search for")
    limit: Optional[int] = Field(10, ge=1, le=50, description="Max search results to return")
    source: Optional[str] = Field("thenkiri", description="Target provider (e.g., thenkiri)")


class SearchResultItem(BaseModel):
    title: str = Field(..., description="Movie title found")
    url: str = Field(..., description="URL of movie page on target site")
    year: Optional[str] = Field(None, description="Release year if available")
    poster_url: Optional[str] = Field(None, description="Poster image URL")
    source: str = Field("thenkiri", description="Source provider name")


class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResultItem]
    duration_ms: float
    error: Optional[str] = None


class DownloadOptionsRequest(BaseModel):
    url: str = Field(..., description="Target movie page URL to extract download options from")
    title: Optional[str] = Field(None, description="Movie title if known")


class DownloadOptionItem(BaseModel):
    quality: str = Field(..., description="Resolution quality (e.g. 720p, 1080p, 480p)")
    download_url: str = Field(..., description="URL pointing to file hoster or intermediate page")
    file_size: Optional[str] = Field(None, description="Human readable file size (e.g. 1.2 GB)")
    hoster: Optional[str] = Field("downloadwella", description="Name of the download hosting provider")
    direct_url: Optional[str] = Field(None, description="Direct download link if resolved")


class DownloadOptionsResponse(BaseModel):
    url: str
    title: Optional[str] = None
    options: List[DownloadOptionItem]
    duration_ms: float
    error: Optional[str] = None


class BypassRequest(BaseModel):
    url: str = Field(..., description="Target intermediate download page URL to bypass")


class BypassResponse(BaseModel):
    original_url: str
    direct_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[str] = None
    status: str = Field("pending", description="Bypass status: 'resolved', 'failed', 'pending'")
    duration_ms: float
    error: Optional[str] = None


class ScraperStatsResponse(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_duration_ms: float
    uptime_seconds: float
