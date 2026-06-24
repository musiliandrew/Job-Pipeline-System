"""
jobs/collector.py — Orchestrates all external job provider collections.
Uses ThreadPoolExecutor for high-performance concurrent collection.
Uses raw psycopg2 via db/ layer — no Django ORM.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.connection import DBConn
from db.upserts import upsert_source, upsert_company, upsert_location, upsert_job, log_collection
from jobs.normalize import normalize_unified

logger = logging.getLogger(__name__)

DEFAULT_QUERY = (
    "data scientist OR machine learning OR ai engineer OR software engineer"
)

# Active Providers Registry
PROVIDERS = {
    # Tier 1 Free REST APIs
    "remotive":   {"base_url": "https://remotive.com"},
    "arbeitnow":  {"base_url": "https://arbeitnow.com"},
    "adzuna":     {"base_url": "https://adzuna.com"},
    "jobicy":     {"base_url": "https://jobicy.com"},
    "themuse":    {"base_url": "https://www.themuse.com"},
    "himalayas":  {"base_url": "https://himalayas.app"},
    "jooble":     {"base_url": "https://jooble.org"},
    "reddit":     {"base_url": "https://reddit.com"},
    "eventbrite": {"base_url": "https://www.eventbriteapi.com"},
    
    # Tier 3 GitHub Open Source
    "simplify":   {"base_url": "https://github.com/SimplifyJobs"},
    "pittcsc":    {"base_url": "https://github.com/pittcsc"},
    "everjobs":   {"base_url": "https://github.com"},
}


def _get_fetch(provider: str):
    if provider == "adzuna":
        from jobs.providers.adzuna import fetch
    elif provider == "jooble":
        from jobs.providers.jooble import fetch
    elif provider == "reddit":
        from jobs.providers.reddit import fetch
    elif provider == "eventbrite":
        from jobs.providers.eventbrite import fetch
    elif provider == "remotive":
        from jobs.providers.remotive import fetch
    elif provider == "arbeitnow":
        from jobs.providers.arbeitnow import fetch
    elif provider == "jobicy":
        from jobs.providers.jobicy import fetch
    elif provider == "themuse":
        from jobs.providers.themuse import fetch
    elif provider == "himalayas":
        from jobs.providers.himalayas import fetch
    elif provider == "simplify":
        from jobs.github.simplify import fetch
    elif provider == "pittcsc":
        from jobs.github.pittcsc import fetch
    elif provider == "everjobs":
        from jobs.github.everjobs import fetch
    else:
        raise ValueError(f"Unknown provider: {provider}")
    return fetch


def collect_provider(provider: str, query: str = DEFAULT_QUERY, limit: int = 40) -> Dict[str, Any]:
    meta = PROVIDERS.get(provider)
    if not meta:
        return {"provider": provider, "status": "skipped", "reason": "unknown provider"}

    started = datetime.now(timezone.utc)
    fetch_fn = _get_fetch(provider)
    errors = []

    try:
        # Call fetch with correct signatures
        if provider in ("simplify", "pittcsc", "everjobs"):
            items = fetch_fn(limit=limit)
        elif provider == "adzuna":
            items = fetch_fn(query=query, page=1, results_per_page=limit)
        elif provider == "reddit":
            items = fetch_fn(query=query, limit=limit)
        else:
            items = fetch_fn(query=query, limit=limit)
    except Exception as e:
        items = []
        errors.append(str(e))

    received = len(items)
    created = updated = skipped = 0

    try:
        with DBConn() as conn:
            source_id = upsert_source(conn, provider, meta["base_url"])
            for raw in items:
                try:
                    unified     = normalize_unified(provider, raw)
                    company_id  = upsert_company(conn, unified["company_name"])
                    location_id = upsert_location(conn, unified["location_text"])
                    status = upsert_job(
                        conn,
                        external_id  = unified["external_id"],
                        source_id    = source_id,
                        company_id   = company_id,
                        location_id  = location_id,
                        title        = unified["title"],
                        description  = unified["description"],
                        external_url = unified["external_url"],
                        apply_url    = unified["external_url"],
                        work_type    = unified.get("work_type"),
                        is_remote    = unified.get("is_remote"),
                        is_hybrid    = unified.get("is_hybrid"),
                        skills       = list(unified.get("skills") or []),
                        posted_at    = unified.get("posted_at"),
                        parsed_metadata={"salary_formatted": unified.get("salary_formatted")},
                    )
                    if status == "created":
                        created += 1
                    elif status == "updated":
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append(str(e))
                    skipped += 1

            log_collection(
                conn, source_id,
                status="completed" if not errors else "completed_errors",
                started_at=started,
                jobs_requested=limit,
                jobs_received=received,
                jobs_created=created,
                jobs_updated=updated,
                jobs_skipped=skipped,
                errors=errors,
                params={"query": query, "limit": limit},
            )
    except Exception as e:
        errors.append(str(e))

    result = {
        "provider": provider,
        "created":  created,
        "updated":  updated,
        "skipped":  skipped,
        "received": received,
        "errors":   errors,
    }
    logger.info("collect_provider %s: %s", provider, result)
    return result


def collect_all(query: str = DEFAULT_QUERY, limit: int = 40) -> Dict[str, Any]:
    """
    Run all providers concurrently in a ThreadPoolExecutor to prevent blocking and lag.
    """
    results = {}
    # Run Reddit and Eventbrite as lower priority or include all
    active_keys = list(PROVIDERS.keys())
    
    with ThreadPoolExecutor(max_workers=min(len(active_keys), 12)) as executor:
        futures = {
            executor.submit(collect_provider, p, query=query, limit=limit): p 
            for p in active_keys
        }
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                results[p] = fut.result()
            except Exception as e:
                results[p] = {
                    "provider": p,
                    "created": 0,
                    "updated": 0,
                    "skipped": 0,
                    "received": 0,
                    "errors": [str(e)],
                }
    return results
