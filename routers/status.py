"""routers/status.py — Per-source collection stats from job_collection_logs"""
from fastapi import APIRouter
from db.connection import DBConn

router = APIRouter(prefix="/status", tags=["Status"])


@router.get("/")
def get_status(limit: int = 20):
    """Return last N collection log entries per source with aggregate stats."""
    try:
        with DBConn() as conn:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT
                    js.name AS source,
                    COUNT(*) AS total_runs,
                    MAX(jcl.completed_at) AS last_run,
                    SUM(jcl.jobs_created) AS total_created,
                    SUM(jcl.jobs_updated) AS total_updated,
                    SUM(jcl.errors_count) AS total_errors,
                    MAX(jcl.status) AS last_status
                FROM job_collection_logs jcl
                JOIN job_sources js ON js.id = jcl.source_id
                GROUP BY js.name
                ORDER BY last_run DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        return {"sources": rows}
    except Exception as e:
        return {"error": str(e)}


@router.get("/{source}")
def get_source_status(source: str, limit: int = 10):
    """Return recent collection log entries for a specific source."""
    try:
        with DBConn() as conn:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT jcl.*, js.name AS source_name
                FROM job_collection_logs jcl
                JOIN job_sources js ON js.id = jcl.source_id
                WHERE js.name = %s
                ORDER BY jcl.started_at DESC
                LIMIT %s
                """,
                (source, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        return {"source": source, "logs": rows}
    except Exception as e:
        return {"error": str(e)}
