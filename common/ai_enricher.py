"""
common/ai_enricher.py — Gemini 2.5 Flash AI Job Classification & Enrichment

Uses Google Gemini 2.5 Flash API to accurately classify unstructured posts
(e.g., Reddit, RSS, social media) and extract structured job data.
"""
import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDepav23nN09yxxdYzd8aUrU4U0rQa-C1Q")
GEMINI_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash")
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

def classify_and_enrich_post(title: str, body: str) -> Optional[Dict[str, Any]]:
    """
    Calls Gemini 2.5 Flash to determine if a raw post is a valid hiring opportunity
    and extracts structured metadata. Returns None if it is NOT a job post.
    """
    if not GEMINI_API_KEY:
        return None

    prompt = f"""
Analyze the following post title and body to evaluate if it is a legitimate job opening / hiring announcement for software, data, AI, or tech roles.
Do NOT classify '[For Hire]' posts (people looking for jobs) as job openings. Only classify '[Hiring]' or employer job posts as valid.

Title: {title}
Body: {body[:1500]}

Respond strictly in valid JSON format with no Markdown wrapping:
{{
    "is_hiring_job": true or false,
    "clean_title": "Extracted official job title",
    "company_name": "Extracted company name or 'Remote/Unknown'",
    "is_remote": true or false,
    "skills": ["Skill1", "Skill2"],
    "salary_formatted": "Extracted salary string or 'Not specified'"
}}
"""

    try:
        url = f"{GEMINI_ENDPOINT}?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code != 200:
            logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text}")
            return None

        result_text = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        # Clean any markdown block formatting if returned
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]

        data = json.loads(result_text.strip())
        if data.get("is_hiring_job"):
            return data
        return None
    except Exception as e:
        logger.error(f"Error calling Gemini AI Enricher: {e}")
        return None
