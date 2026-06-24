"""
jobs/ats/lever.py — Lever ATS Public API Integration.
Falls back to HTML scraping if API fails or board slug cannot be resolved.
"""
from typing import List, Dict
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
}


def is_lever_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("jobs.lever.co") or host.endswith("lever.co")
    except Exception:
        return False


def _extract_company_slug(url: str) -> str:
    """Extract company from e.g. https://jobs.lever.co/vercel"""
    try:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return parts[0]
    except Exception:
        pass
    return ""


def extract_jobs_from_lever(careers_url: str, limit: int = 100) -> List[Dict]:
    if not is_lever_url(careers_url):
        return []

    company = _extract_company_slug(careers_url)
    if company:
        # Try Lever Public API: https://api.lever.co/v0/postings/{company}?mode=json
        api_url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json() or []
                jobs: List[Dict] = []
                for j in data:
                    title = (j.get("text") or "").strip()
                    apply_url = j.get("applyUrl") or j.get("hostedUrl") or ""
                    external_id = str(j.get("id"))
                    
                    cats = j.get("categories") or {}
                    location_text = cats.get("location") or "Remote"
                    commitment = cats.get("commitment") or ""
                    
                    desc = j.get("descriptionHtml") or j.get("description") or ""
                    # append lists (requirements, lists etc)
                    lists_text = ""
                    for lst in (j.get("lists") or []):
                        lists_text += f"\n\n### {lst.get('text')}\n{lst.get('content')}"
                    
                    jobs.append({
                        "title": title,
                        "apply_url": apply_url,
                        "external_id": external_id,
                        "location_text": location_text,
                        "description": f"{desc}{lists_text}",
                        "work_type": commitment,
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
        jobs: List[Dict] = []
        for a in soup.select("a[href*='/jobs/']"):
            title = (a.get_text() or "").strip()
            href = a.get("href")
            if not title or not href:
                continue
            jobs.append({
                "title": title,
                "apply_url": urljoin(careers_url, href),
                "external_id": None,
                "location_text": "Remote",
            })
            if len(jobs) >= limit:
                break
        return jobs
    except Exception:
        return []
