"""jobs/ats/ingest.py — Ported from DataIngestion/Jobs/ingest.py (Django ORM removed)"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urlparse

from db.connection import DBConn
from db.upserts import (
    upsert_source, upsert_company, upsert_location, upsert_job,
    get_actively_hiring_companies, log_company_monitoring,
)
from jobs.ats.workday import is_workday_url, extract_jobs_from_workday
from jobs.ats.greenhouse import is_greenhouse_url, extract_jobs_from_greenhouse
from jobs.ats.lever import is_lever_url, extract_jobs_from_lever
from jobs.ats.ashby import is_ashby_url, extract_jobs_from_ashby
from jobs.ats.generic import extract_jobs_from_generic
from jobs.ats.ai_extractor import extract_jobs_ai
from companies.discovery import resolve_careers_candidates, choose_best_careers

logger = logging.getLogger(__name__)

ATS_SOURCES = {
    "workday":    "https://wd1.myworkdayjobs.com",
    "greenhouse": "https://boards.greenhouse.io",
    "lever":      "https://jobs.lever.co",
    "ashby":      "https://jobs.ashbyhq.com",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generic_source_name(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower() or "generic"
    except Exception:
        return "generic"


def ingest_company_jobs(company_id: str) -> Dict:
    started = _now()
    results: Dict = {
        "company_id":  company_id,
        "created":     0,
        "updated":     0,
        "skipped":     0,
        "provider":    None,
        "chosen_url":  None,
        "candidates":  [],
    }

    try:
        with DBConn() as conn:
            # Fetch company record
            from db.connection import get_conn, put_conn
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, name, website, careers_page_url FROM companies WHERE id = %s",
                (company_id,),
            )
            company = dict(cur.fetchone() or {})
            cur.close()
            if not company:
                logger.warning("ingest_company_jobs: company %s not found", company_id)
                return results

            # Prepare ATS sources
            src_ids = {}
            for ats, base in ATS_SOURCES.items():
                src_ids[ats] = upsert_source(conn, ats, base)
            default_location_id = upsert_location(conn, "Remote")

            # Resolve careers URL candidates
            careers_url = company.get("careers_page_url")
            if not careers_url:
                pick = choose_best_careers(company["name"], company.get("website"))
                careers_url = (pick or {}).get("url")

            candidates = resolve_careers_candidates(
                company["name"], company.get("website"), careers_url
            )
            results["candidates"] = candidates

            items: List[Dict] = []
            provider = None
            source_id = src_ids.get("workday")

            for cand in candidates:
                if is_workday_url(cand):
                    extracted = extract_jobs_from_workday(cand) or []
                    if extracted:
                        provider, source_id, items = "workday", src_ids["workday"], extracted
                        results["chosen_url"] = cand
                        break
                if is_greenhouse_url(cand):
                    extracted = extract_jobs_from_greenhouse(cand) or []
                    if extracted:
                        provider, source_id, items = "greenhouse", src_ids["greenhouse"], extracted
                        results["chosen_url"] = cand
                        break
                if is_lever_url(cand):
                    extracted = extract_jobs_from_lever(cand) or []
                    if extracted:
                        provider, source_id, items = "lever", src_ids["lever"], extracted
                        results["chosen_url"] = cand
                        break
                if is_ashby_url(cand):
                    extracted = extract_jobs_from_ashby(cand) or []
                    if extracted:
                        provider, source_id, items = "ashby", src_ids["ashby"], extracted
                        results["chosen_url"] = cand
                        break
                extracted = extract_jobs_ai(cand) or []
                if extracted:
                    host     = (_generic_source_name(cand) or "ai")
                    provider = f"ai:{host}"
                    source_id = upsert_source(conn, provider[:50], f"https://{host}")
                    items    = extracted
                    results["chosen_url"] = cand
                    break
                extracted = extract_jobs_from_generic(cand) or []
                if extracted:
                    host     = _generic_source_name(cand)
                    provider = f"generic:{host}"
                    source_id = upsert_source(conn, provider[:50], f"https://{host}")
                    items    = extracted
                    results["chosen_url"] = cand
                    break

            results["provider"] = provider
            created = updated = skipped = 0

            company_id_for_upsert = upsert_company(conn, company["name"])

            for it in items:
                try:
                    title = (it.get("title") or "Job")[:255]
                    desc = it.get("description") or ""
                    loc = it.get("location_text") or "Remote"
                    item_work_type = (it.get("work_type") or "").lower()
                    
                    loc_lower = loc.lower()
                    text_lower = f"{title} {desc}".lower()
                    
                    is_hybrid = "hybrid" in loc_lower or "hybrid" in text_lower or item_work_type == "hybrid"
                    if is_hybrid:
                        is_remote = False
                    else:
                        is_remote = (
                            "remote" in loc_lower or
                            "remote" in text_lower or
                            item_work_type == "remote" or
                            any(w in loc_lower for w in ["anywhere", "worldwide", "wfh"])
                        )
                    work_type = "hybrid" if is_hybrid else ("remote" if is_remote else "onsite")

                    status = upsert_job(
                        conn,
                        external_id  = it.get("external_id") or it.get("apply_url") or str(uuid.uuid4()),
                        source_id    = source_id,
                        company_id   = company_id_for_upsert,
                        location_id  = default_location_id,
                        title        = title,
                        external_url = it.get("apply_url") or "",
                        apply_url    = it.get("apply_url") or "",
                        description  = desc,
                        work_type    = work_type,
                        is_remote    = is_remote,
                        is_hybrid    = is_hybrid,
                    )
                    if status == "created":
                        created += 1
                    elif status == "updated":
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.error("ingest_company_jobs upsert error: %s", e)
                    skipped += 1

            log_company_monitoring(
                conn, company_id, "jobs_ingest", "completed", started,
                items_processed=len(items),
                items_created=created,
                items_updated=updated,
                parameters={"company_id": company_id},
                results={**results, "created": created, "updated": updated, "skipped": skipped},
            )

        results.update({"created": created, "updated": updated, "skipped": skipped})
        return results

    except Exception as e:
        logger.error("ingest_company_jobs failed for %s: %s", company_id, e)
        try:
            with DBConn() as conn:
                log_company_monitoring(
                    conn, company_id, "jobs_ingest", "failed", started,
                    errors_count=1, error_details=str(e), parameters={"company_id": company_id},
                )
        except Exception:
            pass
        raise


def ingest_all_hiring_companies(limit: int = 100) -> Dict:
    """Ingest jobs for all actively hiring companies."""
    summary = {"companies": 0, "created": 0, "updated": 0, "skipped": 0}
    with DBConn() as conn:
        companies = get_actively_hiring_companies(conn, limit=limit)
    for c in companies:
        try:
            res = ingest_company_jobs(str(c["id"]))
            summary["companies"] += 1
            summary["created"]   += res.get("created", 0)
            summary["updated"]   += res.get("updated", 0)
            summary["skipped"]   += res.get("skipped", 0)
        except Exception as e:
            logger.error("ingest_all_hiring_companies: company %s failed: %s", c["id"], e)
    logger.info("ingest_all_hiring_companies: %s", summary)
    return summary
