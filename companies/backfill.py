"""companies/backfill.py — Backfill missing company URLs using discovery."""
import logging
from typing import Dict

from db.connection import DBConn
from db.upserts import get_all_companies, update_company
from companies.discovery import choose_best_homepage, choose_best_careers

logger = logging.getLogger(__name__)


def backfill_missing_urls(limit: int = 200) -> Dict:
    results = {"processed": 0, "homepage_filled": 0, "careers_filled": 0, "errors": 0}

    with DBConn() as conn:
        companies = get_all_companies(conn, limit=limit)

    for c in companies:
        try:
            updates = {}
            name    = c.get("name") or ""
            if not name:
                continue

            if not c.get("website"):
                hp = choose_best_homepage(name, tier=c.get("tier"))
                if hp and hp.get("url"):
                    updates["website"] = hp["url"]
                    results["homepage_filled"] += 1

            if not c.get("careers_page_url"):
                cp = choose_best_careers(name, c.get("website"))
                if cp and cp.get("url"):
                    updates["careers_page_url"] = cp["url"]
                    results["careers_filled"] += 1

            if updates:
                with DBConn() as conn:
                    update_company(conn, str(c["id"]), updates)

            results["processed"] += 1
        except Exception as e:
            logger.error("backfill_missing_urls: company %s error: %s", c.get("id"), e)
            results["errors"] += 1

    logger.info("backfill_missing_urls: %s", results)
    return results
