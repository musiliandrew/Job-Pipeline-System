"""
jobs/providers/himalayas.py — Himalayas API Integration.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from common.http import safe_get_json, polite_delay
from jobs.filters import is_relevant_role

NAME = "himalayas"


def _parse_date(val: Any) -> datetime:
    try:
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, tz=timezone.utc)
        val_str = str(val).strip()
        if val_str.isdigit():
            return datetime.fromtimestamp(int(val_str), tz=timezone.utc)
        dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def fetch(query: str = "", limit: int = 40) -> List[Dict[str, Any]]:
    # Use search endpoint if query is specified, otherwise browse
    if query:
        url = "https://himalayas.app/jobs/api/search"
        params = {"q": query}
    else:
        url = "https://himalayas.app/jobs/api"
        params = {"limit": min(limit, 20)}

    # Override User-Agent header to bypass Cloudflare block
    headers = {"User-Agent": "python-requests/2.32.3"}

    polite_delay(0.3)
    data = safe_get_json(url, params=params, headers=headers)
    if not data or not isinstance(data, dict):
        return []

    raw_jobs = data.get("jobs") or []
    items: List[Dict[str, Any]] = []

    for j in raw_jobs:
        title = (j.get("title") or "").strip()
        company_name = (j.get("companyName") or "").strip() or "Unknown Company"
        
        # Parse locations list from locationRestrictions
        locs = j.get("locationRestrictions")
        if locs and isinstance(locs, list):
            location_text = ", ".join(locs)
        else:
            location_text = "Remote"

        description = (j.get("description") or j.get("excerpt") or "").strip()
        external_url = j.get("applicationLink") or ""
        external_id = str(j.get("guid") or external_url or title)
        
        # Salary details
        salary_formatted = "Not specified"
        sal_min = j.get("minSalary")
        sal_max = j.get("maxSalary")
        currency = j.get("currency") or "USD"
        if sal_min or sal_max:
            salary_formatted = f"{currency} {sal_min or '0'} - {sal_max or 'unspecified'}"

        pre = {
            "title": title,
            "company_name": company_name,
            "location_text": location_text,
            "description": description,
            "posted_at": _parse_date(j.get("pubDate")),
            "external_url": external_url,
            "external_id": external_id,
            "salary_formatted": salary_formatted,
            "work_type": "remote",
        }

        # Apply relevance check
        text_to_search = f"{title} {description}".lower()
        if not is_relevant_role(text_to_search):
            continue

        items.append(pre)
        if len(items) >= limit:
            break

    return items
