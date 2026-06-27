"""
events/bus.py — Transport-agnostic Event Bus for Data Ingestion.

Abstracts the publishing of ingestion events (like 'job_created') away from 
the underlying messaging infrastructure (GCP Pub/Sub, Redis, etc.)
"""
import abc
import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

class EventBus(abc.ABC):
    """Abstract interface for publishing events."""
    
    @abc.abstractmethod
    def publish(self, topic: str, event_type: str, payload: Dict[str, Any]) -> bool:
        """
        Publish a structured event to a topic.
        :param topic: The routing key or topic name (e.g. 'raw-jobs')
        :param event_type: A string identifier for the event (e.g. 'job_created')
        :param payload: The actual data payload to send
        :return: bool indicating success
        """
        pass


class GCPPubSubBus(EventBus):
    """
    Google Cloud Pub/Sub implementation.
    Requires `google-cloud-pubsub` and `GOOGLE_APPLICATION_CREDENTIALS`.
    """
    def __init__(self):
        try:
            from google.cloud import pubsub_v1
            self.publisher = pubsub_v1.PublisherClient()
            self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            if not self.project_id:
                logger.warning("GCPPubSubBus initialized without GOOGLE_CLOUD_PROJECT env var.")
        except ImportError:
            self.publisher = None
            logger.warning("google-cloud-pubsub is not installed. GCPPubSubBus will fail if used.")

    def publish(self, topic: str, event_type: str, payload: Dict[str, Any]) -> bool:
        if not self.publisher or not self.project_id:
            logger.error("GCPPubSubBus cannot publish: Missing library or project_id")
            return False
            
        topic_path = self.publisher.topic_path(self.project_id, topic)
        data_str = json.dumps(payload)
        data_bytes = data_str.encode("utf-8")
        
        try:
            future = self.publisher.publish(
                topic_path, 
                data=data_bytes, 
                event_type=event_type  # Sent as a Pub/Sub attribute
            )
            message_id = future.result()
            logger.debug(f"Published event {event_type} to Pub/Sub topic {topic} with ID {message_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish to GCP Pub/Sub: {e}")
            return False


class LocalEventBus(EventBus):
    """
    In-memory or local mock implementation for local development.
    Simply logs the event instead of relying on cloud infrastructure.
    """
    def publish(self, topic: str, event_type: str, payload: Dict[str, Any]) -> bool:
        logger.info(f"[LOCAL EVENT BUS] Topic: {topic} | Event: {event_type} | Payload: {payload.get('id', 'unknown')}")
        return True


# Factory to get the active Event Bus based on environment
def get_event_bus() -> EventBus:
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "production":
        return GCPPubSubBus()
    return LocalEventBus()

# Singleton instance
event_bus = get_event_bus()
