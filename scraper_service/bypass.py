"""
Bypass and direct link resolution module for Downloadwella and file hosters.
Pure HTTP form emulation only — no Selenium/Chrome.
"""

import re
import logging
from typing import Tuple, Optional, Dict
import httpx
from bs4 import BeautifulSoup

from scraper_service.config import DEFAULT_USER_AGENT, SCRAPER_HTTP_TIMEOUT, is_safe_external_url

logger = logging.getLogger("scraper_service.bypass")


async def resolve_downloadwella_http(
    url: str, timeout: float = SCRAPER_HTTP_TIMEOUT
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Async HTTP bypass for Downloadwella.
    Emulates the XFS 'op=download2' form submission.
    Returns: (direct_url, file_name, file_size, error_message)
    """
    if not is_safe_external_url(url, {"downloadwella.com"}):
        return None, None, None, "URL must be an HTTPS Downloadwella URL"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": url,
        "Origin": "https://downloadwella.com",
    }

    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=5.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None, None, None, f"Failed to load download page: HTTP {resp.status_code}"

            soup = BeautifulSoup(resp.text, "html.parser")
            form = soup.find("form", attrs={"name": "F1"}) or soup.find(
                "form", action=lambda a: a is None or a == ""
            )
            if not form:
                direct_candidate = soup.find("a", href=lambda h: h and "/d/" in h)
                if direct_candidate:
                    return direct_candidate["href"], None, None, None
                return None, None, None, "Downloadwella form 'F1' not found on page"

            post_data: Dict[str, str] = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if name:
                    post_data[name] = inp.get("value", "")

            if "op" not in post_data:
                post_data["op"] = "download2"

            if not post_data.get("id"):
                id_match = re.search(r"downloadwella\.com/([a-zA-Z0-9]+)", url)
                if id_match:
                    post_data["id"] = id_match.group(1)

            post_url = form.get("action") or url
            if not post_url.startswith("http"):
                post_url = "https://downloadwella.com" + (
                    post_url if post_url.startswith("/") else f"/{post_url}"
                )
            if not is_safe_external_url(post_url, {"downloadwella.com"}):
                return None, None, None, "Download form action is not an approved URL"

            step2_resp = await client.post(post_url, data=post_data, headers=headers)
            if step2_resp.status_code != 200:
                return None, None, None, f"Download link generation failed: HTTP {step2_resp.status_code}"

            step2_soup = BeautifulSoup(step2_resp.text, "html.parser")

            direct_link_tag = step2_soup.find("a", href=lambda h: h and "/d/" in h)
            if not direct_link_tag:
                span = step2_soup.find(id="direct_link")
                if span:
                    parent_a = span.find_parent("a")
                    if parent_a and parent_a.get("href"):
                        direct_link_tag = parent_a

            if not direct_link_tag or not direct_link_tag.get("href"):
                return None, None, None, "Direct download link not generated in response"

            direct_url = direct_link_tag["href"]

            file_name = None
            file_size = None
            file_slot = step2_soup.find("table", class_="file_slot") or step2_soup.find(id="container")
            if file_slot:
                slot_text = file_slot.get_text(separator=" ", strip=True)
                fn_match = re.search(r"Filename:\s*([^\s\n\r]+)", slot_text)
                if fn_match:
                    file_name = fn_match.group(1).strip()
                size_match = re.search(
                    r"Size:\s*([\d\.]+\s*(?:MB|GB|KB))", slot_text, re.IGNORECASE
                )
                if size_match:
                    file_size = size_match.group(1).strip()

            return direct_url, file_name, file_size, None

    except httpx.TimeoutException:
        return None, None, None, "Downloadwella request timed out"
    except Exception as exc:
        logger.error("Error in resolve_downloadwella_http for %s: %s", url, exc)
        return None, None, None, f"HTTP resolver error: {str(exc)}"


async def resolve_download_link(
    url: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Resolve an intermediate Downloadwella (or similar) page to a direct CDN link.

    Pure HTTP only. No browser automation — keeps memory stable on constrained
    hosts (Render free/starter, small containers).
    """
    direct_url, file_name, file_size, err = await resolve_downloadwella_http(url)
    if direct_url:
        return direct_url, file_name, file_size, None
    return None, None, None, err or "HTTP bypass failed"
