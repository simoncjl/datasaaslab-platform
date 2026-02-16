# datasaaslab-platform

Production-ready backend with FastAPI, PostgreSQL 16, Redis, SQLAlchemy 2.0, Alembic, Celery, and a local HTMX/Jinja2 admin UI.

## Quick Start

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

## Admin UI

Open: http://localhost:8000/admin

Auth behavior:

- If `ADMIN_USER` and `ADMIN_PASS` are set, `/admin` requires HTTP Basic auth.
- If they are not set, `/admin` allows localhost-only access (`127.0.0.1` / `::1`).

Example:

```bash
export ADMIN_USER=admin
export ADMIN_PASS=change-me
```

Then restart the stack (`make down && make up`).

## Admin Workflow

1. Create or edit a topic in `/admin/topics`.
2. Click `Generate` to create a run and enqueue async generation.
3. Open the run page, review FR/EN artifacts, edit MDX bodies, mark both reviewed.
4. Ensure export gates pass:
   - run status is `succeeded`
   - FR and EN artifacts exist
   - FR and EN are reviewed
   - `run.meta.claims_to_verify` is empty or missing
5. Click `Export FR + EN` to write files to:
   - `BLOG_REPO_PATH/src/content/blog/fr/{slug}.mdx`
   - `BLOG_REPO_PATH/src/content/blog/en/{slug}.mdx`

## Batch Generation (Admin)

- Create batch: `/admin/batches`
- View batch: `/admin/batches/{id}`
- Trigger manual poll: `Poll now` button

Make sure `OPENAI_API_KEY` and `BLOG_REPO_PATH` are configured in `.env`.
