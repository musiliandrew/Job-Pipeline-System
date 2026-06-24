"""
jobs/github/pittcsc.py — Pitt Computer Science Club (pittcsc) internships parser.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any
from common.http import safe_get_json
from jobs.filters import is_relevant_role

NAME = "pittcsc"
URL_2026 = "https://raw.githubusercontent.com/pittcsc/Summer2026-Internships/dev/.github/scripts/listings.json"
URL_2026_FALLBACK = "https://raw.githubusercontent.com/pittcsc/Summer2026-Internships/main/.github/scripts/listings.json"
URL_2025 = "https://raw.githubusercontent.com/pittcsc/Summer2025-Internships/dev/.github/scripts/listings.json"
URL_2025_FALLBACK = "https://raw.githubusercontent.com/pittcsc/Summer2025-Internships/main/.github/scripts/listings.json"


def fetch(limit: int = 100) -> List[Dict[str, Any]]:
    # Try 2026 then 2025
    data = safe_get_json(URL_2026)
    if not data:
        data = safe_get_json(URL_2026_FALLBACK)
    if not data:
        data = safe_get_json(URL_2025)
    if not data:
        data = safe_get_json(URL_2025_FALLBACK)

    if not data or not isinstance(data, list):
        return []

    items: List[Dict[str, Any]] = []
    for j in data:
        if not isinstance(j, dict):
            continue
        title = (j.get("title") or "Software Engineering Intern").strip()
        company_name = (j.get("company") or j.get("company_name") or "").strip() or "Unknown Company"
        
        # Location
        locs = j.get("locations") or j.get("location") or "Remote"
        if isinstance(locs, list):
            location_text = ", ".join(locs)
        else:
            location_text = str(locs)

        external_url = j.get("url") or j.get("apply_url") or ""
        external_id = str(j.get("id") or j.get("hash") or external_url or title)

        posted_val = j.get("date_added") or j.get("date") or ""
        try:
            if isinstance(posted_val, (int, float)):
                posted_at = datetime.fromtimestamp(posted_val, tz=timezone.utc)
            else:
                posted_at = datetime.fromisoformat(str(posted_val).replace("Z", "+00:00"))
        except Exception:
            posted_at = datetime.now(timezone.utc)

        pre = {
            "title": title,
            "company_name": company_name,
            "location_text": location_text,
            "description": f"Internship listing from Pitt CSC. Location: {location_text}",
            "posted_at": posted_at,
            "external_url": external_url,
            "external_id": external_id,
            "salary_formatted": "Not specified",
            "work_type": "internship",
        }

        if not is_relevant_role(f"{title}"):
            continue

        items.append(pre)
        if len(items) >= limit:
            break

    return items
