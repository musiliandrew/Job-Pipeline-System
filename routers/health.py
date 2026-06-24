"""routers/health.py — Liveness and readiness checks"""
from fastapi import APIRouter
from scheduler import get_job_statuses

router = APIRouter(tags=["Health"])


@router.get("/health")
def health():
    try:
        jobs = get_job_statuses()
        return {
            "status": "ok",
            "scheduler": "running",
            "scheduled_jobs": len(jobs),
            "jobs": jobs,
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}
