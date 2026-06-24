"""
jobs/providers/arbeitnow.py — Arbeitnow API Integration.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from common.http import safe_get_json, polite_delay
from jobs.filters import is_relevant_role

NAME = "arbeitnow"
API_URL = "https://arbeitnow.com/api/job-board-api"


def _parse_date(val: Any) -> datetime:
    if not val:
        return datetime.now(timezone.utc)
    try:
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, tz=timezone.utc)
        val_str = str(val).strip()
        if val_str.isdigit():
            return datetime.fromtimestamp(int(val_str), tz=timezone.utc)
        return datetime.fromisoformat(val_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def fetch(query: str = "", limit: int = 40) -> List[Dict[str, Any]]:
    # Arbeitnow doesn't have a direct search query parameter on the public endpoint,
    # but we fetch and filter locally or paginate a bit.
    params = {}
    
    polite_delay(0.3)
    data = safe_get_json(API_URL, params=params)
    if not data or not isinstance(data, dict):
        return []

    raw_jobs = data.get("data") or []
    items: List[Dict[str, Any]] = []

    for j in raw_jobs:
        title = (j.get("title") or "").strip()
        company_name = (j.get("company_name") or "").strip() or "Unknown Company"
        location_text = (j.get("location") or "Remote").strip()
        description = (j.get("description") or "").strip()
        external_url = j.get("url") or ""
        external_id = str(j.get("slug") or external_url or title)
        
        is_remote = bool(j.get("remote"))
        work_type = "remote" if is_remote else "onsite"

        pre = {
            "title": title,
            "company_name": company_name,
            "location_text": location_text,
            "description": description,
            "posted_at": _parse_date(j.get("created_at")),
            "external_url": external_url,
            "external_id": external_id,
            "salary_formatted": "Not specified",
            "work_type": work_type,
        }

        # Apply relevance check and query search if specified
        text_to_search = f"{title} {description}".lower()
        if query and query.lower() not in text_to_search:
            continue
            
        if not is_relevant_role(text_to_search):
            continue

        items.append(pre)
        if len(items) >= limit:
            break

    return items
