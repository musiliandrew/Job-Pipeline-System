"""jobs/providers/reddit.py — Ported from DataIngestion/Jobs/providers/reddit.py"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from common.http import polite_delay
from jobs.filters import reddit_is_job_listing, extract_skills, detect_work_type, is_relevant_role

NAME          = "reddit"
DEFAULT_SUBS  = os.getenv("REDDIT_SUBREDDITS", "forhire,remotejobs,cscareerquestionsjobs").split(",")
OAUTH_URL     = "https://www.reddit.com/api/v1/access_token"
BASE_OAUTH_API = "https://oauth.reddit.com"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_token() -> str:
    cid  = os.getenv("REDDIT_CLIENT_ID")
    csec = os.getenv("REDDIT_CLIENT_SECRET")
    if not cid or not csec:
        return ""
    auth    = requests.auth.HTTPBasicAuth(cid, csec)
    headers = {"User-Agent": "careerscoper/0.1"}
    try:
        r = requests.post(OAUTH_URL, auth=auth, data={"grant_type": "client_credentials"},
                          headers=headers, timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token", "")
    except Exception:
        return ""
    return ""


def _fetch_sub(sub: str, token: str, limit: int) -> List[Dict[str, Any]]:
    if not token:
        return []
    headers = {"Authorization": f"bearer {token}", "User-Agent": "careerscoper/0.1"}
    url     = f"{BASE_OAUTH_API}/r/{sub}/new.json"
    try:
        r = requests.get(url, headers=headers, params={"limit": min(limit, 50)}, timeout=20)
        if r.status_code != 200:
            return []
        children = (((r.json() or {}).get("data") or {}).get("children")) or []
        out: List[Dict[str, Any]] = []
        for ch in children:
            d    = (ch or {}).get("data") or {}
            title = (d.get("title") or "").strip()
            body  = (d.get("selftext") or "").strip()
            link  = d.get("url_overridden_by_dest") or d.get("url") or ""
            pid   = d.get("id") or d.get("name") or link or title
            created_utc = d.get("created_utc")
            posted_at   = _now()
            if isinstance(created_utc, (int, float)):
                try:
                    posted_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                except Exception:
                    posted_at = _now()
            if not reddit_is_job_listing(title, body):
                continue
            text = f"{title}\n{body}"
            pre: Dict[str, Any] = {
                "title":         title,
                "company_name":  (d.get("author") or "Unknown Company"),
                "location_text": "Remote" if "remote" in text.lower() else "",
                "description":   body[:4000],
                "posted_at":     posted_at,
                "external_url":  link,
                "external_id":   str(pid),
                "salary_formatted": "Not specified",
                "skills":        extract_skills(text),
                "work_type":     detect_work_type(text),
            }
            if not is_relevant_role(text):
                continue
            out.append(pre)
        return out
    except Exception:
        return []


def fetch(query: str = "", limit: int = 20, subs: List[str] = None) -> List[Dict[str, Any]]:
    subs  = subs or DEFAULT_SUBS
    token = _get_token()
    if not token:
        return []
    items: List[Dict[str, Any]] = []
    per   = max(5, min(50, limit // max(1, len(subs))))
    for s in subs:
        polite_delay(0.2)
        s = s.strip().lstrip("r/")
        items.extend(_fetch_sub(s, token, per))
        if len(items) >= limit:
            break
    return items[:limit]
