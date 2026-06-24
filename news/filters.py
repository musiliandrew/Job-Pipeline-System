"""news/filters.py — Ported from DataIngestion/News/filters.py (no Django deps)"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
import re

INCLUDE_KEYWORDS = [
    "data science", "machine learning", "ml", "ai", "artificial intelligence",
    "software engineering", "llm", "mlops", "genai", "generative ai",
    "deep learning", "neural network", "vector db", "rag", "data engineering",
    "technology", "software", "cloud", "gpu", "nvidia", "openai", "anthropic", "meta ai",
]

EXCLUDE_KEYWORDS = [
    "football", "basketball", "baseball", "celebrity", "gossip", "coupon", "lottery", "horoscope",
]

ALLOWED_SOURCES: List[str] = []
BLOCKED_SOURCES: List[str] = []
MAX_AGE_DAYS = 14


def _norm(val) -> str:
    return (val or "").lower()


def _match_topics(text: str) -> List[str]:
    seen = []
    for kw in INCLUDE_KEYWORDS:
        if kw in text:
            token = re.sub(r"[^a-z0-9]+", "-", kw.strip().lower()).strip("-")
            if token not in seen:
                seen.append(token)
    return seen


def should_keep(item: Dict) -> Tuple[bool, List[str]]:
    source = _norm(item.get("source"))
    if source in [s.lower() for s in BLOCKED_SOURCES if s]:
        return False, []
    if ALLOWED_SOURCES and source not in [s.lower() for s in ALLOWED_SOURCES if s]:
        return False, []
    pub = item.get("published_at")
    if isinstance(pub, datetime):
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub < datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS):
            return False, []
    text = f"{_norm(item.get('title'))} {_norm(item.get('summary'))} {_norm(item.get('content'))}"
    if not any(kw in text for kw in INCLUDE_KEYWORDS):
        return False, []
    if any(ek in text for ek in EXCLUDE_KEYWORDS):
        return False, []
    return True, _match_topics(text)
