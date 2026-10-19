"""
Bypass and direct link resolution module for Downloadwella and file hosters.
Provides high-speed HTTP form emulation with a Selenium headless browser fallback.
"""

import re
import time
import logging
from typing import Tuple, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup

from scraper_service.config import DEFAULT_USER_AGENT, SCRAPER_HTTP_TIMEOUT

logger = logging.getLogger("scraper_service.bypass")


async def resolve_downloadwella_http(url: str, timeout: float = SCRAPER_HTTP_TIMEOUT) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Fast-path async HTTP bypass for Downloadwella.
    Emulates the XFS 'op=download2' form submission.
    Returns: (direct_url, file_name, file_size, error_message)
    """
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": url,
        "Origin": "https://downloadwella.com",
    }

    try:
        async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout, connect=5.0), follow_redirects=True) as client:
            # Step 1: Fetch initial page to extract form hidden fields & file ID
            resp = await client.get(url)
            if resp.status_code != 200:
                return None, None, None, f"Failed to load download page: HTTP {resp.status_code}"

            soup = BeautifulSoup(resp.text, "html.parser")
            form = soup.find("form", attrs={"name": "F1"}) or soup.find("form", action=lambda a: a is None or a == "")
            if not form:
                # If form is missing, maybe it's already a direct link or different structure
                direct_candidate = soup.find("a", href=lambda h: h and "/d/" in h)
                if direct_candidate:
                    return direct_candidate["href"], None, None, None
                return None, None, None, "Downloadwella form 'F1' not found on page"

            # Extract inputs
            post_data: Dict[str, str] = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if name:
                    post_data[name] = inp.get("value", "")

            # Ensure required XFS fields exist
            if "op" not in post_data:
                post_data["op"] = "download2"
            
            # Extract file ID from URL if missing
            if not post_data.get("id"):
                id_match = re.search(r"downloadwella\.com/([a-zA-Z0-9]+)", url)
                if id_match:
                    post_data["id"] = id_match.group(1)

            # Step 2: Post the form to trigger direct link generation
            post_url = form.get("action") or url
            if not post_url.startswith("http"):
                post_url = "https://downloadwella.com" + (post_url if post_url.startswith("/") else f"/{post_url}")

            step2_resp = await client.post(post_url, data=post_data, headers=headers)
            if step2_resp.status_code != 200:
                return None, None, None, f"Download link generation failed: HTTP {step2_resp.status_code}"

            step2_soup = BeautifulSoup(step2_resp.text, "html.parser")

            # Step 3: Extract direct link
            # Downloadwella direct links use pattern https://{server}.downloadwella.com/d/{token}/{filename}
            direct_link_tag = step2_soup.find("a", href=lambda h: h and "/d/" in h)
            if not direct_link_tag:
                # Look for span#direct_link or button
                span = step2_soup.find(id="direct_link")
                if span:
                    parent_a = span.find_parent("a")
                    if parent_a and parent_a.get("href"):
                        direct_link_tag = parent_a

            if not direct_link_tag or not direct_link_tag.get("href"):
                return None, None, None, "Direct download link not generated in response"

            direct_url = direct_link_tag["href"]

            # Extract filename and size
            file_name = None
            file_size = None
            file_slot = step2_soup.find("table", class_="file_slot") or step2_soup.find(id="container")
            if file_slot:
                slot_text = file_slot.get_text(separator=" ", strip=True)
                fn_match = re.search(r"Filename:\s*([^\s\n\r]+)", slot_text)
                if fn_match:
                    file_name = fn_match.group(1).strip()
                size_match = re.search(r"Size:\s*([\d\.]+\s*(?:MB|GB|KB))", slot_text, re.IGNORECASE)
                if size_match:
                    file_size = size_match.group(1).strip()

            return direct_url, file_name, file_size, None

    except httpx.TimeoutException:
        return None, None, None, "Downloadwella request timed out"
    except Exception as exc:
        logger.error("Error in resolve_downloadwella_http for %s: %s", url, exc)
        return None, None, None, f"HTTP resolver error: {str(exc)}"


def resolve_downloadwella_selenium(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Selenium headless browser bypass for Downloadwella when JavaScript execution
    or Cloudflare challenges are required.
    Returns: (direct_url, file_name, file_size, error_message)
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        return None, None, None, "Selenium is not installed"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(timeout)
        driver.get(url)

        # Locate and click download button
        btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.ID, "downloadbtn"))
        )
        btn.click()

        # Wait for direct link on step 2 page
        link_elem = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/d/')]"))
        )
        direct_url = link_elem.get_attribute("href")

        return direct_url, None, None, None

    except Exception as exc:
        logger.warning("Selenium bypass attempt failed: %s", exc)
        return None, None, None, f"Selenium bypass error: {str(exc)}"
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


async def resolve_download_link(url: str, force_selenium: bool = False) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Main bypass entry point.
    Tries fast HTTP bypass first; if it fails or if force_selenium is requested,
    attempts Selenium headless bypass.
    """
    if not force_selenium:
        direct_url, file_name, file_size, err = await resolve_downloadwella_http(url)
        if direct_url:
            return direct_url, file_name, file_size, None
        logger.info("Fast HTTP bypass failed (%s), attempting Selenium fallback...", err)

    # Fallback to Selenium
    import asyncio
    direct_url, file_name, file_size, sel_err = await asyncio.to_thread(resolve_downloadwella_selenium, url)
    if direct_url:
        return direct_url, file_name, file_size, None

    return None, None, None, f"Both bypass methods failed: HTTP err=({err if not force_selenium else 'skipped'}), Selenium err=({sel_err})"
