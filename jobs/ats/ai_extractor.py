"""
jobs/ats/ai_extractor.py — AI-powered job extraction via Firecrawl.
Falls back to empty list if Firecrawl is not configured.
"""
from typing import List, Dict

SCHEMA = (
    '{"type":"object",'
    '"properties":{"jobs":{"type":"array","items":{"type":"object",'
    '"properties":{"title":{"type":"string"},"applyUrl":{"type":"string"},'
    '"location":{"type":"string"},"workType":{"type":"string"}},'
    '"required":["title"]}}},'
    '"required":["jobs"]}'
)


def extract_jobs_ai(careers_url: str, limit: int = 50) -> List[Dict]:
    """Use Firecrawl AI extraction to pull job listings from a careers page."""
    try:
        from common.firecrawl_client import extract as fc_extract
        er = fc_extract(schema=SCHEMA, url=careers_url, timeout=30)
        data = (er or {}).get("data") or {}
        jobs_raw = []
        if isinstance(data, dict):
            jobs_raw = data.get("jobs") or []
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    if isinstance(item.get("data"), dict):
                        jobs_raw = item["data"].get("jobs") or []
                        break
                    jobs_raw.extend(item.get("jobs") or [])

        out: List[Dict] = []
        for j in jobs_raw[:limit]:
            if not isinstance(j, dict):
                continue
            title = (j.get("title") or "").strip()
            if not title:
                continue
            out.append({
                "title":     title,
                "apply_url": j.get("applyUrl") or careers_url,
                "location":  j.get("location") or "",
                "work_type": j.get("workType") or "",
                "external_id": None,
            })
        return out
    except Exception:
        return []
