"""companies/discovery.py — Ported from DataIngestion/Companies/discovery.py (Django removed)"""
from typing import Optional, Dict, List, Tuple
from urllib.parse import urljoin
import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
AGGREGATOR_HOSTS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "monster.com",
    "ziprecruiter.com", "simplyhired.com", "careerbuilder.com",
}
TRUST_TLDS = {"com", "io", "ai", "dev", "co"}


def brand_tokens(name: str) -> List[str]:
    n = name.lower()
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    return [p for p in n.split() if p and p not in {"inc", "ltd", "corp", "co", "plc"}]


def guess_homepage_candidates(name: str) -> List[str]:
    toks = brand_tokens(name)
    joined = "".join(toks)
    hyphen = "-".join(toks)
    return [
        f"https://{joined}.com", f"https://{joined}.ai", f"https://{joined}.io",
        f"https://{hyphen}.com", f"https://{hyphen}.ai", f"https://{hyphen}.io",
    ]


def common_careers_from_homepage(homepage: str) -> List[str]:
    paths = ["/careers", "/jobs", "/join", "/join-us", "/work-with-us", "/open-roles"]
    return [urljoin(homepage, p) for p in paths]


def score_domain_for_brand(url: str, tokens: List[str]) -> int:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).netloc or "").lower()
        tld  = host.split(".")[-1]
        return max(0, min(100, sum(20 for t in tokens if t and t in host) + (10 if tld in TRUST_TLDS else 0)))
    except Exception:
        return 0


def is_http_ok(url: str) -> bool:
    try:
        r = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        return r.status_code in (200, 301, 302, 403)
    except Exception:
        return False


def is_aggregator(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).netloc or "").lower()
        return any(agg in host for agg in AGGREGATOR_HOSTS)
    except Exception:
        return False


def _pick_best(candidates: List[str], brand: str) -> Optional[Tuple[str, int]]:
    tokens = brand_tokens(brand)
    scored = [(u, score_domain_for_brand(u, tokens)) for u in candidates if is_http_ok(u)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0] if scored else None


def choose_best_homepage(name: str, tier: Optional[str] = None) -> Optional[Dict]:
    try:
        from common.firecrawl_client import discover as fc_discover
        d  = fc_discover(name=name, tier=tier, confirm_with_fetch=True)
        hp = (d or {}).get("homepage") or {}
        url = hp.get("final_url") or hp.get("url")
        if url:
            return {"url": url, "score": hp.get("score") or 0}
    except Exception:
        pass
    h_guesses  = guess_homepage_candidates(name)
    h_pick     = _pick_best(h_guesses, name)
    try:
        from common.tavily_client import search_homepage
        t_results = search_homepage(name, tier) or []
        t_pick    = _pick_best([r.get("url") for r in t_results if r.get("url")], name)
    except Exception:
        t_pick = None
    picks = [p for p in [h_pick, t_pick] if p]
    if not picks:
        return None
    best = max(picks, key=lambda x: x[1])
    return {"url": best[0], "score": best[1]}


def choose_best_careers(name: str, homepage: Optional[str]) -> Optional[Dict]:
    try:
        from common.firecrawl_client import discover as fc_discover
        d  = fc_discover(name=name, tier=None, confirm_with_fetch=True)
        cp = (d or {}).get("careers") or {}
        url = cp.get("final_url") or cp.get("url")
        if url and not is_aggregator(url):
            return {"url": url, "score": cp.get("score") or 0}
    except Exception:
        pass
    candidates = list(common_careers_from_homepage(homepage)) if homepage else []
    try:
        from common.tavily_client import search_careers
        candidates.extend([r.get("url") for r in (search_careers(name) or []) if r.get("url")])
    except Exception:
        pass
    candidates = [c for c in candidates if c and not is_aggregator(c)]
    pick = _pick_best(candidates, name)
    if not pick:
        return None
    return {"url": pick[0], "score": pick[1]}


def resolve_careers_candidates(name: str, homepage: Optional[str], careers_url: Optional[str]) -> List[str]:
    candidates: List[str] = []
    if careers_url:
        candidates.append(careers_url)
    if homepage:
        candidates.extend(common_careers_from_homepage(homepage))
    try:
        from common.tavily_client import search_careers
        candidates.extend([r.get("url") for r in (search_careers(name) or []) if r.get("url")])
    except Exception:
        pass
    try:
        from common.firecrawl_client import crawl as fc_crawl
        seed = careers_url or homepage or ""
        if seed:
            cr   = fc_crawl(seed, limit=6, depth=1)
            data = (cr or {}).get("data") or {}
            links: List[str] = []
            if isinstance(data, dict) and isinstance(data.get("links"), list):
                links = [l.get("url") for l in data["links"] if isinstance(l, dict) and l.get("url")]
            elif isinstance(data, list):
                for page in data:
                    for l in (page.get("links") or []):
                        u = l.get("url") if isinstance(l, dict) else None
                        if u:
                            links.append(u)
            job_terms = ("job", "jobs", "career", "careers", "opening", "openings", "positions", "workday", "greenhouse", "lever")
            candidates.extend(u for u in links if any(t in (u or "").lower() for t in job_terms))
    except Exception:
        pass
    candidates = [c for c in candidates if c and not is_aggregator(c)]
    seen:  set = set()
    deduped: List[str] = []
    for u in candidates:
        if u not in seen:
            deduped.append(u)
            seen.add(u)
    return deduped
