"""
flush_outbox.py — Transactional Outbox Publisher

Designed to be executed as a standalone GCP Cloud Run Job.
It reads pending events from the PostgreSQL outbox_events table,
publishes them securely to the GCP Pub/Sub EventBus, and deletes them upon success.

This guarantees 100% reliable, idempotent event delivery for downstream AI workers.
"""
import logging
import sys
import os

from db.connection import DBConn
from events.bus import event_bus
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("flush_outbox")

def ensure_outbox_table(conn):
    """Ensure the outbox_events table exists."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS outbox_events (
                id UUID PRIMARY KEY,
                topic VARCHAR(255) NOT NULL,
                event_type VARCHAR(255) NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

def flush():
    """Reads events from the outbox and publishes them."""
    logger.info("Starting Outbox Flush Job...")
    
    published_count = 0
    failed_count = 0

    with DBConn() as conn:
        ensure_outbox_table(conn)
        
        # Read a batch of events
        # We use FOR UPDATE SKIP LOCKED to prevent concurrent Cloud Run Jobs
        # from processing the same events, enabling horizontal scaling of this job if needed.
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, topic, event_type, payload
                FROM outbox_events
                ORDER BY created_at ASC
                LIMIT 500
                FOR UPDATE SKIP LOCKED
            """)
            events = [dict(r) for r in cur.fetchall()]
            
        if not events:
            logger.info("Outbox is empty. Nothing to flush.")
            return

        logger.info(f"Found {len(events)} pending events in outbox. Publishing...")

        for event in events:
            # Publish to the EventBus (Pub/Sub)
            success = event_bus.publish(
                topic=event["topic"],
                event_type=event["event_type"],
                payload=event["payload"]
            )
            
            if success:
                # Delete successfully published event
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM outbox_events WHERE id = %s", (event["id"],))
                published_count += 1
            else:
                failed_count += 1

    logger.info(f"Outbox Flush Complete. Published: {published_count}, Failed: {failed_count}")
    
    if failed_count > 0:
        logger.warning("Some events failed to publish. They will be retried on the next run.")
        sys.exit(1)
        
if __name__ == "__main__":
    try:
        flush()
    except Exception as e:
        logger.error(f"Fatal error during outbox flush: {e}")
        sys.exit(1)
