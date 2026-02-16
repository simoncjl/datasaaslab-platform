# datasaaslab-platform

Production-ready backend bootstrap with FastAPI, PostgreSQL 16, Redis, SQLAlchemy 2.0, and Alembic.

## Quick start

1. Copy env template:
   ```bash
   cp .env.example .env
   ```
2. Start stack:
   ```bash
   make up
   ```
3. Apply DB migrations:
   ```bash
   make migrate
   ```

API docs: http://localhost:8000/docs
