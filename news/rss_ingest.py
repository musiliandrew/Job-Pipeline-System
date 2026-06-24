"""news/rss_ingest.py — Ported from DataIngestion/News/rss_ingest.py (Django ORM removed)"""
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urlparse

import requests

try:
    import feedparser  # type: ignore
except Exception:
    feedparser = None

from db.connection import DBConn
from db.upserts import upsert_news_article
from news.filters import should_keep

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _parse_date(entry: Dict) -> datetime:
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    s = entry.get("published") or entry.get("updated")
    if isinstance(s, str):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            pass
    return _now()


def ingest_feeds(feed_urls: List[str], max_items_per_feed: int = 30) -> Dict:
    created = 0
    skipped = 0
    errors: List[str] = []
    per_feed: List[Dict] = []

    for feed in feed_urls:
        feed_created = 0
        feed_skipped = 0
        try:
            items: List[Dict] = []
            if feedparser:
                parsed = feedparser.parse(feed)
                for e in (parsed.entries or [])[:max_items_per_feed]:
                    url   = e.get("link") or e.get("id")
                    title = (e.get("title") or "").strip()
                    if not url or not title:
                        continue
                    items.append({
                        "title":        title,
                        "url":          url,
                        "summary":      e.get("summary") or e.get("subtitle") or None,
                        "published_at": _parse_date(e),
                        "source":       _host(url),
                    })

            with DBConn() as conn:
                for it in items:
                    keep, topics = should_keep(it)
                    if not keep:
                        continue
                    it["tags"] = topics
                    status = upsert_news_article(conn, it)
                    if status == "created":
                        feed_created += 1
                    else:
                        feed_skipped += 1

            created += feed_created
            skipped += feed_skipped
            per_feed.append({"feed": feed, "created": feed_created, "skipped": feed_skipped})
        except Exception as e:
            errors.append(f"{feed}: {e}")
            per_feed.append({"feed": feed, "error": str(e)})

    return {"created": created, "skipped": skipped, "feeds": per_feed, "errors": errors}
