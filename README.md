# Distributed Data Ingestion System

A **standalone, high-throughput web scraping and ETL microservice**. It is responsible for gathering raw unstructured data from external sources (job boards, ATS platforms, news APIs, and emails), parsing it, and streaming it directly into a PostgreSQL database.

Built with **FastAPI** and uses **APScheduler** (for local development) and **Google Cloud Tasks/Scheduler** (for production serverless orchestration).

## Architecture Overview
This microservice operates completely independently of any specific business logic or heavy ORM abstractions. 

1. **Direct DB Access:** Uses a raw `psycopg2` ThreadedConnectionPool for maximum write throughput, avoiding the overhead of heavy frameworks like Django/SQLAlchemy ORMs.
2. **Serverless Orchestration:** Exposes generic HTTP endpoints designed to be triggered by Google Cloud Scheduler or Cloud Tasks, allowing the service to scale dynamically and scale down to zero when idle.
3. **Resilient Scraping:** Handles API rate limits, XML/HTML parsing, and unstructured text extraction asynchronously.

## Running Locally

You can run this service entirely on its own to execute scraping pipelines.

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

*Note: In local development, an internal `APScheduler` starts automatically to run periodic scrape jobs. In production, this scheduler disables itself to allow external cloud event triggers.*

## API Endpoints

- **`GET /health`**: Health check.
- **`GET /status`**: View the status of the connection pool and ingestion metrics.
- **`POST /trigger/tier/{tier_name}`**: Manually trigger a scrape orchestration tier (e.g., `hot`, `warm`, `cold`).
- **`POST /worker/consume`**: Execute a specific scrape job (Expects a generic JSON payload detailing the target source).
