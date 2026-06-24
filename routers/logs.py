"""routers/logs.py — Raw collection log entries"""
from fastapi import APIRouter
from db.connection import DBConn

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("/")
def get_logs(limit: int = 50, source: str = None):
    """Return recent job collection log entries. Filter by source name optionally."""
    try:
        with DBConn() as conn:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if source:
                cur.execute(
                    """
                    SELECT jcl.id, js.name AS source, jcl.status,
                           jcl.started_at, jcl.completed_at, jcl.duration_seconds,
                           jcl.jobs_created, jcl.jobs_updated, jcl.jobs_skipped,
                           jcl.errors_count
                    FROM job_collection_logs jcl
                    JOIN job_sources js ON js.id = jcl.source_id
                    WHERE js.name = %s
                    ORDER BY jcl.started_at DESC
                    LIMIT %s
                    """,
                    (source, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT jcl.id, js.name AS source, jcl.status,
                           jcl.started_at, jcl.completed_at, jcl.duration_seconds,
                           jcl.jobs_created, jcl.jobs_updated, jcl.jobs_skipped,
                           jcl.errors_count
                    FROM job_collection_logs jcl
                    JOIN job_sources js ON js.id = jcl.source_id
                    ORDER BY jcl.started_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        return {"count": len(rows), "logs": rows}
    except Exception as e:
        return {"error": str(e)}
