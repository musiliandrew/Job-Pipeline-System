"""
scheduler.py — APScheduler-based background task runner (for Local Development ONLY).
In production (GCP), scheduling is handled natively by Cloud Scheduler, and this file is inactive.
"""
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from executor import (
    _collect_free_apis_parallel,
    _collect_github_sources_parallel,
    _ingest_ats_companies,
    _backfill_company_urls,
    _ingest_company_news,
    _enrich_companies,
    _ingest_rss_news,
    _ingest_industry_dive,
    _ingest_industry_dive_topics
)

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = BackgroundScheduler(timezone="UTC")

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
    logger.info("Local Development Scheduler started with %d jobs", len(_scheduler.get_jobs()))


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def get_job_statuses() -> list:
    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs.append({"id": job.id, "name": job.name, "next_run": next_run})
    return jobs
