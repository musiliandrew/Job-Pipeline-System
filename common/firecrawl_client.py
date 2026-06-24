"""common/firecrawl_client.py — Ported from DataIngestion/_common/firecrawl_client.py"""
import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = (
    os.getenv("CRAWLER_BASE_URL")
    or os.getenv("FIRECRAWLER_BASE_URL")
    or os.getenv("FIRECRAWLER_URL")
    or "http://localhost:7071"
)
API_KEY = (
    os.getenv("CRAWLER_API_KEY")
    or os.getenv("FIRECRAWLER_API_KEY")
    or os.getenv("FIRECRAWLER_KEY")
    or ""
)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
DEFAULT_TIMEOUT = float(os.getenv("CRAWLER_HTTP_TIMEOUT", "20"))
SESSION = requests.Session()


def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def _post(path: str, payload: Dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    url = BASE_URL.rstrip("/") + path
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            resp = SESSION.post(url, headers=_headers(), data=json.dumps(payload), timeout=timeout)
            try:
                data = resp.json()
            except Exception:
                data = {"success": False, "status": resp.status_code, "text": resp.text[:1000]}
            if resp.status_code >= 400:
                last_err = RuntimeError(f"crawler POST {path} failed: {resp.status_code} {data}")
            else:
                return data
        except Exception as e:
            last_err = e
        if attempt < 2:
            time.sleep(1 if attempt == 0 else 3)
    if last_err:
        raise last_err
    return {"success": False, "error": "unknown"}


def fetch(url: str, render: bool = True, timeout: Optional[float] = None) -> Dict[str, Any]:
    payload = {"url": url, "formats": ["html"]}
    return _post("/v2/scrape", payload, timeout=timeout or DEFAULT_TIMEOUT)


def crawl(seed_url: str, limit: int = 8, depth: int = 2, timeout: Optional[float] = None) -> Dict[str, Any]:
    payload = {"url": seed_url, "limit": max(1, min(int(limit), 25)), "scrapeOptions": {"formats": ["html"]}}
    return _post("/v2/crawl", payload, timeout=timeout or DEFAULT_TIMEOUT)


def extract(schema: str, *, url: Optional[str] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"schema": schema}
    if url:
        payload["urls"] = [url]
    return _post("/v2/extract", payload, timeout=timeout or DEFAULT_TIMEOUT)


TRUST_TLDS = {"com", "io", "ai", "dev", "co"}


def _brand_tokens(name: str) -> List[str]:
    import re
    n = name.lower()
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    return [p for p in n.split() if p and p not in {"inc", "ltd", "corp", "co", "plc"}]


def _guess_homepage_candidates(name: str) -> List[str]:
    toks = _brand_tokens(name)
    joined = "".join(toks)
    hyphen = "-".join(toks)
    return [
        f"https://{joined}.com", f"https://{joined}.ai", f"https://{joined}.io",
        f"https://{hyphen}.com", f"https://{hyphen}.ai", f"https://{hyphen}.io",
    ]


def _common_careers_from_homepage(homepage: str) -> List[str]:
    from urllib.parse import urljoin
    paths = ["/careers", "/jobs", "/join", "/join-us", "/work-with-us", "/open-roles"]
    return [urljoin(homepage, p) for p in paths]


def _score_domain(url: str, tokens: List[str]) -> int:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).netloc or "").lower()
        tld = host.split(".")[-1]
        return max(0, min(100, sum(20 for t in tokens if t and t in host) + (10 if tld in TRUST_TLDS else 0)))
    except Exception:
        return 0


def discover(name: str, tier: Optional[str] = None, confirm_with_fetch: bool = True) -> Dict[str, Any]:
    toks = _brand_tokens(name)
    h_guesses = _guess_homepage_candidates(name)
    scored = sorted(((u, _score_domain(u, toks)) for u in h_guesses), key=lambda x: x[1], reverse=True)
    h_best: Optional[Tuple[str, int]] = scored[0] if scored else None

    tav_home: Optional[Tuple[str, int]] = None
    tav_careers: Optional[Tuple[str, int]] = None
    tav_used = False
    if TAVILY_API_KEY:
        try:
            from common.tavily_client import search_homepage, search_careers
            tav_used = True
            def pick(lst):
                best_u, best_s = None, -1
                for it in lst or []:
                    u = it.get("url")
                    if not u: continue
                    s = _score_domain(u, toks)
                    if s > best_s:
                        best_u, best_s = u, s
                return (best_u, best_s) if best_u else None
            tav_home = pick(search_homepage(name, tier))
            tav_careers = pick(search_careers(name))
        except Exception:
            pass

    picks = sorted([p for p in [tav_home, h_best] if p], key=lambda x: x[1], reverse=True)
    homepage_pick = picks[0] if picks else None

    careers_candidates: List[Tuple[str, int]] = []
    if homepage_pick:
        for u in _common_careers_from_homepage(homepage_pick[0]):
            careers_candidates.append((u, _score_domain(u, toks)))
    if tav_careers:
        careers_candidates.append(tav_careers)
    careers_candidates.sort(key=lambda x: x[1], reverse=True)
    careers_pick = careers_candidates[0] if careers_candidates else None

    out: Dict[str, Any] = {"sources": {"tavily_used": tav_used, "heuristics_used": True}}

    def confirm(u_pick):
        if not u_pick:
            return None
        u, s = u_pick
        final_url = None
        if confirm_with_fetch and BASE_URL:
            try:
                resp = fetch(u)
                data = resp.get("data") or {}
                meta = data.get("metadata") or {}
                status = int(meta.get("statusCode") or 0)
                if status in (200, 301, 302, 403):
                    final_url = meta.get("sourceURL") or meta.get("ogUrl") or u
                elif s < 40:
                    return None
            except Exception:
                if s < 60:
                    return None
        return {"url": u, "score": s, **({} if not final_url else {"final_url": final_url})}

    hp = confirm(homepage_pick)
    cp = confirm(careers_pick)
    if hp:
        out["homepage"] = hp
    if cp:
        out["careers"] = cp
    return out
