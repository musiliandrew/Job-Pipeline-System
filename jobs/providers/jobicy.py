"""
jobs/providers/jobicy.py — Jobicy API Integration.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from common.http import safe_get_json, polite_delay
from jobs.filters import is_relevant_role

NAME = "jobicy"
API_URL = "https://jobicy.com/api/v2/remote-jobs"


def _parse_date(s: Any) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        s_str = str(s).strip()
        # Jobicy pubDate e.g. "2026-06-15 12:00:00"
        if " " in s_str and "T" not in s_str:
            s_str = s_str.replace(" ", "T")
        dt = datetime.fromisoformat(s_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def fetch(query: str = "", limit: int = 40) -> List[Dict[str, Any]]:
    params = {"count": min(limit, 100)}
    if query:
        params["tag"] = query

    polite_delay(0.3)
    data = safe_get_json(API_URL, params=params)
    if not data or not isinstance(data, dict):
        return []

    raw_jobs = data.get("jobs") or []
    items: List[Dict[str, Any]] = []

    for j in raw_jobs:
        title = (j.get("jobTitle") or "").strip()
        company_name = (j.get("companyName") or "").strip() or "Unknown Company"
        location_text = (j.get("jobGeo") or "Remote").strip()
        description = (j.get("jobDescription") or j.get("jobExcerpt") or "").strip()
        
        # Correct URL key is "url"
        external_url = j.get("url") or ""
        external_id = str(j.get("id") or external_url or title)
        
        # Correct salary keys are salaryMin / salaryMax
        sal_min = j.get("salaryMin")
        sal_max = j.get("salaryMax")
        sal_curr = j.get("salaryCurrency") or "USD"
        
        salary_formatted = "Not specified"
        if sal_min or sal_max:
            salary_formatted = f"{sal_curr} {sal_min or '0'} - {sal_max or 'unspecified'}"

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
