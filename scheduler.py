"""
scheduler.py — APScheduler-based background task runner.
Replaces all Celery Beat ingestion schedules from Django settings.py.
Handles Tier 1 APIs, Tier 2 ATS, Tier 3 GitHub, and company/news tasks.
"""
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = BackgroundScheduler(timezone="UTC")


# ─── Job collection tasks ──────────────────────────────────────────────────────

def _collect_free_apis_parallel():
    """Trigger all Tier 1 Free APIs in parallel."""
    from jobs.collector import collect_all
    logger.info("Starting concurrent Tier 1 Free API collection...")
    # Run the collector for the primary query
    result = collect_all()
    logger.info("Tier 1 Free API collection finished: %s", {k: {"created": v.get("created"), "errors": len(v.get("errors", []))} for k, v in result.items()})


def _collect_github_sources_parallel():
    """Trigger Tier 3 GitHub sources in parallel."""
    from jobs.collector import collect_provider
    import concurrent.futures
    logger.info("Starting concurrent Tier 3 GitHub sources collection...")
    sources = ["simplify", "pittcsc", "everjobs"]
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futs = {executor.submit(collect_provider, src, limit=100): src for src in sources}
        for fut in concurrent.futures.as_completed(futs):
            src = futs[fut]
            try:
                results[src] = fut.result()
            except Exception as e:
                results[src] = {"error": str(e)}
    logger.info("Tier 3 GitHub collection finished: %s", results)


def _collect_single_provider(provider: str):
    from jobs.collector import collect_provider
    result = collect_provider(provider)
    logger.info("Single provider collect %s: %s", provider, result)


def _ingest_ats_companies():
    from jobs.ats.ingest import ingest_all_hiring_companies
    result = ingest_all_hiring_companies(limit=100)
    logger.info("ats_companies: %s", result)


# ─── Company tasks ────────────────────────────────────────────────────────────

def _backfill_company_urls():
    try:
        from companies.backfill import backfill_missing_urls
        result = backfill_missing_urls(limit=200)
        logger.info("company_backfill: %s", result)
    except Exception as e:
        logger.error("company_backfill error: %s", e)


def _ingest_company_news():
    try:
        from companies.news import ingest_news_for_companies
        result = ingest_news_for_companies(limit_companies=50, items_per_company=5)
        logger.info("company_news: %s", result)
    except Exception as e:
        logger.error("company_news error: %s", e)


def _enrich_companies():
    try:
        from companies.enrich import enrich_missing_metadata
        result = enrich_missing_metadata(limit_companies=200)
        logger.info("company_enrich: %s", result)
    except Exception as e:
        logger.error("company_enrich error: %s", e)


# ─── News tasks ───────────────────────────────────────────────────────────────

def _ingest_rss_news():
    from news.rss_ingest import ingest_feeds
    from news.feeds import FEEDS
    result = ingest_feeds(FEEDS, max_items_per_feed=30)
    logger.info("rss_news: %s", result)


def _ingest_industry_dive():
    from news.industry_dive import ingest_industry_dive
    result = ingest_industry_dive(max_items=50)
    logger.info("industry_dive: %s", result)


def _ingest_industry_dive_topics():
    from news.industry_dive import ingest_industry_dive
    TOPIC_QUERIES = [
        "artificial intelligence", "machine learning", "data science",
        "software engineering", "large language models", "mlops",
        "vector database", "rag",
    ]
    total = {"created": 0, "skipped": 0}
    for q in TOPIC_QUERIES:
        r = ingest_industry_dive(max_items=25, query=q)
        total["created"] += r.get("created", 0)
        total["skipped"] += r.get("skipped", 0)
    logger.info("industry_dive_topics: %s", total)


# ─── Scheduler setup ──────────────────────────────────────────────────────────

def _mins(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _hours(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def start_scheduler():
    # Tier 1 Free REST APIs Run Parallel every 10 min
    free_api_interval = _mins("FREE_API_INTERVAL_MINUTES", 10)
    _scheduler.add_job(
        _collect_free_apis_parallel,
        IntervalTrigger(minutes=free_api_interval),
        id="free_apis_parallel",
        replace_existing=True
    )

    # Tier 3 GitHub Open Source Run Parallel every 6 hours
    github_interval = _hours("GITHUB_INTERVAL_HOURS", 6)
    _scheduler.add_job(
        _collect_github_sources_parallel,
        IntervalTrigger(hours=github_interval),
        id="github_sources_parallel",
        replace_existing=True
    )

    # Tier 2 ATS Public API run every 12 hours
    ats_interval = _hours("ATS_INTERVAL_HOURS", 12)
    _scheduler.add_job(
        _ingest_ats_companies,
        IntervalTrigger(hours=ats_interval),
        id="ats_companies",
        replace_existing=True
    )

    # Company & News Tasks
    _scheduler.add_job(_backfill_company_urls,     IntervalTrigger(hours=_hours("COMPANY_BACKFILL_INTERVAL_HOURS", 1)), id="company_backfill", replace_existing=True)
    _scheduler.add_job(_ingest_company_news,       IntervalTrigger(hours=_hours("COMPANY_NEWS_INTERVAL_HOURS", 6)),   id="company_news",       replace_existing=True)
    _scheduler.add_job(_enrich_companies,          IntervalTrigger(hours=_hours("COMPANY_ENRICHMENT_INTERVAL_HOURS", 24)), id="company_enrich", replace_existing=True)
    _scheduler.add_job(_ingest_rss_news,           IntervalTrigger(minutes=_mins("RSS_NEWS_INTERVAL_MINUTES", 20)),   id="rss_news",           replace_existing=True)
    _scheduler.add_job(_ingest_industry_dive,      IntervalTrigger(minutes=_mins("INDUSTRY_DIVE_INTERVAL_MINUTES", 10)), id="industry_dive",   replace_existing=True)
    _scheduler.add_job(_ingest_industry_dive_topics, IntervalTrigger(minutes=30),                                     id="industry_dive_topics", replace_existing=True)

    _scheduler.start()
    logger.info("DIS Scheduler started with %d jobs", len(_scheduler.get_jobs()))


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def get_job_statuses() -> list:
    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs.append({"id": job.id, "name": job.name, "next_run": next_run})
    return jobs


def trigger_job(job_id: str) -> bool:
    """Manually trigger a scheduled job or individual provider by ID."""
    fn_map = {
        "free_apis_parallel":     _collect_free_apis_parallel,
        "github_sources_parallel": _collect_github_sources_parallel,
        "ats_companies":          _ingest_ats_companies,
        "company_backfill":       _backfill_company_urls,
        "company_news":           _ingest_company_news,
        "company_enrich":         _enrich_companies,
        "rss_news":               _ingest_rss_news,
        "industry_dive":          _ingest_industry_dive,
        "industry_dive_topics":   _ingest_industry_dive_topics,
        
        # Individual provider stubs for on-demand trigger views
        "remotive":               lambda: _collect_single_provider("remotive"),
        "arbeitnow":              lambda: _collect_single_provider("arbeitnow"),
        "adzuna":                 lambda: _collect_single_provider("adzuna"),
        "jobicy":                 lambda: _collect_single_provider("jobicy"),
        "themuse":                lambda: _collect_single_provider("themuse"),
        "himalayas":              lambda: _collect_single_provider("himalayas"),
        "jooble":                 lambda: _collect_single_provider("jooble"),
        "reddit":                 lambda: _collect_single_provider("reddit"),
        "eventbrite":             lambda: _collect_single_provider("eventbrite"),
        "simplify":               lambda: _collect_single_provider("simplify"),
        "pittcsc":                lambda: _collect_single_provider("pittcsc"),
        "everjobs":               lambda: _collect_single_provider("everjobs"),
    }
    
    if job_id not in fn_map:
        return False
        
    try:
        fn_map[job_id]()
    except Exception as e:
        logger.error("trigger_job %s error: %s", job_id, e)
    return True
