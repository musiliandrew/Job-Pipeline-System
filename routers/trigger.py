"""routers/trigger.py — Manually fire any ingestion job via HTTP POST"""
import logging
from fastapi import APIRouter, HTTPException

from orchestrator import orchestrate_tier

router = APIRouter(prefix="/trigger", tags=["Trigger"])
logger = logging.getLogger(__name__)

VALID_TIERS = {"hot", "warm", "cold", "archive"}

@router.post("/tier/{tier_name}")
def trigger_tier(tier_name: str):
    """
    Cloud Scheduler hits this endpoint to evaluate and queue a tier of scrapers.
    It does not scrape synchronously. It pushes tasks to Pub/Sub.
    """
    tier_name = tier_name.lower()
    if tier_name not in VALID_TIERS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown tier '{tier_name}'. Valid options: {VALID_TIERS}",
        )
        
    logger.info("Triggering orchestration for tier: %s", tier_name)
    
    try:
        result = orchestrate_tier(tier_name)
        return result
    except Exception as e:
        logger.error("Error orchestrating tier %s: %s", tier_name, str(e))
        raise HTTPException(status_code=500, detail=f"Orchestration error: {str(e)}")


@router.get("/")
def list_sources():
    return {"sources": list(VALID_TIERS)}
