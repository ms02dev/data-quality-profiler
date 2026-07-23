Changelog

Format based on Keep a Changelog. Versioning follows Semantic Versioning.

[Unreleased]
Added
Dockerfile now copies the tests folder into the image, so pytest can run inside the container
Centralized configuration via Pydantic Settings: startup validation (Field(ge=, le=)), SecretStr for the database password
APScheduler for recurring table profiling (customers: 6h, orders: 12h, big_table: 24h)
Schedule intervals configurable via SCHEDULE_*_HOURS environment variables
GET /api/schedule/status endpoint showing scheduled jobs and next run times
POST /api/schedule/trigger endpoint for manual profiling of any table in the database
Scheduler skips tables missing from the database instead of failing at runtime
Graceful shutdown waits for an in-progress profiling run to finish (wait=True)