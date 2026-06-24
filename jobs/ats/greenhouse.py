"""
jobs/ats/greenhouse.py — Greenhouse ATS Public API Integration.
Falls back to HTML scraping if API fails or board slug cannot be resolved.
"""
from typing import List, Dict
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
}


def is_greenhouse_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("boards.greenhouse.io") or host.endswith("greenhouse.io")
    except Exception:
        return False


def _extract_board_slug(url: str) -> str:
    """Extract slug from e.g. https://boards.greenhouse.io/stripe or https://boards.greenhouse.io/embed/job_board?board=stripe"""
    try:
        parsed = urlparse(url)
        # Handle query parameter first (embedded board)
        from urllib.parse import parse_qs
        qs = parse_qs(parsed.query)
        if "board" in qs:
            return qs["board"][0]
        # Otherwise path is /slug or /embed/job_board/slug
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            if parts[0] == "embed" and len(parts) > 1:
                return parts[-1]
            return parts[0]
    except Exception:
        pass
    return ""


def extract_jobs_from_greenhouse(careers_url: str, limit: int = 100) -> List[Dict]:
    if not is_greenhouse_url(careers_url):
        return []

    slug = _extract_board_slug(careers_url)
    if slug:
        # Try Greenhouse Boards API first
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json() or {}
                jobs: List[Dict] = []
                for j in data.get("jobs", []):
                    title = (j.get("title") or "").strip()
                    apply_url = j.get("absolute_url") or ""
                    external_id = str(j.get("id"))
                    
                    loc = j.get("location") or {}
                    location_text = loc.get("name") or "Remote"
                    
                    jobs.append({
                        "title": title,
                        "apply_url": apply_url,
                        "external_id": external_id,
                        "location_text": location_text,
                        "description": j.get("content") or "", # api returns full HTML content
                    })
                    if len(jobs) >= limit:
                        break
                if jobs:
                    return jobs
        except Exception:
            pass

    # Fallback: HTML scraping
    try:
        resp = requests.get(careers_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []
        for a in soup.select("a[href*='/jobs/']"):
            title = (a.get_text() or "").strip()
            href = a.get("href")
            if not title or not href:
                continue
            apply_url = urljoin(careers_url, href) if href.startswith("/") else href
            
            # Try to get id from href
            # e.g. /jobs/123456
            external_id = None
            import re
            m = re.search(r"jobs/(\d+)", href)
            if m:
                external_id = m.group(1)
                
            jobs.append({
                "title": title,
                "apply_url": apply_url,
                "external_id": external_id,
                "location_text": "Remote",
            })
            if len(jobs) >= limit:
                break
        return jobs
    except Exception:
        return []
