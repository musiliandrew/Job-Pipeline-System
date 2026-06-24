"""
common/apify_client.py — Apify client for complex/paid scraping tasks.
Uses APIFY_API_TOKEN.
"""
import os
import requests
from typing import Any, Dict, Optional

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
SESSION = requests.Session()


def run_actor(actor_id: str, run_input: Dict[str, Any], timeout_secs: int = 300) -> Optional[Dict[str, Any]]:
    """
    Run an Apify actor synchronously (blocks until run completes or times out).
    Returns the run result or None.
    """
    if not APIFY_TOKEN:
        return None
        
    url = f"https://api.apify.com/v2/acts/{actor_id}/runs"
    params = {"token": APIFY_TOKEN, "timeout": timeout_secs}
    
    try:
        resp = SESSION.post(url, json=run_input, params=params, timeout=timeout_secs + 10)
        if resp.status_code in (200, 201):
            run_data = resp.json().get("data") or {}
            # Get output dataset
            dataset_id = run_data.get("defaultDatasetId")
            if dataset_id:
                return get_dataset_items(dataset_id)
            return run_data
    except Exception:
        pass
    return None


def get_dataset_items(dataset_id: str) -> Optional[Dict[str, Any]]:
    if not APIFY_TOKEN:
        return None
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    params = {"token": APIFY_TOKEN}
    try:
        resp = SESSION.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return {"items": resp.json()}
    except Exception:
        pass
    return None
