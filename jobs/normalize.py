"""jobs/normalize.py — Ported from DataIngestion/Jobs/normalize.py"""
from datetime import datetime, timezone
from typing import Dict, Any

from jobs.filters import extract_skills, detect_work_type, is_relevant_role


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_unified(provider: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize provider-specific item into unified shape for upsert_job().
    Input fields: title, company_name, location_text, description,
                  posted_at, external_url, external_id, salary_formatted?
    """
    title        = (item.get("title") or "").strip()[:255]
    company_name = (item.get("company_name") or "Unknown Company").strip()[:255]
    location_text = (item.get("location_text") or "Remote").strip()
    description  = (item.get("description") or "").strip()
    external_url = item.get("external_url") or ""
    external_id  = item.get("external_id") or external_url or title
    posted_at    = item.get("posted_at") or _now()
    # Detect remote/hybrid location details
    loc_lower = location_text.lower()
    text_lower = f"{title} {description}".lower()
    item_work_type = (item.get("work_type") or "").lower()

    is_hybrid = "hybrid" in loc_lower or "hybrid" in text_lower or item_work_type == "hybrid"
    if is_hybrid:
        is_remote = False
    else:
        is_remote = (
            item.get("is_remote") is True or
            item_work_type == "remote" or
            provider in ("remotive", "jobicy", "himalayas") or
            any(w in loc_lower for w in ["remote", "anywhere", "worldwide", "wfh"]) or
            any(w in text_lower for w in ["remote", "wfh", "work from home", "telecommute"])
        )

    work_type = "hybrid" if is_hybrid else ("remote" if is_remote else "onsite")
    skills       = item.get("skills") or extract_skills(f"{title} {description}")
    salary_formatted = item.get("salary_formatted") or "Not specified"

    return {
        "title":            title,
        "company_name":     company_name,
        "location_text":    location_text,
        "work_type":        work_type,
        "is_remote":        is_remote,
        "is_hybrid":        is_hybrid,
        "salary_formatted": salary_formatted,
        "posted_at":        posted_at,
        "skills":           skills,
        "description":      description,
        "source":           provider,
        "external_url":     external_url,
        "external_id":      str(external_id),
    }

