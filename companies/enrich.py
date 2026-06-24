"""companies/enrich.py — Enrich company metadata (logo_url, etc.)"""
import logging
from typing import Dict

from db.connection import DBConn
from db.upserts import get_all_companies, update_company

logger = logging.getLogger(__name__)


def enrich_missing_metadata(limit_companies: int = 200) -> Dict:
    results = {"processed": 0, "enriched": 0, "errors": 0}

    with DBConn() as conn:
        companies = get_all_companies(conn, limit=limit_companies)

    for c in companies:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        try:
            updates = {}
            # Logo enrichment via Clearbit (if available)
            website = c.get("website")
            if website and not c.get("logo_url"):
                from urllib.parse import urlparse
                domain = (urlparse(website).netloc or "").replace("www.", "")
                if domain:
                    candidate = f"https://logo.clearbit.com/{domain}"
                    try:
                        import requests
                        r = requests.head(candidate, timeout=5)
                        if r.status_code == 200:
                            updates["logo_url"] = candidate
                    except Exception:
                        pass
            if updates:
                with DBConn() as conn:
                    update_company(conn, str(c["id"]), updates)
                results["enriched"] += 1
            results["processed"] += 1
        except Exception as e:
            logger.error("enrich_missing_metadata: %s error: %s", c.get("id"), e)
            results["errors"] += 1

    logger.info("enrich_missing_metadata: %s", results)
    return results
