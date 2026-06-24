# Data Ingestion System (DIS) — Lead Document

> **This is the single source of truth for the DIS pipeline.**
> Every engineer touching this service should read this first.

---

## What This Service Does

The DIS is a **standalone FastAPI service** that runs independently from the Django API backend.
It pulls job data from every source we support, normalises it into a unified schema, and writes
directly to the shared PostgreSQL database — no Celery, no broker, no Django ORM.

The Django backend (`/api/jobs/`, `/api/companies/`) reads from the same DB.
DIS only **writes**. Django only **reads** (from the jobs tables).

---

## Core Design Rule: Everything Runs in Parallel

> **The pipeline must never lag. Sources must not block each other.**

All collectors run concurrently via `ThreadPoolExecutor`. A slow ATS scrape
does not delay the Adzuna collection. A Firecrawl timeout does not stall Remotive.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        APScheduler Tick (every N minutes)            │
│                                                                      │
│  ThreadPoolExecutor(max_workers=12)                                  │
│  ┌─────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌──────────────┐   │
│  │ Remotive│ │Adzuna  │ │Arbeitnow │ │Jobicy  │ │ The Muse     │   │
│  └────┬────┘ └───┬────┘ └────┬─────┘ └───┬────┘ └──────┬───────┘   │
│  ┌────┴────┐ ┌───┴────┐ ┌────┴─────┐ ┌───┴────┐ ┌──────┴───────┐   │
│  │Himalayas│ │Jooble  │ │Greenhouse│ │ Lever  │ │    Ashby     │   │
│  └────┬────┘ └───┬────┘ └────┬─────┘ └───┬────┘ └──────┬───────┘   │
│       │          │           │            │             │            │
│       └──────────┴───────────┴────────────┴─────────────┘            │
│                              │                                       │
│                              ▼                                       │
│                    ┌─────────────────┐                               │
│                    │  psycopg2 pool  │                               │
│                    │  upsert_job()   │                               │
│                    └────────┬────────┘                               │
│                             │                                        │
└─────────────────────────────┼────────────────────────────────────────┘
                              ▼
                     PostgreSQL Database
                     (jobs, companies, locations, job_sources, job_collection_logs)
```

---

## Source Inventory

### Tier 1 — Free REST APIs (run every 10 min)

| Source | Endpoint | Auth | Rate Limit | Notes |
|--------|----------|------|-----------|-------|
| **Remotive** | `https://remotive.com/api/remote-jobs` | None | ~200 req/hr | Remote-only, great quality |
| **Arbeitnow** | `https://arbeitnow.com/api/job-board-api` | None | No stated limit | EU-heavy, paginated |
| **Adzuna** | `https://api.adzuna.com/v1/api/jobs/{country}/search/1` | `app_id` + `app_key` | 250/day free | Multi-country |
| **Jobicy** | `https://jobicy.com/api/v2/remote-jobs` | None | No stated limit | Remote-only |
| **The Muse** | `https://www.themuse.com/api/public/jobs` | Optional `api_key` | 3600/hr | Good company metadata |
| **Himalayas** | `https://himalayas.app/jobs/api` | None | No stated limit | Remote-first, great metadata |
| **Jooble** | `https://jooble.org/api/{API_KEY}` | POST body, API key | Per plan | Aggregator, wide coverage |

### Tier 2 — ATS Direct Public API Exploitation (run every 12 hrs per company)

These are **not scraping** — they are public, documented board APIs:

| ATS | Pattern | Format |
|-----|---------|--------|
| **Greenhouse** | `https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs` | JSON REST |
| **Lever** | `https://api.lever.co/v0/postings/{company}?mode=json` | JSON REST |
| **Ashby** | `https://api.ashbyhq.com/posting-public/job-board/{board_id}` | JSON REST |

> These return full structured job data — title, description, location, department, apply URL.
> No scraping, no Firecrawl needed. Pure API calls.

### Tier 3 — GitHub Open-Source Job Data (run every 6 hrs)

These repos publish JSON/CSV files of curated job listings:

| Repo | Source | Data Format |
|------|--------|-------------|
| **SimplifyJobs/New-Grad-Positions** | `github.com/SimplifyJobs/New-Grad-Positions` | README table + JSON |
| **pittcsc/Summer2025-Internships** | `github.com/pittcsc/Summer2025-Internships` | README table + JSON |
| **EverJobs** (open job board repos) | Various `github.com` repos with `jobs.json` | JSON |

> Strategy: fetch the raw JSON file from GitHub's CDN:
> `https://raw.githubusercontent.com/{org}/{repo}/main/jobs.json`
> Parse → normalise → upsert. No API key. No rate limit issues.

### Tier 4 — Paid Services (use surgically, not in bulk loops)

> **These cost money. Only call them when free alternatives fail.**

| Service | When to Use | Cost Signal |
|---------|-------------|------------|
| **Tavily** | Company homepage/careers URL discovery, news enrichment | Per search query |
| **Firecrawl** | JS-heavy career pages that block plain requests | Per page crawled |
| **Apify** | Complex multi-page ATS scraping, LinkedIn job data | Per compute unit |

**Rules for paid service usage:**
1. Always try the free public API or direct HTML request first
2. Only call Tavily for company URL discovery if no URL is known
3. Only call Firecrawl if `requests.get()` returns empty HTML or a 403
4. Only call Apify for sources with no other path (LinkedIn-type walls)
5. Cache all paid service results in the DB — never re-query the same URL twice

---

## Target DB Fields Per Source

Every source must map to this unified schema before calling `upsert_job()`:

```python
{
    # Required
    "external_id":    str,   # unique ID from source (deduplicate on this + source_id)
    "title":          str,   # max 255 chars
    "company_name":   str,   # used to get/create companies row
    "location_text":  str,   # "Remote", "New York, NY", etc.
    "external_url":   str,   # canonical job URL
    "apply_url":      str,   # direct apply link (may == external_url)

    # Strongly preferred
    "description":    str,   # full job description text
    "posted_at":      datetime,
    "work_type":      str,   # "remote" | "hybrid" | "onsite" | "contract" | "internship" | "full-time"
    "skills":         list[str],
    "technologies":   list[str],
    "experience_level": str, # "junior" | "mid" | "senior" | "lead" | "entry"

    # Salary (fill what you have)
    "salary_min":     float | None,
    "salary_max":     float | None,
    "salary_currency": str | None,  # "USD", "EUR", etc.
    "salary_period":  str | None,   # "year" | "month" | "hour"

    # Optional enrichment
    "is_remote":      bool | None,
    "is_hybrid":      bool | None,
    "categories":     list[str] | None,
    "expires_at":     datetime | None,
    "parsed_metadata": dict,  # store raw salary_formatted, department, etc.
    "raw_data":       dict,   # full raw API response for debugging
}
```

### Field Coverage by Source

| Field | Remotive | Adzuna | Arbeitnow | Jobicy | TheMuse | Himalayas | Greenhouse | Lever | Ashby |
|-------|:--------:|:------:|:---------:|:------:|:-------:|:---------:|:----------:|:-----:|:-----:|
| `title` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `company_name` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `location_text` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `description` | ✅ | partial | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `posted_at` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `apply_url` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `work_type` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | partial | partial | partial |
| `skills` | detect | detect | detect | detect | ✅ | ✅ | detect | detect | detect |
| `salary_min/max` | partial | ✅ | partial | partial | partial | ✅ | ❌ | ❌ | ❌ |
| `experience_level` | detect | detect | detect | detect | ✅ | ✅ | detect | detect | detect |
| `is_remote` | ✅ | partial | ✅ | ✅ | ✅ | ✅ | detect | detect | detect |

> **"detect"** = extract from title/description text using `jobs/filters.py`
> **"partial"** = sometimes present, handle gracefully

---

## Parallel Execution Architecture

### Current (sequential — BAD for large loads)
```python
# Old approach — each provider blocks the next
for provider in PROVIDERS:
    collect_provider(provider)  # blocks until done
```

### Target (parallel — required)
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def collect_all_parallel():
    tasks = {
        "remotive":   collect_remotive,
        "adzuna":     collect_adzuna,
        "arbeitnow":  collect_arbeitnow,
        "jobicy":     collect_jobicy,
        "themuse":    collect_themuse,
        "himalayas":  collect_himalayas,
        "jooble":     collect_jooble,
    }
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result(timeout=60)
            except Exception as e:
                results[name] = {"error": str(e)}
    return results
```

Each collector gets its own DB connection from the pool — writes never block each other.

---

## Scheduler Configuration (Target)

```
Every 10 min  → [Remotive, Adzuna, Arbeitnow, Jobicy, TheMuse, Himalayas, Jooble]
                 ALL fired in parallel via ThreadPoolExecutor

Every 6 hrs   → [GitHub sources: Simplify, pittcsc, EverJobs]
                 Parallel fetch of raw JSON files

Every 12 hrs  → [ATS sweep: Greenhouse boards, Lever boards, Ashby boards]
                 Parallel per company (each company = one thread)

Every 1 hr    → [Company URL backfill] — uses Tavily sparingly
Every 6 hrs   → [Company news] — uses Tavily sparingly
Every 24 hrs  → [Company metadata enrich]

Paid triggers (on-demand only):
  Firecrawl   → only when standard request returns empty/403
  Apify       → only for LinkedIn-type sources with no free path
```

---

## Source Implementation Status

| Source | Provider File | Status |
|--------|--------------|--------|
| Adzuna | `jobs/providers/adzuna.py` | ✅ Built |
| Jooble | `jobs/providers/jooble.py` | ✅ Built |
| Reddit | `jobs/providers/reddit.py` | ✅ Built (deprioritise) |
| Eventbrite | `jobs/providers/eventbrite.py` | ✅ Built (deprioritise) |
| **Remotive** | `jobs/providers/remotive.py` | ❌ TODO |
| **Arbeitnow** | `jobs/providers/arbeitnow.py` | ❌ TODO |
| **Jobicy** | `jobs/providers/jobicy.py` | ❌ TODO |
| **The Muse** | `jobs/providers/themuse.py` | ❌ TODO |
| **Himalayas** | `jobs/providers/himalayas.py` | ❌ TODO |
| **Greenhouse API** | `jobs/ats/greenhouse.py` | ⚠️ Partial (HTML scrape) → upgrade to API |
| **Lever API** | `jobs/ats/lever.py` | ⚠️ Partial (HTML scrape) → upgrade to API |
| **Ashby API** | `jobs/ats/ashby.py` | ❌ TODO |
| **SimplifyJobs** | `jobs/github/simplify.py` | ❌ TODO |
| **pittcsc** | `jobs/github/pittcsc.py` | ❌ TODO |
| **EverJobs** | `jobs/github/everjobs.py` | ❌ TODO |
| **Parallel collector** | `jobs/collector.py` | ⚠️ Sequential → upgrade to ThreadPoolExecutor |

---

## File Structure (Target)

```
data-ingestion-system/
├── main.py
├── scheduler.py
├── .env / .env.example
├── requirements.txt
├── Dockerfile
│
├── db/
│   ├── connection.py          ← psycopg2 pool
│   └── upserts.py             ← all SQL writes
│
├── common/
│   ├── http.py                ← safe_get_json, safe_post_json
│   ├── firecrawl_client.py    ← PAID — use carefully
│   ├── tavily_client.py       ← PAID — use carefully
│   └── apify_client.py        ← PAID — use carefully (TODO)
│
├── jobs/
│   ├── filters.py             ← relevance, skill extract, work_type detect
│   ├── normalize.py           ← unified normaliser
│   ├── collector.py           ← parallel orchestrator (ThreadPoolExecutor)
│   │
│   ├── providers/             ← Tier 1: Free REST APIs
│   │   ├── remotive.py        ← TODO
│   │   ├── adzuna.py          ← ✅ built
│   │   ├── arbeitnow.py       ← TODO
│   │   ├── jobicy.py          ← TODO
│   │   ├── themuse.py         ← TODO
│   │   ├── himalayas.py       ← TODO
│   │   └── jooble.py          ← ✅ built
│   │
│   ├── ats/                   ← Tier 2: ATS Public APIs
│   │   ├── greenhouse.py      ← upgrade to boards-api.greenhouse.io
│   │   ├── lever.py           ← upgrade to api.lever.co/v0/postings
│   │   ├── ashby.py           ← TODO: api.ashbyhq.com
│   │   ├── workday.py         ← ✅ built (HTML, no public API)
│   │   ├── generic.py         ← ✅ built
│   │   ├── ai_extractor.py    ← ✅ built (Firecrawl fallback)
│   │   └── ingest.py          ← company ATS orchestrator
│   │
│   └── github/                ← Tier 3: GitHub open-source repos
│       ├── simplify.py        ← TODO
│       ├── pittcsc.py         ← TODO
│       └── everjobs.py        ← TODO
│
├── companies/
│   ├── discovery.py
│   ├── enrich.py
│   ├── news.py
│   └── backfill.py
│
├── news/
│   ├── feeds.py
│   ├── filters.py
│   ├── rss_ingest.py
│   └── industry_dive.py
│
└── routers/
    ├── health.py    → GET /health
    ├── trigger.py   → POST /trigger/{source}
    ├── status.py    → GET /status
    └── logs.py      → GET /logs
```

---

## Environment Variables Reference

```env
# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://user:password@host:5432/careerscoper

# ── Tier 1: Free APIs ─────────────────────────────────────────────────────────
ADZUNA_APP_ID=
ADZUNA_API_KEY=
ADZUNA_COUNTRY=us

JOOBLE_API_KEY=

THEMUSE_API_KEY=            # optional, raises rate limit
REMOTIVE_MAX_JOBS=100       # default
ARBEITNOW_MAX_PAGES=5       # default
HIMALAYAS_MAX_JOBS=100      # default
JOBICY_MAX_JOBS=50          # default

REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=

# ── Tier 2: ATS boards ────────────────────────────────────────────────────────
# Comma-separated list of known Greenhouse board slugs to poll
GREENHOUSE_BOARDS=stripe,airbnb,shopify,figma,notion,linear
# Comma-separated Lever company slugs
LEVER_COMPANIES=gitlab,hashicorp,vercel,supabase
# Ashby board IDs
ASHBY_BOARDS=loom,retool,dbt-labs

# ── Tier 3: GitHub ────────────────────────────────────────────────────────────
GITHUB_TOKEN=               # optional, raises rate limit from 60→5000 req/hr

# ── Tier 4: Paid Services ─────────────────────────────────────────────────────
TAVILY_API_KEY=
CRAWLER_BASE_URL=http://localhost:7071   # Firecrawl self-hosted or managed
CRAWLER_API_KEY=
APIFY_API_TOKEN=            # only needed if using Apify actors

# ── AI / LLM (for job enrichment fallback) ────────────────────────────────────
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4o-mini
GEMINI_API_KEY=

# ── Scheduler intervals ───────────────────────────────────────────────────────
FREE_API_INTERVAL_MINUTES=10
GITHUB_INTERVAL_HOURS=6
ATS_INTERVAL_HOURS=12
COMPANY_BACKFILL_INTERVAL_HOURS=1
COMPANY_NEWS_INTERVAL_HOURS=6
```

---

## Paid Service Usage Budget Guidelines

| Service | Budget Rule | Max per run |
|---------|-------------|-------------|
| **Tavily** | Only for company URL discovery when DB has no URL | 1 search per company, cached permanently |
| **Firecrawl** | Only when `requests.get()` returns < 500 chars of content | 1 fetch per unique URL, cached 24h |
| **Apify** | Only for sources with no free path | Manual trigger only, not scheduled |

---

## Quality Checklist Before Any Source Goes Live

Before merging a new provider:

- [ ] `external_id` is unique and stable across re-fetches (not a timestamp)
- [ ] `company_name` normalised (trim, not empty, max 255)
- [ ] `location_text` has a fallback of `"Remote"` never empty
- [ ] `posted_at` is a timezone-aware `datetime`, not a string
- [ ] `external_url` is a valid absolute URL
- [ ] `apply_url` filled — if none, copy `external_url`
- [ ] Relevance filter applied (`is_relevant_role()`) before upsert
- [ ] `log_collection()` called after every run (success or failure)
- [ ] Rate limit respected (add `polite_delay()` between paginated requests)
- [ ] Test: run in isolation, check DB rows appear with correct field values

---

## Next Implementation Steps (Priority Order)

1. **Upgrade `jobs/collector.py`** → parallel `ThreadPoolExecutor` (unblocking)
2. **Build `jobs/providers/remotive.py`** — free, high quality, no auth
3. **Build `jobs/providers/arbeitnow.py`** — free, no auth
4. **Build `jobs/providers/himalayas.py`** — free, structured JSON
5. **Build `jobs/providers/jobicy.py`** — free, no auth
6. **Build `jobs/providers/themuse.py`** — good metadata
7. **Upgrade `jobs/ats/greenhouse.py`** → `boards-api.greenhouse.io` (pure API)
8. **Upgrade `jobs/ats/lever.py`** → `api.lever.co/v0/postings` (pure API)
9. **Build `jobs/ats/ashby.py`** → `api.ashbyhq.com/posting-public`
10. **Build `jobs/github/simplify.py`** → fetch raw JSON from GitHub CDN
11. **Build `jobs/github/pittcsc.py`**
12. **Build `jobs/github/everjobs.py`**
