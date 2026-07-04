# CareerScoper Data Ingestion System

The Data Ingestion System is a **standalone, high-throughput web scraping and ETL microservice**. It is responsible for gathering raw data from external sources (Adzuna, Jooble, Eventbrite, Reddit, Company ATS pages, and Gmail), parsing it, and inserting it directly into a PostgreSQL database.

It is built with **FastAPI** and uses **APScheduler** (for local development) and **Google Cloud Tasks/Scheduler** (for production orchestration).

## Architecture Overview
This microservice operates completely independently of the CareerScoper API. It does not rely on Django ORM or any of the monolith's business logic.

1. **Direct DB Access:** Uses a raw `psycopg2` ThreadedConnectionPool for maximum write throughput, bypassing heavy ORM abstractions.
2. **Serverless Orchestration:** Exposes HTTP endpoints (`/trigger/tier/{tier_name}` and `/worker/consume`) designed to be hit by Google Cloud Scheduler or Cloud Tasks, allowing the microservice to scale down to zero when idle.
3. **Resilient Scraping:** Handles API rate limits, XML parsing, and unstructured text extraction asynchronously.

## Running Locally (Standalone)

You can run this service entirely on its own to populate a database.

1. Create a virtual environment: `python -m venv env`
2. Activate it: `source env/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Set environment variables (requires `DATABASE_URL`):
   ```bash
   cp .env.example .env
   ```
5. Run the server:
   ```bash
   uvicorn main:app --reload --port 8001
   ```

*Note: In local development, an internal `APScheduler` starts automatically to run periodic scrapes. In production, this scheduler disables itself to allow Google Cloud Scheduler to handle execution.*

## API Endpoints

- **`GET /health`**: Health check.
- **`GET /status`**: View the status of the connection pool and ingestion metrics.
- **`POST /trigger/tier/{tier_name}`**: Manually trigger a scrape orchestration tier (e.g., `hot`, `warm`, `cold`).
- **`POST /worker/consume`**: Execute a specific scrape job (Expects a Google Cloud Task JSON payload).
