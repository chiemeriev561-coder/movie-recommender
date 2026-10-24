"""
HTTP client and parser for Thenkiri movie site.
Provides search_movies and get_download_options with robust error handling.
Pure httpx + BeautifulSoup only — no Selenium/Chrome (avoids OOM on Render).
"""

import re
import asyncio
import urllib.parse
import logging
from typing import List, Optional, Tuple, Dict
import httpx
from bs4 import BeautifulSoup

from scraper_service.config import (
    THENKIRI_BASE_URL,
    DEFAULT_USER_AGENT,
    SCRAPER_HTTP_TIMEOUT,
    is_safe_external_url,
)
from scraper_service.models import (
    SearchResultItem,
    DownloadOptionItem,
    TVEpisodeItem,
    TVSeasonItem
)

logger = logging.getLogger("scraper_service.client")

HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": THENKIRI_BASE_URL,
}

# Cap related season fetches so we stay within memory/time on small hosts
MAX_RELATED_SEASON_PAGES = 12
RELATED_FETCH_CONCURRENCY = 3


def _extract_year(text: str, fallback_url: str = "") -> Optional[str]:
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
    cleaned = re.sub(r"\|\s*Download\s+(?:Hollywood\s+)?Movie.*$", "", raw_title, flags=re.IGNORECASE)
    cleaned = re.sub(r"Download\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _infer_quality(url: str, text: str = "") -> str:
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


def _episode_label_from_context(anchor, href: str) -> str:
    p = anchor
    for _ in range(6):
        p = getattr(p, "parent", None)
        if p is None or not hasattr(p, "get_text"):
            break
        pt = p.get_text(" ", strip=True)
        m = re.search(r"(Episode\s+\d+(?:\s*\([^)]+\))?)", pt, re.IGNORECASE)
        if m:
            return m.group(1)
    m = re.search(r"[Ss](\d+)[Ee](\d+)", href)
    if m:
        return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}"
    text = anchor.get_text(" ", strip=True)
    return text if text else "Download Episode"


def _normalize_series_base(title: str) -> str:
    """
    'The Vampire Diaries S01 (Complete) | TV Series' -> 'the vampire diaries'
    Used to match related season posts.
    """
    t = title or ""
    t = re.sub(r"(?i)^download\s+", "", t)
    t = re.sub(r"\s*\|\s*.*$", "", t)
    t = re.sub(r"\s*\([^)]*\)", " ", t)
    t = re.sub(r"(?i)\bS(?:eason)?\s*\d+\b", " ", t)
    t = re.sub(r"(?i)\band\b", " ", t)
    t = re.sub(r"(?i)\b(?:tv\s*series|complete|hollywood|series)\b", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _season_numbers_from_text(text: str) -> List[int]:
    nums = []
    for m in re.finditer(r"(?i)\bS(?:eason)?\s*(\d+)\b", text or ""):
        n = int(m.group(1))
        if n not in nums:
            nums.append(n)
    return nums


def _season_sort_key(name: str) -> Tuple[int, str]:
    m = re.search(r"(?i)season\s*(\d+)", name or "")
    if m:
        return (int(m.group(1)), name.lower())
    m = re.search(r"(?i)\bS(\d+)\b", name or "")
    if m:
        return (int(m.group(1)), name.lower())
    return (9999, (name or "").lower())


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
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search_movies(self, query: str, limit: int = 10) -> Tuple[List[SearchResultItem], Optional[str]]:
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
        results: List[SearchResultItem] = []

        articles = soup.find_all("article")
        if not articles:
            articles = soup.find_all("div", class_=lambda c: c and ("search-entry" in c or "entry" in c))

        for art in articles:
            if len(results) >= limit:
                break

            title_tag = art.find(["h2", "h1", "h3"], class_=lambda c: c and "entry-title" in c)
            link_tag = None
            if title_tag:
                link_tag = title_tag.find("a")
            if not link_tag:
                link_tag = art.find("a", href=True)

            if not link_tag or not link_tag.get("href"):
                continue

            page_url = link_tag["href"]
            raw_title = link_tag.get_text(strip=True) or (title_tag.get_text(strip=True) if title_tag else "")
            if not raw_title:
                continue

            year = _extract_year(raw_title, page_url)
            cleaned_title = _clean_title(raw_title)

            poster_url = None
            img_tag = art.find("img")
            if img_tag:
                poster_url = img_tag.get("src") or img_tag.get("data-src") or (
                    img_tag.get("srcset", "").split()[0] if img_tag.get("srcset") else None
                )

            results.append(SearchResultItem(
                title=cleaned_title,
                url=page_url,
                year=year,
                poster_url=poster_url,
                source="thenkiri"
            ))

        return results

    async def get_download_options(
        self, movie_url: str, title: Optional[str] = None
    ) -> Tuple[List[DownloadOptionItem], Optional[str], Optional[str]]:
        if not movie_url:
            return [], None, "Movie URL cannot be empty"
        if not is_safe_external_url(movie_url, {"thenkiri.com"}):
            return [], None, "Movie URL must be an HTTPS Thenkiri URL"

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

    def _parse_download_page(
        self, soup: BeautifulSoup, page_url: str, fallback_title: Optional[str] = None
    ) -> Tuple[List[DownloadOptionItem], Optional[str]]:
        options: List[DownloadOptionItem] = []

        page_title = fallback_title
        h1 = soup.find("h1", class_=lambda c: c and "entry-title" in c)
        if h1:
            page_title = _clean_title(h1.get_text(strip=True))
        elif soup.title:
            page_title = _clean_title(soup.title.get_text(strip=True))

        file_size: Optional[str] = None
        alert = soup.find(class_=lambda c: c and "elementor-alert" in c)
        if alert:
            size_match = re.search(r"(\d+(?:\.\d+)?\s*(?:MB|GB))", alert.get_text(), re.IGNORECASE)
            if size_match:
                file_size = size_match.group(1).strip()

        seen_links = set()
        links = soup.find_all("a", href=True)

        for l in links:
            href = l["href"].strip()
            if not href or href in seen_links:
                continue

            is_hoster = any(host in href.lower() for host in ["downloadwella.com", "mega.nz", "drive.google.com"])
            btn_wrapper = l.find_parent(class_=lambda c: c and "elementor-button" in c) or (
                "elementor-button" in (l.get("class") or [])
            )

            if is_hoster or (
                btn_wrapper
                and "download" in l.get_text().lower()
                and not href.endswith(("/how-to-download/", "/cant-download/"))
            ):
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
        """
        Extract seasons/episodes for a Thenkiri TV page.

        1) Parse the requested page (may already contain multiple seasons).
        2) If Thenkiri split the show across separate posts (S01, S02, ...),
           search for sibling season pages and merge them.
        """
        if not url:
            return [], None, "TV-series URL cannot be empty"
        if not is_safe_external_url(url, {"thenkiri.com"}):
            return [], None, "TV URL must be an HTTPS Thenkiri URL"

        logger.info("Fetching TV download options (pure HTTP): %s", url)
        client = await self.get_client()

        try:
            resp = await client.get(url, headers={**HEADERS, "Referer": THENKIRI_BASE_URL + "/"})
            if resp.status_code != 200:
                return [], None, f"Target page returned HTTP {resp.status_code}"

            soup = BeautifulSoup(resp.text, "html.parser")
            seasons, title = self._parse_tv_page(soup, url)

            if title:
                seasons = await self._merge_related_season_pages(
                    primary_url=url,
                    primary_title=title,
                    primary_seasons=seasons,
                )

            seasons = sorted(seasons, key=lambda s: _season_sort_key(s.season_name))
            logger.info("Found %d seasons with episodes for %s", len(seasons), url)
            return seasons, title, None

        except httpx.TimeoutException:
            return [], None, "Target TV-series page timed out"
        except Exception as exc:
            logger.error("Error extracting TV options for '%s': %s", url, exc)
            return [], None, f"Scraper error: {str(exc)}"

    async def _merge_related_season_pages(
        self,
        primary_url: str,
        primary_title: str,
        primary_seasons: List[TVSeasonItem],
    ) -> List[TVSeasonItem]:
        """
        Discover other Thenkiri posts for the same series and merge their seasons.

        Example: opening Vampire Diaries S01 should also pull S02–S08 pages.
        """
        base = _normalize_series_base(primary_title)
        if not base or len(base) < 3:
            return primary_seasons

        primary_season_nums = _season_numbers_from_text(primary_title)
        page_has_multi = len(primary_seasons) > 1
        if page_has_multi and len(primary_season_nums) > 1:
            return primary_seasons

        results, err = await self.search_movies(base, limit=30)
        if err or not results:
            logger.info("No related season posts found for base=%r (%s)", base, err)
            return primary_seasons

        primary_norm = primary_url.rstrip("/").lower()
        related: List[Tuple[str, str, List[int]]] = []
        for item in results:
            item_base = _normalize_series_base(item.title)
            if not self._bases_match(base, item_base):
                continue
            item_url = (item.url or "").rstrip("/")
            if item_url.lower() == primary_norm:
                continue
            nums = _season_numbers_from_text(item.title) or _season_numbers_from_text(item_url)
            if not nums:
                continue
            related.append((item.url, item.title, nums))

        if not related:
            return primary_seasons

        seen_urls = {primary_norm}
        to_fetch: List[Tuple[str, str, List[int]]] = []
        for u, t, nums in related:
            key = u.rstrip("/").lower()
            if key in seen_urls:
                continue
            seen_urls.add(key)
            to_fetch.append((u, t, nums))
            if len(to_fetch) >= MAX_RELATED_SEASON_PAGES:
                break

        logger.info("Aggregating %d related season pages for %r", len(to_fetch), base)

        sem = asyncio.Semaphore(RELATED_FETCH_CONCURRENCY)

        async def fetch_one(page_url: str, page_title: str, nums: List[int]) -> List[TVSeasonItem]:
            async with sem:
                try:
                    client = await self.get_client()
                    resp = await client.get(
                        page_url,
                        headers={**HEADERS, "Referer": THENKIRI_BASE_URL + "/"},
                    )
                    if resp.status_code != 200:
                        return []
                    soup = BeautifulSoup(resp.text, "html.parser")
                    seasons, _ = self._parse_tv_page(soup, page_url)
                    if len(seasons) == 1 and nums:
                        seasons[0] = TVSeasonItem(
                            season_name=f"Season {nums[0]}",
                            episodes=seasons[0].episodes,
                        )
                    return seasons
                except Exception as exc:
                    logger.warning("Failed related season page %s: %s", page_url, exc)
                    return []

        fetched_lists = await asyncio.gather(
            *[fetch_one(u, t, n) for u, t, n in to_fetch]
        )

        merged: Dict[str, TVSeasonItem] = {}

        def add_season(s: TVSeasonItem) -> None:
            key = s.season_name.strip().lower()
            m = re.match(r"(?i)season\s*0*(\d+)$", key)
            if m:
                key = f"season {int(m.group(1))}"
                s = TVSeasonItem(season_name=f"Season {int(m.group(1))}", episodes=s.episodes)
            if key not in merged:
                merged[key] = s
            else:
                existing = merged[key]
                if len(s.episodes) > len(existing.episodes):
                    merged[key] = s

        for s in primary_seasons:
            if len(primary_seasons) == 1 and primary_season_nums:
                add_season(TVSeasonItem(
                    season_name=f"Season {primary_season_nums[0]}",
                    episodes=s.episodes,
                ))
            else:
                add_season(s)

        for season_list in fetched_lists:
            for s in season_list:
                add_season(s)

        return list(merged.values())

    @staticmethod
    def _bases_match(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b:
            return True
        ta = set(a.split())
        tb = set(b.split())
        if not ta or not tb:
            return False
        smaller, larger = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        overlap = len(smaller & larger) / len(smaller)
        return overlap >= 0.8

    def _parse_tv_page(self, soup: BeautifulSoup, page_url: str) -> Tuple[List[TVSeasonItem], Optional[str]]:
        title: Optional[str] = None
        h1 = soup.find("h1", class_=lambda c: c and "entry-title" in c)
        if h1:
            title = h1.get_text(" ", strip=True)
        elif soup.title:
            title = soup.title.get_text(" ", strip=True)

        seasons: List[TVSeasonItem] = []
        current: Optional[TVSeasonItem] = None
        seen_urls: set = set()

        for element in soup.find_all(["h2", "h3", "h4", "a"]):
            text = element.get_text(" ", strip=True)
            text_upper = text.upper().strip()

            if element.name in ("h2", "h3", "h4"):
                if re.match(r"^SEASON\s*\d+", text_upper) and len(text) < 40:
                    if current and current.season_name == text:
                        continue
                    current = TVSeasonItem(season_name=text, episodes=[])
                    seasons.append(current)
                continue

            if current is None:
                continue

            href = (element.get("href") or "").strip()
            if not href or "downloadwella.com" not in href.lower():
                continue

            absolute_url = urllib.parse.urljoin(page_url, href)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)

            ep_name = _episode_label_from_context(element, href)
            current.episodes.append(TVEpisodeItem(name=ep_name, download_url=absolute_url))

        if not seasons or all(not s.episodes for s in seasons):
            all_episodes: List[TVEpisodeItem] = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "downloadwella.com" not in href.lower():
                    continue
                absolute_url = urllib.parse.urljoin(page_url, href)
                if absolute_url in seen_urls:
                    continue
                seen_urls.add(absolute_url)
                all_episodes.append(
                    TVEpisodeItem(
                        name=_episode_label_from_context(a, href),
                        download_url=absolute_url,
                    )
                )
            if all_episodes:
                nums = _season_numbers_from_text(title or "") or _season_numbers_from_text(page_url)
                season_name = f"Season {nums[0]}" if nums else "All Episodes"
                seasons = [TVSeasonItem(season_name=season_name, episodes=all_episodes)]

        return [s for s in seasons if s.episodes], title
