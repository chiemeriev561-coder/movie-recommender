"""
HTTP client and parser for Thenkiri movie site.
Provides search_movies and get_download_options with robust error handling.
"""

import re
import asyncio
import time
import urllib.parse
import logging
from typing import List, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
except ImportError:  # Selenium is optional for local/dev environments.
    webdriver = None
    Options = None
    By = None

from scraper_service.config import (
    THENKIRI_BASE_URL,
    DEFAULT_USER_AGENT,
    SCRAPER_HTTP_TIMEOUT
)
from scraper_service.models import (
    SearchResultItem,
    SearchResponse,
    DownloadOptionItem,
    DownloadOptionsResponse,
    TVEpisodeItem,
    TVSeasonItem
)

logger = logging.getLogger("scraper_service.client")

# Common headers mimicking standard desktop browsers
HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": THENKIRI_BASE_URL,
}


def _extract_year(text: str, fallback_url: str = "") -> Optional[str]:
    """Extract release year (4 digits) from title or URL slug."""
    match = re.search(r"\((\d{4})\)", text)
    if match:
        return match.group(1)
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if match:
        return match.group(1)
    if fallback_url:
        match = re.search(r"-(\d{4})-", fallback_url)
        if match:
            return match.group(1)
    return None


def _clean_title(raw_title: str) -> str:
    """Clean up promotional suffixes from Thenkiri titles."""
    cleaned = re.sub(r"\|\s*Download\s+(?:Hollywood\s+)?Movie.*$", "", raw_title, flags=re.IGNORECASE)
    cleaned = re.sub(r"Download\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _infer_quality(url: str, text: str = "") -> str:
    """Infer video quality (1080p, 720p, 480p, 4K, etc.) from link or text."""
    combined = f"{url} {text}".lower()
    if "2160p" in combined or "4k" in combined:
        return "4K"
    if "1080p" in combined:
        return "1080p"
    if "720p" in combined:
        return "720p"
    if "480p" in combined:
        return "480p"
    if "webrip" in combined or "web-dl" in combined:
        return "720p (WEBRip)"
    if "hdrip" in combined:
        return "720p (HDRip)"
    return "Standard HD"


class ThenkiriClient:
    """Async scraper client for Thenkiri."""

    def __init__(self, base_url: str = THENKIRI_BASE_URL, timeout: float = SCRAPER_HTTP_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=httpx.Timeout(self.timeout, connect=6.0),
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search_movies(self, query: str, limit: int = 10) -> Tuple[List[SearchResultItem], Optional[str]]:
        """
        Search Thenkiri for movie query.
        Returns (list_of_results, error_message).
        """
        if not query or not query.strip():
            return [], "Query cannot be empty"

        search_url = f"{self.base_url}/?s={urllib.parse.quote(query.strip())}"
        client = await self.get_client()

        try:
            resp = await client.get(search_url)
            if resp.status_code != 200:
                logger.warning("Thenkiri search failed with HTTP status %d", resp.status_code)
                return [], f"Target site returned HTTP {resp.status_code}"
            
            soup = BeautifulSoup(resp.text, "html.parser")
            return self._parse_search_results(soup, limit), None

        except httpx.TimeoutException:
            logger.warning("Timeout searching Thenkiri for query '%s'", query)
            return [], "Target search site timed out"
        except Exception as exc:
            logger.error("Error searching Thenkiri for '%s': %s", query, exc)
            return [], f"Scraper error: {str(exc)}"

    def _parse_search_results(self, soup: BeautifulSoup, limit: int) -> List[SearchResultItem]:
        """Parse BeautifulSoup DOM of Thenkiri search results page."""
        results: List[SearchResultItem] = []

        # Find search result articles
        articles = soup.find_all("article")
        if not articles:
            # Fallback to search entries if article tags are absent
            articles = soup.find_all("div", class_=lambda c: c and ("search-entry" in c or "entry" in c))

        for art in articles:
            if len(results) >= limit:
                break

            # Find title and link
            title_tag = art.find(["h2", "h1", "h3"], class_=lambda c: c and "entry-title" in c)
            link_tag = None
            if title_tag:
                link_tag = title_tag.find("a")
            if not link_tag:
                link_tag = art.find("a", href=True)

            if not link_tag or not link_tag.get("href"):
                continue

            page_url = link_tag["href"]
            raw_title = link_tag.get_text(strip=True) or title_tag.get_text(strip=True) if title_tag else ""
            if not raw_title:
                continue

            # Year extraction
            year = _extract_year(raw_title, page_url)
            cleaned_title = _clean_title(raw_title)

            # Poster image extraction
            poster_url = None
            img_tag = art.find("img")
            if img_tag:
                poster_url = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("srcset", "").split()[0]

            results.append(SearchResultItem(
                title=cleaned_title,
                url=page_url,
                year=year,
                poster_url=poster_url,
                source="thenkiri"
            ))

        return results

    async def get_download_options(self, movie_url: str, title: Optional[str] = None) -> Tuple[List[DownloadOptionItem], Optional[str], Optional[str]]:
        """
        Extract download options from a Thenkiri movie detail page.
        Returns (list_of_options, extracted_title, error_message).
        """
        if not movie_url:
            return [], None, "Movie URL cannot be empty"

        client = await self.get_client()

        try:
            resp = await client.get(movie_url)
            if resp.status_code != 200:
                return [], None, f"Target page returned HTTP {resp.status_code}"

            soup = BeautifulSoup(resp.text, "html.parser")
            options, found_title = self._parse_download_page(soup, movie_url, title)
            return options, found_title, None

        except httpx.TimeoutException:
            return [], None, "Target movie page timed out"
        except Exception as exc:
            logger.error("Error extracting download options for '%s': %s", movie_url, exc)
            return [], None, f"Scraper error: {str(exc)}"

    def _parse_download_page(self, soup: BeautifulSoup, page_url: str, fallback_title: Optional[str] = None) -> Tuple[List[DownloadOptionItem], Optional[str]]:
        """Parse download buttons and file metadata from movie detail page."""
        options: List[DownloadOptionItem] = []

        # Extract movie title from h1 or title tag
        page_title = fallback_title
        h1 = soup.find("h1", class_=lambda c: c and "entry-title" in c)
        if h1:
            page_title = _clean_title(h1.get_text(strip=True))
        elif soup.title:
            page_title = _clean_title(soup.title.get_text(strip=True))

        # Extract file size if present (e.g. in .elementor-alert)
        file_size: Optional[str] = None
        alert = soup.find(class_=lambda c: c and "elementor-alert" in c)
        if alert:
            size_match = re.search(r"(\d+(?:\.\d+)?\s*(?:MB|GB))", alert.get_text(), re.IGNORECASE)
            if size_match:
                file_size = size_match.group(1).strip()

        # Find all download links (downloadwella or other hosters)
        seen_links = set()
        links = soup.find_all("a", href=True)

        for l in links:
            href = l["href"].strip()
            if not href or href in seen_links:
                continue

            # Check if this link points to a known file hoster
            is_hoster = any(host in href.lower() for host in ["downloadwella.com", "mega.nz", "drive.google.com"])
            # Or if it's an elementor download button
            btn_wrapper = l.find_parent(class_=lambda c: c and "elementor-button" in c) or ("elementor-button" in (l.get("class") or []))

            if is_hoster or (btn_wrapper and "download" in l.get_text().lower() and not href.endswith(("/how-to-download/", "/cant-download/"))):
                seen_links.add(href)
                quality = _infer_quality(href, l.get_text(strip=True))
                hoster = "downloadwella" if "downloadwella" in href.lower() else "external"

                options.append(DownloadOptionItem(
                    quality=quality,
                    download_url=href,
                    file_size=file_size,
                    hoster=hoster,
                    direct_url=None
                ))

        return options, page_title

    async def get_tv_options(self, url: str) -> Tuple[List[TVSeasonItem], Optional[str], Optional[str]]:
        """Extract all season and episode links from a Thenkiri TV-series page.

        Thenkiri keeps some seasons inside tabs/accordions which are not present
        in the initial HTTP response. Selenium renders the page and clicks those
        controls before parsing the resulting DOM.
        """
        if not url:
            return [], None, "TV-series URL cannot be empty"

        client = await self.get_client()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return [], None, f"Target page returned HTTP {resp.status_code}"

            html = resp.text
            if webdriver is not None:
                try:
                    html = await asyncio.to_thread(self._render_tv_page, url)
                except Exception as exc:
                    logger.warning(
                        "Selenium TV render failed for %s; using HTTP HTML: %s",
                        url,
                        exc,
                    )

            soup = BeautifulSoup(html, "html.parser")
            seasons, title = self._parse_tv_page(soup, url)
            return seasons, title, None
        except httpx.TimeoutException:
            return [], None, "Target TV-series page timed out"
        except Exception as exc:
            logger.error("Error extracting TV options for '%s': %s", url, exc)
            return [], None, f"Scraper error: {str(exc)}"

    @staticmethod
    def _render_tv_page(series_url: str) -> str:
        """Render a TV page and click controls that reveal hidden seasons."""
        if webdriver is None or Options is None or By is None:
            raise RuntimeError("Selenium is not installed")

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")

        driver = webdriver.Chrome(options=opts)
        try:
            driver.get(series_url)
            time.sleep(3)

            selectors = (
                "button",
                ".elementor-tab-title",
                ".wp-block-button__link",
                "a[href^='#season']",
            )
            clicked = set()
            for selector in selectors:
                for button in driver.find_elements(By.CSS_SELECTOR, selector):
                    text = button.text.strip().upper()
                    if "SEASON" not in text and "EPISODE" not in text:
                        continue
                    # Avoid clicking the same control repeatedly when it matches
                    # more than one selector.
                    marker = (text, button.get_attribute("outerHTML"))
                    if marker in clicked:
                        continue
                    clicked.add(marker)
                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});",
                            button,
                        )
                        time.sleep(0.2)
                        button.click()
                        time.sleep(0.5)
                    except Exception:
                        logger.debug("Could not click TV tab %r", text, exc_info=True)

            return driver.page_source
        finally:
            driver.quit()

    def _parse_tv_page(self, soup: BeautifulSoup, page_url: str) -> Tuple[List[TVSeasonItem], Optional[str]]:
        """Parse rendered TV markup into season groups and episode links."""
        title: Optional[str] = None
        h1 = soup.find("h1", class_=lambda c: c and "entry-title" in c)
        if h1:
            title = h1.get_text(" ", strip=True)
        elif soup.title:
            title = soup.title.get_text(" ", strip=True)

        seasons: List[TVSeasonItem] = []
        current: Optional[TVSeasonItem] = None
        seen_urls = set()

        for element in soup.find_all(["h2", "h3", "h4", "strong", "p", "a"]):
            text = element.get_text(" ", strip=True)
            text_lower = text.lower()

            if "season" in text_lower and len(text) < 80:
                season_name = element.get_text(" ", strip=True)
                if not season_name:
                    continue
                if current and current.season_name == season_name:
                    continue
                current = TVSeasonItem(season_name=season_name, episodes=[])
                seasons.append(current)
                continue

            if current is None:
                continue
            name = text
            href = element.get("href", "").strip()
            if element.name != "a" or "download" not in text_lower or not href:
                continue

            absolute_url = urllib.parse.urljoin(page_url, href)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)
            current.episodes.append(TVEpisodeItem(name=name, download_url=absolute_url))

        return [season for season in seasons if season.episodes], title
