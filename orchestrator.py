"""
orchestrator.py — Data-driven Task Generation Engine

Instead of executing scrapers directly, the Orchestrator reads from the database,
calculates dynamic "Scheduling Scores", and pushes execution tasks to the EventBus.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

from events.bus import event_bus
from db.connection import DBConn
import psycopg2.extras

logger = logging.getLogger(__name__)

def _calculate_scheduling_score(source: Dict[str, Any]) -> float:
    """
    Scheduling Score = (Priority * Freshness Factor) - Failure Penalty
    """
    priority = source.get("priority", 50)
    health_score = source.get("health_score", 100)
    
    # Base score
    score = float(priority)
    
    # Penalize unhealthy sources
    if health_score < 50:
        score -= (100 - health_score) * 0.5
        
    return max(0.0, score)

def orchestrate_tier(tier_name: str) -> dict:
    """
    Finds all sources in a given tier, calculates their scheduling scores,
    sorts them, and publishes scrape tasks to the 'scrape-tasks' queue.
    """
    logger.info(f"Orchestrating tier: {tier_name}")
    
    with DBConn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.id as source_id, s.name, p.name as provider_name,
                       m.priority, m.health_score, m.last_successful_scrape,
                       m.last_job_id_seen, m.etag,
                       p.pagination_strategy, p.supports_etag, p.supports_cursor_pagination
                FROM scrape_metadata m
                JOIN job_sources s ON s.id = m.source_id
                LEFT JOIN job_providers p ON p.id = s.provider_id
                WHERE m.tier = %s AND s.is_active = TRUE
                """,
                (tier_name,)
            )
            sources = [dict(row) for row in cur.fetchall()]
            
    if not sources:
        return {"tier": tier_name, "tasks_generated": 0}
        
    # 1. Calculate Scheduling Scores
    for src in sources:
        src["scheduling_score"] = _calculate_scheduling_score(src)
        
    # 2. Sort by highest score first
    sources.sort(key=lambda x: x["scheduling_score"], reverse=True)
    
    # 3. Publish Tasks to Queue
    tasks_generated = 0
    for src in sources:
        task_payload = {
            "source_id": src["source_id"],
            "source_name": src["name"],
            "provider": src["provider_name"] or "unknown",
            "tier": tier_name,
            "capabilities": {
                "pagination_strategy": src["pagination_strategy"],
                "supports_etag": src["supports_etag"],
                "supports_cursor": src["supports_cursor_pagination"],
                "last_job_id": src["last_job_id_seen"],
                "etag": src["etag"]
            }
        }
        
        # Publish to the internal task queue instead of executing directly
        success = event_bus.publish(
            topic="scrape-tasks", 
            event_type="execute_scrape", 
            payload=task_payload
        )
        
        if success:
            tasks_generated += 1
            
    logger.info(f"Successfully orchestrated {tasks_generated} tasks for tier '{tier_name}'")
    return {
        "tier": tier_name,
        "sources_evaluated": len(sources),
        "tasks_queued": tasks_generated
    }
