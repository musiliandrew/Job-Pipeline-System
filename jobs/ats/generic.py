"""
jobs/ats/generic.py — Generic HTML scraper for career pages that aren't Workday/Greenhouse/Lever.
Uses BeautifulSoup to find <a> tags with job-like URLs.
"""
from typing import List, Dict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
}

JOB_URL_HINTS = (
    "job", "jobs", "career", "careers", "opening", "openings",
    "position", "positions", "vacancy", "vacancies", "hire", "hiring",
)


def _is_job_link(href: str, text: str) -> bool:
    h = (href or "").lower()
    t = (text or "").lower()
    return any(k in h or k in t for k in JOB_URL_HINTS)


def extract_jobs_from_generic(careers_url: str, limit: int = 50) -> List[Dict]:
    try:
        resp = requests.get(careers_url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code not in (200, 403):
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        base_host = (urlparse(careers_url).netloc or "").lower()
        jobs: List[Dict] = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = (a.get_text() or "").strip()
            if not text or len(text) < 4 or len(text) > 200:
                continue
            if not _is_job_link(href, text):
                continue
            apply_url = urljoin(careers_url, href) if href.startswith("/") else href
            link_host = (urlparse(apply_url).netloc or "").lower()
            # Allow same-domain or known ATS hosts
            if link_host and link_host != base_host and not any(
                k in link_host for k in ("greenhouse", "lever", "workday", "smartrecruiters", "jobvite", "icims")
            ):
                continue
            jobs.append({"title": text, "apply_url": apply_url, "external_id": None})
            if len(jobs) >= limit:
                break
        return jobs
    except Exception:
        return []
