"""
jobs/github/simplify.py — SimplifyJobs GitHub listings parser.
Fetches public listings from raw.githubusercontent.com.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any
from common.http import safe_get_json
from jobs.filters import is_relevant_role

NAME = "simplify"
URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json"
FALLBACK_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/main/.github/scripts/listings.json"


def fetch(limit: int = 100) -> List[Dict[str, Any]]:
    # Try dev branch first, then fallback to main branch
    data = safe_get_json(URL)
    if not data:
        data = safe_get_json(FALLBACK_URL)
    if not data or not isinstance(data, list):
        return []

    items: List[Dict[str, Any]] = []
    for j in data:
        if not isinstance(j, dict):
            continue
        title = (j.get("title") or "").strip()
        company_name = (j.get("company") or j.get("company_name") or "").strip() or "Unknown Company"
        
        # Location
        locs = j.get("locations") or j.get("location") or "Remote"
        if isinstance(locs, list):
            location_text = ", ".join(locs)
        else:
            location_text = str(locs)

        external_url = j.get("url") or j.get("apply_url") or ""
        # Create a stable external_id
        external_id = str(j.get("id") or j.get("hash") or external_url or title)

        # Date added
        posted_val = j.get("date_added") or j.get("date") or ""
        try:
            if isinstance(posted_val, (int, float)):
                posted_at = datetime.fromtimestamp(posted_val, tz=timezone.utc)
            else:
                # E.g. "2026-06-15" or ISO
                posted_at = datetime.fromisoformat(str(posted_val).replace("Z", "+00:00"))
        except Exception:
            posted_at = datetime.now(timezone.utc)

        pre = {
            "title": title,
            "company_name": company_name,
            "location_text": location_text,
            "description": f"New Grad Position from SimplifyJobs. Location: {location_text}",
            "posted_at": posted_at,
            "external_url": external_url,
            "external_id": external_id,
            "salary_formatted": "Not specified",
            "work_type": "full-time",
        }

        if not is_relevant_role(f"{title}"):
            continue

        items.append(pre)
        if len(items) >= limit:
            break

    return items
