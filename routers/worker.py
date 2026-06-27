"""
routers/worker.py — Distributed Scraper Worker Endpoint

Consumes HTTP POST push events from the internal 'scrape-tasks' Pub/Sub queue.
This allows Cloud Run to horizontally scale workers independently of the Orchestrator.
"""
import logging
import base64
import json
from fastapi import APIRouter, HTTPException, Request, Response

from executor import execute_job

router = APIRouter(prefix="/worker", tags=["Worker"])
logger = logging.getLogger(__name__)

@router.post("/consume")
async def consume_task(request: Request):
    """
    Pub/Sub Push endpoint for executing an individual scrape task.
    """
    try:
        envelope = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if "message" not in envelope:
        raise HTTPException(status_code=400, detail="Not a valid Pub/Sub message format")

    message = envelope["message"]
    if "data" not in message:
        logger.error("Pub/Sub message missing 'data' field.")
        return Response(status_code=204)  # Ack to prevent infinite retries of bad message

    try:
        decoded_data = base64.b64decode(message["data"]).decode("utf-8")
        task_payload = json.loads(decoded_data)
    except Exception as e:
        logger.error(f"Failed to decode message data: {e}")
        return Response(status_code=204)

    source_id = task_payload.get("source_id")
    source_name = task_payload.get("source_name")
    capabilities = task_payload.get("capabilities", {})
    
    if not source_name:
        logger.error("Task payload missing 'source_name'. Cannot execute.")
        return Response(status_code=204)

    logger.info(f"Worker received task for source: {source_name} | Capabilities: {capabilities}")

    try:
        # Pass the capabilities to the executor so it can use etag, cursor pagination, etc.
        # Note: execute_job must be modified to accept **capabilities if needed
        success = execute_job(source_name)
        if not success:
            logger.error(f"Execution failed for {source_name}")
            raise HTTPException(status_code=500, detail="Internal worker error")
            
    except Exception as e:
        logger.error(f"Worker crashed executing {source_name}: {str(e)}")
        # Raise 500 so Pub/Sub triggers exponential backoff & retry
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Successfully processed task for {source_name}")
    # Return 200/204 to acknowledge the message to Pub/Sub
    return Response(status_code=200)
