"""routers/companies.py — On-Demand Company Discovery Endpoint"""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from db.connection import DBConn
from db.upserts import upsert_company
from companies.discovery import choose_best_homepage, choose_best_careers
# Assume enrich.py can also just enrich a single company by ID, but currently it takes limit
# We will do basic discovery and db update here, then rely on the scheduler to run full enrich later, 
# or we can call a specific enrichment logic.
# For now, let's just do discovery.

router = APIRouter(prefix="/companies", tags=["Companies"])
logger = logging.getLogger(__name__)

class DiscoverRequest(BaseModel):
    company_id: str
    company_name: str

def discover_and_enrich_task(company_id: str, company_name: str):
    """Background task to discover company URLs and update the DB."""
    logger.info(f"Starting discovery for {company_name} ({company_id})")
    try:
        homepage_data = choose_best_homepage(company_name)
        homepage_url = homepage_data.get("url") if homepage_data else None
        
        careers_data = choose_best_careers(company_name, homepage_url) if homepage_url else None
        careers_url = careers_data.get("url") if careers_data else None

        updates = {
            "website": homepage_url,
            "careers_page_url": careers_url,
            "is_monitored": True
        }

        # Remove None values
        updates = {k: v for k, v in updates.items() if v is not None}

        if updates:
            with DBConn() as conn:
                from db.upserts import update_company
                update_company(conn, company_id, updates)
            logger.info(f"Updated {company_name} with: {updates}")
        else:
            logger.warning(f"Could not discover URLs for {company_name}")

    except Exception as e:
        logger.error(f"Error during discovery for {company_name}: {e}")

@router.post("/discover")
def discover_company(req: DiscoverRequest, background_tasks: BackgroundTasks):
    """
    Called by the Django backend when a user follows a company that is not yet fully profiled.
    """
    logger.info(f"Received discovery request for company: {req.company_name}")
    background_tasks.add_task(discover_and_enrich_task, req.company_id, req.company_name)
    return {"status": "accepted", "message": f"Discovery task started for {req.company_name}"}
