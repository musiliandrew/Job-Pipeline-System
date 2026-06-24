"""
common/http.py — Shared HTTP helpers ported from DataIngestion/_common.
"""
import time
from typing import Any, Dict, Optional

import requests

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124 Safari/537.36"
    )
})


def polite_delay(seconds: float = 0.3) -> None:
    time.sleep(seconds)


def safe_get_json(
    url: str,
    params: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    timeout: int = 20,
) -> Optional[Dict[str, Any]]:
    try:
        r = SESSION.get(url, params=params, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def safe_post_json(
    url: str,
    body: Any,
    headers: Optional[Dict] = None,
    timeout: int = 20,
) -> Optional[Dict[str, Any]]:
    try:
        r = SESSION.post(url, json=body, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None
