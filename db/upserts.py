"""
db/upserts.py — Raw SQL upsert helpers for all DIS writes.
Replaces Django ORM calls. Writes to the same PostgreSQL schema owned by Django migrations.
"""
import uuid
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib

import psycopg2.extras
from events.bus import event_bus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(text: str) -> str:
    """Simple slug — mirrors Django's slugify for company names."""
    t = text.lower().strip()
    t = re.sub(r"[^\w\s-]", "", t)
    t = re.sub(r"[\s_-]+", "-", t)
    t = re.sub(r"^-+|-+$", "", t)
    return t[:255]


# ─── JobSources ───────────────────────────────────────────────────────────────

def upsert_source(conn, name: str, base_url: str) -> int:
    """Get or create a job_sources row. Returns the integer id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO job_sources (name, base_url, is_active, created_at)
            VALUES (%s, %s, TRUE, %s)
            ON CONFLICT (name) DO UPDATE SET base_url = EXCLUDED.base_url
            RETURNING id
            """,
            (name[:50], base_url, _now()),
        )
        return cur.fetchone()[0]


def get_scrape_metadata(conn, source_id: int) -> Dict[str, Any]:
    """Retrieve operational metadata for a job source to support incremental scraping."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT tier, last_successful_scrape, last_job_id_seen, 
                   etag, average_update_frequency
            FROM scrape_metadata
            WHERE source_id = %s
            """,
            (source_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def update_scrape_metadata(conn, source_id: int, updates: Dict[str, Any]) -> None:
    """Update checkpoints for adaptive scheduling."""
    if not updates:
        return
        
    allowed = {"tier", "last_successful_scrape", "last_job_id_seen", "etag", "jobs_found_last_run"}
    valid_updates = {k: v for k, v in updates.items() if k in allowed}
    
    if not valid_updates:
        return
        
    # Generate ON CONFLICT DO UPDATE SET string dynamically
    set_parts = [f"{k} = EXCLUDED.{k}" for k in valid_updates.keys()]
    set_parts.append("updated_at = EXCLUDED.updated_at")
    
    # We must insert a new uuid if the row doesn't exist yet
    columns = ["id", "source_id", "updated_at"] + list(valid_updates.keys())
    values = [str(uuid.uuid4()), source_id, _now()] + list(valid_updates.values())
    
    placeholders = ", ".join(["%s"] * len(columns))
    
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO scrape_metadata ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (source_id) DO UPDATE SET {', '.join(set_parts)}
            """,
            values
        )


# ─── Companies ────────────────────────────────────────────────────────────────

def upsert_company(conn, name: str) -> str:
    """Get or create a companies row. Returns UUID as string."""
    n = (name or "Unknown Company").strip()[:255]
    slug = _slugify(n)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO companies (id, name, slug, is_actively_hiring, created_at, updated_at)
            VALUES (%s, %s, %s, TRUE, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            (str(uuid.uuid4()), n, slug, _now(), _now()),
        )
        return str(cur.fetchone()[0])


# ─── Locations ────────────────────────────────────────────────────────────────

def upsert_location(conn, location_text: str) -> int:
    """Get or create a locations row. Returns bigint id."""
    t = (location_text or "Remote").strip() or "Remote"
    is_remote = t.lower() == "remote"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO locations (city, state, country, country_code, is_remote, created_at, updated_at)
            VALUES (%s, NULL, %s, 'XX', %s, %s, %s)
            ON CONFLICT (city, state, country)
            DO UPDATE SET is_remote = EXCLUDED.is_remote
            RETURNING id
            """,
            (t, t, is_remote, _now(), _now()),
        )
        return cur.fetchone()[0]


def upsert_location_full(
    conn,
    city: str,
    state: Optional[str],
    country: str,
    country_code: str = "XX",
    is_remote: bool = False,
) -> int:
    """Upsert a fully-specified location. Returns bigint id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO locations (city, state, country, country_code, is_remote, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (city, state, country)
            DO UPDATE SET state = EXCLUDED.state, is_remote = EXCLUDED.is_remote
            RETURNING id
            """,
            (city or "Remote", state, country or "Remote",
             country_code[:2].upper() if country_code else "XX", is_remote, _now(), _now()),
        )
        return cur.fetchone()[0]


# ─── Jobs ─────────────────────────────────────────────────────────────────────

def _freshness_score(posted_at: Optional[datetime]) -> tuple[int, bool]:
    """Return (freshness_score, is_fresh) — mirrors Jobs.update_freshness_score()."""
    if not posted_at:
        return 0, False
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - posted_at).total_seconds() / 3600
    if age_h < 24:
        return 100, True
    if age_h < 48:
        return 75, True
    if age_h < 72:
        return 50, False
    if age_h < 168:
        return 25, False
    return 0, False


def upsert_job(
    conn,
    *,
    external_id: str,
    source_id: int,
    company_id: str,
    location_id: str,
    title: str,
    description: str = "",
    external_url: str = "",
    apply_url: str = "",
    work_type: Optional[str] = None,
    skills: Optional[List[str]] = None,
    salary_min: Optional[float] = None,
    salary_max: Optional[float] = None,
    salary_currency: Optional[str] = None,
    salary_period: Optional[str] = None,
    is_remote: Optional[bool] = None,
    is_hybrid: Optional[bool] = None,
    experience_level: Optional[str] = None,
    categories: Optional[List[str]] = None,
    technologies: Optional[List[str]] = None,
    posted_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    parsed_metadata: Optional[Dict] = None,
    raw_data: Optional[Dict] = None,
) -> str:
    """Insert or update a job row. Returns 'created' or 'updated'."""
    now = _now()
    posted_at = posted_at or now
    freshness, fresh = _freshness_score(posted_at)
    slug = title[:255]
    skills_arr = skills or []
    tech_arr = technologies or []
    cats_arr = categories or []
    
    # Generate deterministic deduplication hash
    hash_input = f"{external_url}{company_id}{title}".encode("utf-8")
    job_hash = hashlib.sha256(hash_input).hexdigest()

    with conn.cursor() as cur:
        # Check if exists
        cur.execute(
            "SELECT id FROM jobs WHERE job_hash = %s OR (external_id = %s AND source_id = %s)",
            (job_hash, external_id[:255], source_id),
        )
        row = cur.fetchone()

        if row:
            cur.execute(
                """
                UPDATE jobs SET
                    company_id = %s, location_id = %s, title = %s, slug = %s,
                    description = COALESCE(NULLIF(description, ''), %s),
                    external_url = %s, apply_url = %s, work_type = COALESCE(work_type, %s),
                    skills = CASE WHEN skills IS NULL OR skills = '{}' THEN %s ELSE skills END,
                    salary_min = COALESCE(salary_min, %s),
                    salary_max = COALESCE(salary_max, %s),
                    salary_currency = COALESCE(salary_currency, %s),
                    salary_period = COALESCE(salary_period, %s),
                    is_remote = COALESCE(is_remote, %s),
                    is_hybrid = COALESCE(is_hybrid, %s),
                    experience_level = COALESCE(experience_level, %s),
                    categories = CASE WHEN categories IS NULL OR categories = '{}' THEN %s ELSE categories END,
                    technologies = CASE WHEN technologies IS NULL OR technologies = '{}' THEN %s ELSE technologies END,
                    expires_at = COALESCE(expires_at, %s),
                    parsed_metadata = COALESCE(parsed_metadata, %s::jsonb),
                    status = 'active',
                    source_updated_at = %s, last_verified_at = %s,
                    freshness_score = %s, is_fresh = %s, last_freshness_update = %s,
                    updated_at = %s, job_hash = %s
                WHERE id = %s
                """,
                (
                    company_id, location_id, title[:255], slug,
                    description, external_url, apply_url, work_type,
                    skills_arr, salary_min, salary_max, salary_currency,
                    salary_period, is_remote, is_hybrid, experience_level,
                    cats_arr, tech_arr, expires_at,
                    psycopg2.extras.Json(parsed_metadata) if parsed_metadata else None,
                    now, now, freshness, fresh, now, now, job_hash,
                    row[0],
                ),
            )
            return "updated"
        else:
            job_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO jobs (
                    id, external_id, source_id, company_id, location_id,
                    title, slug, description, external_url, apply_url,
                    work_type, skills, salary_min, salary_max,
                    salary_currency, salary_period, is_remote, is_hybrid,
                    experience_level, categories, technologies,
                    expires_at, parsed_metadata, raw_data,
                    status, posted_at, source_updated_at, ingested_at,
                    last_verified_at, freshness_score, is_fresh,
                    last_freshness_update, created_at, updated_at, job_hash
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s::jsonb, %s::jsonb,
                    'active', %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    job_id, external_id[:255], source_id, company_id, location_id,
                    title[:255], slug, description, external_url, apply_url,
                    work_type, skills_arr, salary_min, salary_max,
                    salary_currency, salary_period, is_remote, is_hybrid,
                    experience_level, cats_arr, tech_arr,
                    expires_at,
                    psycopg2.extras.Json(parsed_metadata) if parsed_metadata else None,
                    psycopg2.extras.Json(raw_data) if raw_data else None,
                    posted_at, now, now,
                    now, freshness, fresh,
                    now, now, now, job_hash,
                ),
            )
            
            # Event-Driven Publication: Transactional Outbox Pattern
            # Insert into outbox_events within the SAME database transaction.
            outbox_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO outbox_events (id, topic, event_type, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    outbox_id,
                    "raw-jobs",
                    "job_created",
                    psycopg2.extras.Json({
                        "job_id": job_id,
                        "title": title,
                        "description": description,
                        "company_id": company_id,
                        "external_url": external_url
                    })
                )
            )
            
            return "created"


def update_job_fields(conn, job_id: str, fields: Dict[str, Any]) -> None:
    """Update specific fields on an existing job by UUID."""
    if not fields:
        return
    allowed = {
        "description", "work_type", "experience_level", "is_remote", "is_hybrid",
        "salary_min", "salary_max", "salary_currency", "salary_period",
        "skills", "technologies", "categories", "expires_at", "posted_at",
        "location_id",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_parts = [f"{k} = %s" for k in updates]
    set_parts.append("updated_at = %s")
    values = list(updates.values()) + [_now(), job_id]
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = %s",
            values,
        )


def get_jobs_needing_enrichment(conn, company_id: str, limit: int = 100) -> List[Dict]:
    """Return jobs missing description or salary for a given company."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT j.id, j.title, j.apply_url, j.external_url,
                   j.description, j.salary_min, j.salary_max,
                   j.is_remote, j.is_hybrid, j.salary_currency,
                   j.salary_period, j.work_type, j.expires_at,
                   j.skills, j.technologies, j.categories,
                   j.posted_at, j.parsed_metadata,
                   js.name AS source_name,
                   l.city AS location_city
            FROM jobs j
            JOIN job_sources js ON js.id = j.source_id
            LEFT JOIN locations l ON l.id = j.location_id
            WHERE j.company_id = %s
              AND j.status = 'active'
              AND (
                  j.description IS NULL OR j.description = ''
                  OR j.salary_min IS NULL
                  OR j.salary_max IS NULL
                  OR j.expires_at IS NULL
              )
            ORDER BY j.posted_at DESC
            LIMIT %s
            """,
            (company_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]


# ─── Collection Logs ──────────────────────────────────────────────────────────

def log_collection(
    conn,
    source_id: int,
    status: str,
    started_at: datetime,
    jobs_requested: int = 0,
    jobs_received: int = 0,
    jobs_created: int = 0,
    jobs_updated: int = 0,
    jobs_skipped: int = 0,
    errors: Optional[List[str]] = None,
    params: Optional[Dict] = None,
) -> None:
    now = _now()
    duration = int((now - started_at).total_seconds())
    err_count = len(errors) if errors else 0
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO job_collection_logs (
                id, source_id, status, started_at, completed_at,
                duration_seconds, jobs_requested, jobs_received,
                jobs_created, jobs_updated, jobs_skipped,
                errors_count, error_details, collection_params
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                str(uuid.uuid4()), source_id, status[:20], started_at, now,
                duration, jobs_requested, jobs_received,
                jobs_created, jobs_updated, jobs_skipped,
                err_count,
                psycopg2.extras.Json({"errors": errors}) if errors else None,
                psycopg2.extras.Json(params) if params else None,
            ),
        )


# ─── News ─────────────────────────────────────────────────────────────────────

def upsert_news_article(conn, article: Dict) -> str:
    """Insert or skip a news article. Returns 'created' or 'skipped'."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM news_articles WHERE url = %s", (article["url"],))
        if cur.fetchone():
            return "skipped"
        cur.execute(
            """
            INSERT INTO news_articles (
                id, title, url, source, published_at, content,
                summary, category, tags, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                (article.get("title") or "")[:500],
                article["url"],
                (article.get("source") or "")[:100],
                article.get("published_at") or _now(),
                article.get("content") or "",
                article.get("summary") or "",
                (article.get("category") or "")[:100],
                article.get("tags") or [],
                _now(),
            ),
        )
        return "created"


# ─── Company helpers ──────────────────────────────────────────────────────────

def get_actively_hiring_companies(conn, limit: int = 100) -> List[Dict]:
    """Return companies marked as actively hiring."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, slug, website, careers_page_url
            FROM companies
            WHERE is_actively_hiring = TRUE
            ORDER BY updated_at DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_all_companies(conn, limit: int = 200) -> List[Dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, name, slug, website, careers_page_url, tier FROM companies ORDER BY updated_at DESC NULLS LAST LIMIT %s",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def update_company(conn, company_id: str, fields: Dict[str, Any]) -> None:
    if not fields:
        return
    allowed = {
        "website", "careers_page_url", "logo_url", "is_actively_hiring",
        "last_job_scrape", "last_news_check", "active_jobs_count",
        "total_jobs_posted", "jobs_last_30_days", "data_freshness_score",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    set_parts = [f"{k} = %s" for k in updates]
    values = list(updates.values()) + [company_id]
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE companies SET {', '.join(set_parts)} WHERE id = %s",
            values,
        )


def log_company_monitoring(
    conn,
    company_id: str,
    job_type: str,
    status: str,
    started_at: datetime,
    items_processed: int = 0,
    items_created: int = 0,
    items_updated: int = 0,
    errors_count: int = 0,
    parameters: Optional[Dict] = None,
    results: Optional[Dict] = None,
    error_details: Optional[str] = None,
) -> None:
    now = _now()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_monitoring_jobs (
                id, company_id, job_type, status, started_at, completed_at,
                duration_seconds, items_processed, items_created, items_updated,
                errors_count, parameters, results, error_details, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """,
            (
                str(uuid.uuid4()), company_id, job_type[:30], status[:20],
                started_at, now,
                int((now - started_at).total_seconds()),
                items_processed, items_created, items_updated, errors_count,
                psycopg2.extras.Json(parameters) if parameters else None,
                psycopg2.extras.Json(results) if results else None,
                error_details, now,
            ),
        )
