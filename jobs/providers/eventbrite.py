"""jobs/providers/eventbrite.py — Ported from DataIngestion/Jobs/providers/eventbrite.py"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from common.http import safe_get_json, polite_delay
from jobs.filters import is_relevant_role

NAME     = "eventbrite"
BASE_URL = "https://www.eventbriteapi.com/v3/events/search/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fetch(query: str = "job fair hiring", page: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
    key = os.getenv("EVENTBRITE_API_KEY") or os.getenv("EVENTBRITE_PRIVATE_TOKEN")
    if not key:
        return []
    params  = {"q": query, "page": page, "expand": "organizer,venue"}
    headers = {"Authorization": f"Bearer {key}"}
    polite_delay(0.3)
    data = safe_get_json(BASE_URL, params=params, headers=headers)
    if not data:
        return []
    items: List[Dict[str, Any]] = []
    for e in (data.get("events") or [])[:limit]:
        name = ((e.get("name") or {}).get("text") or "").strip()
        desc = ((e.get("description") or {}).get("text") or "").strip()
        url  = e.get("url") or ""
        eid  = e.get("id") or url or name
        start = ((e.get("start") or {}).get("utc"))
        posted_at = _now()
        if start:
            try:
                posted_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except Exception:
                posted_at = _now()
        text = f"{name} {desc}"
        if not any(k in text.lower() for k in ["hiring", "job", "recruit", "career", "talent fair"]):
            continue
        if not is_relevant_role(text):
            continue
        items.append({
            "title":            name or "Hiring Event",
            "company_name":     (e.get("organization_id") or "Event"),
            "location_text":    (e.get("venue_id") or ""),
            "description":      desc[:4000],
            "posted_at":        posted_at,
            "external_url":     url,
            "external_id":      str(eid),
            "salary_formatted": "Not specified",
        })
    return items
