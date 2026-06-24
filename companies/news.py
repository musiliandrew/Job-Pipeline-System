"""companies/news.py — Ingest recent news for companies via Tavily."""
import logging
from datetime import datetime, timezone
from typing import Dict

from db.connection import DBConn
from db.upserts import get_all_companies, upsert_news_article

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ingest_news_for_companies(limit_companies: int = 50, items_per_company: int = 5) -> Dict:
    results = {"companies": 0, "created": 0, "skipped": 0, "errors": 0}

    with DBConn() as conn:
        companies = get_all_companies(conn, limit=limit_companies)

    for c in companies:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        try:
            from common.tavily_client import search_news
            news_items = search_news(name, max_results=items_per_company) or []
            created = skipped = 0
            with DBConn() as conn:
                for item in news_items:
                    url = item.get("url")
                    if not url:
                        continue
                    article = {
                        "title":        (item.get("title") or "")[:500],
                        "url":          url,
                        "source":       (item.get("url") or "").split("/")[2] if url else "",
                        "published_at": _now(),
                        "summary":      item.get("snippet") or item.get("content") or "",
                        "tags":         [name.lower()],
                    }
                    status = upsert_news_article(conn, article)
                    if status == "created":
                        created += 1
                    else:
                        skipped += 1
            results["companies"] += 1
            results["created"]   += created
            results["skipped"]   += skipped
        except Exception as e:
            logger.error("ingest_news_for_companies: %s error: %s", name, e)
            results["errors"] += 1

    logger.info("ingest_news_for_companies: %s", results)
    return results
