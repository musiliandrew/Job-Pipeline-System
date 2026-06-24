"""jobs/providers/adzuna.py — Ported from DataIngestion/Jobs/providers/adzuna.py"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from common.http import safe_get_json, polite_delay
from jobs.filters import is_relevant_role

NAME = "adzuna"
BASE_URL = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_COUNTRY = os.getenv("ADZUNA_COUNTRY", "us")


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


def _format_salary(raw: Dict[str, Any]) -> str:
    mn, mx, cur = raw.get("salary_min"), raw.get("salary_max"), raw.get("salary_currency")
    if mn and mx and cur:
        try:
            return f"{cur} {int(mn):,} - {int(mx):,}"
        except Exception:
            pass
    return "Not specified"


def fetch(query: str, page: int = 1, results_per_page: int = 20,
          country: str = DEFAULT_COUNTRY) -> List[Dict[str, Any]]:
    app_id  = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_API_KEY")
    if not app_id or not app_key:
        return []
    params = {
        "app_id":           app_id,
        "app_key":          app_key,
        "what":             query,
        "results_per_page": results_per_page,
        "content-type":     "application/json",
    }
    url = f"{BASE_URL}/{country}/search/{page}"
    polite_delay(0.3)
    data = safe_get_json(url, params=params)
    if not data:
        return []
    items: List[Dict[str, Any]] = []
    for j in data.get("results") or []:
        title        = (j.get("title") or "").strip()
        company_name = ((j.get("company") or {}).get("display_name") or "").strip() or "Unknown Company"
        location_text = ((j.get("location") or {}).get("display_name") or "").strip() or "Remote"
        description  = (j.get("description") or "").strip()
        external_url = j.get("redirect_url") or ""
        external_id  = str(j.get("id") or external_url or title)
        salary_formatted = _format_salary(j)
        pre = {
            "title":            title,
            "company_name":     company_name,
            "location_text":    location_text,
            "description":      description,
            "posted_at":        _parse_date(j.get("created")),
            "external_url":     external_url,
            "external_id":      external_id,
            "salary_formatted": salary_formatted,
        }
        if not is_relevant_role(f"{title} {description}"):
            continue
        items.append(pre)
    return items
