"""
jobs/providers/remotive.py — Remotive API Integration.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from common.http import safe_get_json, polite_delay
from jobs.filters import is_relevant_role

NAME = "remotive"
API_URL = "https://remotive.com/api/remote-jobs"


def _parse_date(s: Any) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        s_str = str(s).strip()
        dt = datetime.fromisoformat(s_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def fetch(query: str = "", limit: int = 40) -> List[Dict[str, Any]]:
    # Remotive has query parameters: category, search, limit
    params = {}
    if query:
        params["search"] = query
    params["limit"] = limit

    polite_delay(0.3)
    data = safe_get_json(API_URL, params=params)
    if not data or not isinstance(data, dict):
        return []

    raw_jobs = data.get("jobs") or []
    items: List[Dict[str, Any]] = []

    for j in raw_jobs[:limit]:
        title = (j.get("title") or "").strip()
        company_name = (j.get("company_name") or "").strip() or "Unknown Company"
        location_text = (j.get("candidate_required_location") or "Remote").strip()
        description = (j.get("description") or "").strip()
        external_url = j.get("url") or ""
        external_id = str(j.get("id") or external_url or title)
        
        # Salary detection from range if possible
        salary_formatted = j.get("salary") or "Not specified"

        pre = {
            "title": title,
            "company_name": company_name,
            "location_text": location_text,
            "description": description,
            "posted_at": _parse_date(j.get("publication_date")),
            "external_url": external_url,
            "external_id": external_id,
            "salary_formatted": salary_formatted,
            "work_type": "remote",
        }

        # Apply relevance check
        if not is_relevant_role(f"{title} {description}"):
            continue

        items.append(pre)

    return items
