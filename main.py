"""
main.py — FastAPI Data Ingestion System entry point.
Run with: uvicorn main:app --reload --port 8001
"""
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from routers import health, trigger, status, logs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from scheduler import start_scheduler, stop_scheduler
    logger.info("Starting Data Ingestion System scheduler...")
    start_scheduler()
    yield
    logger.info("Shutting down scheduler...")
    stop_scheduler()


app = FastAPI(
    title="CareerScope — Data Ingestion System",
    description=(
        "Standalone FastAPI service that collects job data from Adzuna, Jooble, "
        "Reddit, Eventbrite, and company ATS pages, then writes directly to PostgreSQL. "
        "No Django dependency. Scheduling via APScheduler."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(trigger.router)
app.include_router(status.router)
app.include_router(logs.router)


@app.get("/", tags=["Root"])
def root():
    return {
        "service": "CareerScope Data Ingestion System",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "trigger": "/trigger/{source}",
        "status": "/status",
        "logs": "/logs",
    }
