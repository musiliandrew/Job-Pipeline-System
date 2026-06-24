"""
jobs/providers/themuse.py — The Muse API Integration.
"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from common.http import safe_get_json, polite_delay
from jobs.filters import is_relevant_role

NAME = "themuse"
API_URL = "https://www.themuse.com/api/public/jobs"


def _parse_date(s: str) -> datetime:
    try:
        # The Muse dates: e.g. "2026-06-15T12:00:00Z"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def fetch(query: str = "", limit: int = 40) -> List[Dict[str, Any]]:
    # The Muse allows filtering by category (e.g. "Software Engineering", "Data Science")
    # or general search. Let's do category search if no general query, or query filtering locally.
    params = {"page": 1}
    api_key = os.getenv("THEMUSE_API_KEY")
    if api_key:
        params["api_key"] = api_key

    # Fetch a few categories to get good jobs
    categories = ["Software Engineering", "Data Science", "Data and Analytics"]
    
    items: List[Dict[str, Any]] = []
    
    for cat in categories:
        cat_params = params.copy()
        cat_params["category"] = cat
        
        polite_delay(0.3)
        data = safe_get_json(API_URL, params=cat_params)
        if not data or not isinstance(data, dict):
            continue

        raw_jobs = data.get("results") or []
        for j in raw_jobs:
            title = (j.get("name") or "").strip()
            company_name = ((j.get("company") or {}).get("name") or "").strip() or "Unknown Company"
            
            locs = j.get("locations") or []
            location_text = ", ".join(l.get("name") for l in locs if l.get("name")) or "Remote"
            
            description = (j.get("contents") or "").strip()
            external_url = (j.get("refs") or {}).get("landing_page") or ""
            external_id = str(j.get("id") or external_url or title)

            pre = {
                "title": title,
                "company_name": company_name,
                "location_text": location_text,
                "description": description,
                "posted_at": _parse_date(j.get("publication_date")),
                "external_url": external_url,
                "external_id": external_id,
                "salary_formatted": "Not specified",
            }

            text_to_search = f"{title} {description}".lower()
            if query and query.lower() not in text_to_search:
                continue

            if not is_relevant_role(text_to_search):
                continue

            items.append(pre)
            if len(items) >= limit:
                break
                
        if len(items) >= limit:
            break

    return items[:limit]
