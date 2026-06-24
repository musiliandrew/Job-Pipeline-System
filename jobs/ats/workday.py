"""jobs/ats/workday.py — Ported from DataIngestion/Jobs/workday.py"""
import re
from typing import List, Dict
from urllib.parse import urljoin, urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
}


def is_workday_url(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "").endswith(".wd1.myworkdayjobs.com")
    except Exception:
        return False


def extract_jobs_from_workday(careers_url: str, limit: int = 50) -> List[Dict]:
    if not is_workday_url(careers_url):
        return []
    jobs = _extract_workday_cxs(careers_url, limit)
    if jobs:
        return jobs
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(careers_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        out: List[Dict] = []
        for a in soup.find_all("a", href=True):
            text = (a.get_text() or "").strip()
            href = a["href"]
            if not text or not href:
                continue
            if "/job/" in href or href.startswith("/en/") or href.startswith("/en-US/"):
                apply_url  = urljoin(careers_url, href)
                m          = re.search(r"job/(\d+)", href)
                external_id = m.group(1) if m else None
                out.append({"title": text, "apply_url": apply_url, "external_id": external_id})
                if len(out) >= limit:
                    break
        return out
    except Exception:
        return []


def _extract_workday_cxs(careers_url: str, limit: int) -> List[Dict]:
    try:
        parsed = urlparse(careers_url)
        host   = parsed.hostname or ""
        if ".wd1.myworkdayjobs.com" not in host:
            return []
        tenant = host.split(".")[0]
        path_parts = [p for p in (parsed.path or "").split("/") if p]
        site = "External"
        for p in path_parts:
            if p.lower().startswith("external"):
                site = p
                break
        api = f"https://{tenant}.wd1.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
        h   = {
            "Accept":       "application/json",
            "Content-Type": "application/json",
            "Origin":   f"https://{tenant}.wd1.myworkdayjobs.com",
            "Referer":  f"https://{tenant}.wd1.myworkdayjobs.com/en/{site}",
            **HEADERS,
        }
        payload = {"limit": int(limit), "offset": 0, "searchText": ""}
        r = requests.post(api, json=payload, headers=h, timeout=15)
        if r.status_code != 200:
            r = requests.get(api, headers=h, params={"limit": str(limit)}, timeout=15)
            if r.status_code != 200:
                return []
        out: List[Dict] = []
        for j in r.json().get("jobPostings", [])[:limit]:
            title    = (j.get("title") or "").strip()
            ext_path = j.get("externalPath") or j.get("externalJobLink")
            if not title or not ext_path:
                continue
            apply_url   = urljoin(careers_url, ext_path)
            external_id = None
            for b in (j.get("bulletFields") or []):
                m = re.search(r"\b([A-Z]{2}\d{5,}|\d{5,})\b", b)
                if m:
                    external_id = m.group(1)
                    break
            out.append({"title": title, "apply_url": apply_url, "external_id": external_id})
        return out
    except Exception:
        return []
