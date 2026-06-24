"""jobs/filters.py — Ported from DataIngestion/Jobs/filters.py"""
from typing import List
import re

ROLE_KEYWORDS = {
    "ds":  ["data scientist", "data science"],
    "ml":  ["machine learning", "ml engineer", "mlops"],
    "ai":  ["ai engineer", "llm", "nlp", "computer vision", "genai"],
    "swe": ["software engineer", "backend", "frontend", "fullstack", "devops", "sre", "platform"],
}

SKILL_KEYWORDS = [
    "python", "pytorch", "tensorflow", "sklearn", "sql", "spark", "airflow", "dbt",
    "docker", "kubernetes", "k8s", "aws", "gcp", "azure", "java", "go", "node",
    "react", "kafka",
]

WORKTYPE_MAP = [
    ("remote",    "remote"),
    ("hybrid",    "hybrid"),
    ("onsite",    "onsite"),
    ("full-time", "full-time"),
    ("contract",  "contract"),
    ("intern",    "internship"),
]

EXCLUDE_PATTERNS = [
    r"giveaway|survey|resume review|portfolio review|commission|looking for work|hiring manager advice",
]


def contains_any(text: str, terms: List[str]) -> bool:
    t = text.lower()
    return any(term in t for term in terms)


def is_relevant_role(text: str) -> bool:
    t = text.lower()
    return any(any(k in t for k in bucket) for bucket in ROLE_KEYWORDS.values())


def extract_skills(text: str) -> List[str]:
    t = text.lower()
    return list(dict.fromkeys(s for s in SKILL_KEYWORDS if s in t))


def detect_work_type(text: str) -> str:
    t = text.lower()
    for needle, label in WORKTYPE_MAP:
        if needle in t:
            return label
    return ""


def reddit_is_job_listing(title: str, body: str) -> bool:
    text = f"{title}\n{body}".lower()
    if not is_relevant_role(text):
        return False
    if len(body) < 200:
        return False
    if not ("apply" in text or "http" in text or "@" in text):
        return False
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, text):
            return False
    return bool(extract_skills(text))
