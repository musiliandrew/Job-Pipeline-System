"""common/tavily_client.py — Ported from DataIngestion/_common/tavily_client.py"""
import os
from typing import List, Dict, Optional

try:
    from tavily import TavilyClient  # type: ignore
except Exception:
    TavilyClient = None

DEFAULT_FIELDS = ["title", "url", "content", "score"]


def _get_client() -> Optional["TavilyClient"]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or TavilyClient is None:
        return None
    try:
        return TavilyClient(api_key=api_key)
    except Exception:
        return None


def _normalize(results: List[Dict]) -> List[Dict]:
    norm = []
    for r in results or []:
        item = {k: r.get(k) for k in DEFAULT_FIELDS}
        item["snippet"] = r.get("content")
        norm.append(item)
    return norm


def search_homepage(company_name: str, tier: Optional[str] = None, max_results: int = 5) -> List[Dict]:
    client = _get_client()
    if not client:
        return []
    query = f"{company_name} {tier} official site" if tier else f"{company_name} official site"
    try:
        res = client.search(query=query, max_results=max_results)
        return _normalize(res.get("results", []))
    except Exception:
        return []


def search_careers(company_name: str, max_results: int = 5) -> List[Dict]:
    client = _get_client()
    if not client:
        return []
    try:
        res = client.search(query=f"{company_name} careers jobs", max_results=max_results)
        return _normalize(res.get("results", []))
    except Exception:
        return []


def search_news(company_name: str, max_results: int = 5) -> List[Dict]:
    client = _get_client()
    if not client:
        return []
    try:
        res = client.search(query=f"{company_name} press news", max_results=max_results)
        return _normalize(res.get("results", []))
    except Exception:
        return []
