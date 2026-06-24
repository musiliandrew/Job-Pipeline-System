"""
jobs/ats/ashby.py — Ashby ATS Public API Integration.
"""
from typing import List, Dict
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
}


def is_ashby_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("jobs.ashbyhq.com") or host.endswith("ashbyhq.com")
    except Exception:
        return False


def _extract_board_id(url: str) -> str:
    """Extract board_id from e.g. https://jobs.ashbyhq.com/vercel"""
    try:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return parts[0]
    except Exception:
        pass
    return ""


def extract_jobs_from_ashby(careers_url: str, limit: int = 100) -> List[Dict]:
    if not is_ashby_url(careers_url):
        return []

    board_id = _extract_board_id(careers_url)
    if board_id:
        # Ashby Public Board API: https://api.ashbyhq.com/posting-api/job-board/{board_id}
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_id}"
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json() or {}
                jobs: List[Dict] = []
                for j in data.get("jobs", []):
                    title = (j.get("title") or "").strip()
                    apply_url = j.get("jobUrl") or ""
                    external_id = str(j.get("id"))
                    
                    location_text = j.get("location") or "Remote"
                    employment_type = j.get("employmentType") or ""
                    
                    # Ashby API typically doesn't return full description in the summary board endpoint,
                    # but it is a fast API listing.
                    jobs.append({
                        "title": title,
                        "apply_url": apply_url,
                        "external_id": external_id,
                        "location_text": location_text,
                        "work_type": employment_type,
                        "description": f"Department: {j.get('department') or 'Various'}",
                    })
                    if len(jobs) >= limit:
                        break
                if jobs:
                    return jobs
        except Exception:
            pass

    # Fallback: HTML scraping of Ashby job board page
    try:
        resp = requests.get(careers_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs: List[Dict] = []
        # Ashby renders links with e.g. href="/board_id/job_id" or absolute
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = (a.get_text() or "").strip()
            if not title or len(title) < 5 or not board_id in href:
                continue
            apply_url = urljoin(careers_url, href)
            jobs.append({
                "title": title,
                "apply_url": apply_url,
                "external_id": None,
                "location_text": "Remote",
            })
            if len(jobs) >= limit:
                break
        return jobs
    except Exception:
        return []
