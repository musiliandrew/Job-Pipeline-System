"""news/industry_dive.py — Ported from DataIngestion/News/industry_dive.py (Django ORM removed)"""
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

from db.connection import DBConn
from db.upserts import upsert_news_article
from news.filters import should_keep


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _normalize_item(it: Dict) -> Optional[Dict]:
    title = (it.get("title") or it.get("headline") or "").strip()
    url   = it.get("url") or it.get("link") or it.get("permalink") or ""
    if not url or not title:
        return None
    pub = it.get("published_at") or it.get("date") or it.get("published") or None
    try:
        published_at = datetime.fromisoformat(str(pub).replace("Z", "+00:00")) if isinstance(pub, str) else _now()
    except Exception:
        published_at = _now()
    return {
        "title":        title,
        "url":          url,
        "source":       _host(url),
        "published_at": published_at,
        "summary":      it.get("summary") or it.get("snippet") or None,
        "content":      it.get("content") or it.get("body") or None,
    }


def ingest_industry_dive(
    max_items: int = 50,
    query: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict:
    api_key = os.getenv("INDUSTRY_DIVE_API_KEY")
    base    = os.getenv("INDUSTRY_DIVE_BASE_URL", "https://api.diveaccess.com")
    if not api_key or not base:
        return {"created": 0, "skipped": 0, "error": "missing_api_or_base_url"}
    created = 0
    skipped = 0
    errors: List[str] = []
    try:
        params = {"limit": max_items, "access_key": api_key}
        if query:
            params["query"] = query
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        trimmed  = base.rstrip("/")
        endpoint = trimmed if trimmed.endswith("/articles") else trimmed + "/articles"
        r    = requests.get(endpoint, params=params, timeout=20)
        r.raise_for_status()
        data  = r.json() or {}
        items = data.get("articles") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        norm  = [n for raw in (items or []) if (n := _normalize_item(raw))]
        with DBConn() as conn:
            for it in norm:
                keep, topics = should_keep(it)
                if not keep:
                    continue
                it["tags"] = topics
                status = upsert_news_article(conn, it)
                if status == "created":
                    created += 1
                else:
                    skipped += 1
    except Exception as e:
        errors.append(str(e))
    return {"created": created, "skipped": skipped, "errors": errors}


def industry_dive_preview(
    query: Optional[str] = None,
    limit: int = 10,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict:
    api_key = os.getenv("INDUSTRY_DIVE_API_KEY")
    base    = os.getenv("INDUSTRY_DIVE_BASE_URL", "https://api.diveaccess.com")
    if not api_key or not base:
        return {"error": "missing_api_or_base_url"}
    try:
        params = {"limit": limit, "access_key": api_key}
        if query:
            params["query"] = query
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        trimmed  = base.rstrip("/")
        endpoint = trimmed if trimmed.endswith("/articles") else trimmed + "/articles"
        r     = requests.get(endpoint, params=params, timeout=20)
        data  = r.json() or {}
        items = data.get("articles") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        sample = [(it.get("title") or it.get("headline") or "")[:200] for it in items[:5] if it.get("title") or it.get("headline")]
        return {"status_code": r.status_code, "count": len(items), "sample": sample}
    except Exception as e:
        return {"error": str(e)}
