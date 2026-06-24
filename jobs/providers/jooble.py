"""jobs/providers/jooble.py — Ported from DataIngestion/Jobs/providers/jooble.py"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from common.http import safe_post_json, polite_delay
from jobs.filters import is_relevant_role

API_URL = "https://jooble.org/api/"
NAME    = "jooble"


def _parse_date(s: Any) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        s_str = str(s).strip()
        dt = datetime.fromisoformat(s_str[:19])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def fetch(query: str, page: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
    key = os.getenv("JOOBLE_API_KEY")
    if not key:
        return []
    body: Dict[str, Any] = {"keywords": query, "page": page, "searchMode": 1}
    polite_delay(0.3)
    data = safe_post_json(API_URL + key, body)
    if not data:
        return []
    items: List[Dict[str, Any]] = []
    for j in (data.get("jobs") or [])[:limit]:
        title        = (j.get("title") or "").strip()
        company_name = (j.get("company") or "").strip() or "Unknown Company"
        location_text = (j.get("location") or "").strip() or "Remote"
        description  = (j.get("snippet") or j.get("description") or "").strip()
        external_url = j.get("link") or j.get("url") or ""
        external_id  = str(j.get("id") or external_url or title)
        salary_formatted = str(j.get("salary") or "Not specified")
        pre = {
            "title":            title,
            "company_name":     company_name,
            "location_text":    location_text,
            "description":      description,
            "posted_at":        _parse_date(j.get("updated")),
            "external_url":     external_url,
            "external_id":      external_id,
            "salary_formatted": salary_formatted,
        }
        if not is_relevant_role(f"{title} {description}"):
            continue
        items.append(pre)
    return items
