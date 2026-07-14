# Data Quality Profiler

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Microservice for automated data quality profiling in PostgreSQL. Scans tables, computes metrics (completeness, uniqueness, value distributions), persists historical snapshots, and detects data degradation through SQL Self-Joins. Designed for BI pipelines where data quality must be validated at the source.

## What is in the box

| Area | Component | Purpose |
|------|-----------|---------|
| Profiling | app.core.profiler | Per-column metrics: null ratio, distinct count, min/max, top-N values |
| Big Data | pg_stats fallback | Skip heavy COUNT(DISTINCT) for tables over 100K rows |
| Degradation | compare_with_previous | Self-Join between two snapshots, alerts on metric regressions |
| API | FastAPI endpoints | /api/latest_report, /api/degradation, Swagger UI at /docs |
| Persistence | Snapshot storage | JSONB history table for time-series analysis |
| Seed data | scripts/seed_data.sql | Synthetic dataset with intentional defects plus 10M row stress table |

## Quick start

Requires Docker and Docker Compose.

    docker compose up --build -d

PostgreSQL initialises the schema and runs the seed script. The API becomes available at http://localhost:8000 once the healthcheck passes.

Run the profiler against the seeded tables:

    docker compose exec app python -m app.main run

## API

Interactive documentation at http://localhost:8000/docs

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/latest_report?table=name | GET | Most recent snapshot with all computed metrics |
| /api/degradation?table=name | GET | Compare two latest snapshots, return regressions |
| /api/tables | GET | List profiled tables |

## Architecture

| Layer | Technology | Notes |
|-------|-----------|-------|
| Runtime | Python 3.11, Uvicorn | ASGI, single worker |
| API | FastAPI, Pydantic v2 | Strict mode, typed models |
| Database | PostgreSQL 16 | psycopg2-binary, information_schema and pg_stats |
| Container | Docker | Non-root user, layer caching |
| Orchestration | Docker Compose v2 | Isolated network, healthchecks |
| Testing | pytest | Fixtures with temporary schema |

## Project layout

    data-quality-profiler/
    ├── app/
    │   ├── main.py              # CLI entry and FastAPI app
    │   ├── api/                 # REST routers
    │   ├── core/                # Profiler engine, degradation detector
    │   └── db/                  # Connection pool, snapshot repository
    ├── scripts/
    │   └── seed_data.sql        # Test data generator
    ├── tests/                   # pytest suite
    ├── Dockerfile               # Multi-stage build, non-root
    ├── docker-compose.yml       # App + PostgreSQL stack
    └── requirements.txt         # Pinned dependencies

## Requirements

- Python 3.11 or newer (for local development without Docker)
- PostgreSQL 16 (provided via Docker Compose)
- Docker Engine 24+ and Docker Compose v2
- About 2 GB disk for the 10M row stress table

## Key facts about v1.0.0

pg_stats optimisation. For any table where pg_class.reltuples exceeds 100000, the profiler reads column statistics directly from pg_stats instead of running COUNT(DISTINCT) queries. Latency drops from seconds to single-digit milliseconds on million-row tables. Threshold is configurable via BIG_TABLE_THRESHOLD environment variable.

Self-Join degradation detection. The /api/degradation endpoint performs a single SQL query that joins the two most recent snapshots by table_name and column_name, computes deltas for every numeric metric, and returns only columns where any metric exceeds the configured tolerance (default 5 percentage points for null ratio).

Non-root container. The Dockerfile creates an appuser with UID 1001, copies the application, and drops privileges before the entrypoint. No process inside the container runs as root.

Stress-test seed. scripts/seed_data.sql generates a big_table with exactly 10,000,000 rows using generate_series, plus three smaller tables (customers, orders, products) with intentional defects: null-heavy columns, duplicate IDs, out-of-range dates. The defects are deterministic, so tests remain stable across runs.

Layer-cached Docker build. requirements.txt is copied and pip install runs in a dedicated layer before the application source, so dependency installation is cached as long as requirements.txt is unchanged.

## Testing

    docker compose exec app pytest tests/ -v

Tests spin up an ephemeral PostgreSQL schema via fixtures, run the profiler, and assert on both metric values and degradation detection logic. No external services required beyond the Compose stack.

## License

MIT License. Copyright 2026 ms02dev. See LICENSE file for full text.
