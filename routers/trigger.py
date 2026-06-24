"""routers/trigger.py — Manually fire any ingestion job via HTTP POST"""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks

from scheduler import trigger_job

router = APIRouter(prefix="/trigger", tags=["Trigger"])
logger = logging.getLogger(__name__)

VALID_SOURCES = [
    "free_apis_parallel", "github_sources_parallel", "ats_companies",
    "company_backfill", "company_news", "company_enrich",
    "rss_news", "industry_dive", "industry_dive_topics",
    
    # Individual provider stubs
    "remotive", "arbeitnow", "adzuna", "jobicy", "themuse", "himalayas", "jooble",
    "reddit", "eventbrite", "simplify", "pittcsc", "everjobs",
]


@router.post("/{source}")
def trigger(source: str, background_tasks: BackgroundTasks):
    """
    Manually trigger an ingestion job by source name.
    """
    if source not in VALID_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown source '{source}'. Valid options: {VALID_SOURCES}",
        )
    background_tasks.add_task(trigger_job, source)
    logger.info("Manual trigger: %s", source)
    return {"triggered": source, "status": "queued"}


@router.get("/")
def list_sources():
    return {"sources": VALID_SOURCES}
