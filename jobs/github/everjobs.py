"""
jobs/github/everjobs.py — EverJobs open source job repository parser.
Fetches jobs from community-curated JSON files.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any
from common.http import safe_get_json
from jobs.filters import is_relevant_role

NAME = "everjobs"
# A set of community-driven lists or fallbacks
URLS = [
    "https://raw.githubusercontent.com/rust-jobs/jobs/main/jobs.json",
    "https://raw.githubusercontent.com/golang/jobs/master/jobs.json",
]


def fetch(limit: int = 100) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    
    for url in URLS:
        try:
            data = safe_get_json(url)
            if not data or not isinstance(data, list):
                continue
                
            for j in data:
                if not isinstance(j, dict):
                    continue
                title = (j.get("title") or j.get("role") or "").strip()
                company_name = (j.get("company") or j.get("company_name") or "").strip() or "Unknown Company"
                location_text = (j.get("location") or "Remote").strip()
                external_url = j.get("url") or j.get("apply_url") or ""
                external_id = str(j.get("id") or external_url or title)
                
                desc = (j.get("description") or j.get("summary") or f"Job listing from {url.split('/')[3]}/{url.split('/')[4]}")
                
                posted_val = j.get("posted_at") or j.get("date") or ""
                try:
                    posted_at = datetime.fromisoformat(str(posted_val).replace("Z", "+00:00"))
                except Exception:
                    posted_at = datetime.now(timezone.utc)
                    
                pre = {
                    "title": title,
                    "company_name": company_name,
                    "location_text": location_text,
                    "description": desc,
                    "posted_at": posted_at,
                    "external_url": external_url,
                    "external_id": external_id,
                    "salary_formatted": "Not specified",
                    "work_type": "full-time",
                }
                
                if not is_relevant_role(f"{title} {desc}"):
                    continue
                    
                items.append(pre)
                if len(items) >= limit:
                    break
        except Exception:
            pass
            
        if len(items) >= limit:
            break
            
    return items
