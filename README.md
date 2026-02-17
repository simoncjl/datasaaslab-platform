![AI-assisted](https://img.shields.io/badge/AI--assisted-human%20reviewed-blue)

# datasaaslab-platform

Production-ready backend for an **AI-assisted technical writing pipeline**.

Stack: FastAPI · PostgreSQL 16 · Redis · SQLAlchemy 2.0 · Alembic · Celery · HTMX/Jinja2 admin UI · OpenAI Responses API (Structured Outputs)

This platform generates **bilingual technical article drafts (FR/EN)** with a strict **human review workflow** and **export gates**.

---

## ✨ Features

- Bilingual article generation (FR/EN)
- Section-by-section AI review assistant
- Claims-to-verify workflow
- Human review gates before export
- Single export action writing both MDX files
- Async generation via Celery + Redis
- Batch generation support (OpenAI Batch API)
- Audit trail of AI suggestions

---

## 🔒 Review Gates

Export is blocked unless:

- `run.status == succeeded`
- FR and EN artifacts exist
- both artifacts are reviewed
- `run.meta.claims_to_verify` is empty

This enforces **human validation before publication**.

---

## 🚀 Quick Start

Primary workflow (`make`):

```bash
cp .env.example .env
make up
make migrate
```

API docs: `http://localhost:8000/docs`  
Admin UI: `http://localhost:8000/admin`

Alternative manual workflow (`docker compose`):

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

---

## 🔐 Admin Authentication

- If `ADMIN_USER` and `ADMIN_PASS` are set, HTTP Basic auth is required for `/admin`.
- If not set, `/admin` is restricted to localhost (`127.0.0.1` / `::1`).

Example:

```bash
export ADMIN_USER=admin
export ADMIN_PASS=change-me
make down && make up
```

---

## 🧪 Admin Workflow

1. Create or edit a topic in `/admin/topics`.
2. Click `Generate` to create a run and enqueue async generation.
3. Open the run page:
   - review FR/EN artifacts
   - edit MDX
   - mark both as reviewed
4. Ensure export gates pass.
5. Click `Export FR + EN`.

Files are written to:

- `BLOG_REPO_PATH/src/content/blog/fr/{slug}.mdx`
- `BLOG_REPO_PATH/src/content/blog/en/{slug}.mdx`

---

## 📦 Batch Generation

- Create batch: `/admin/batches`
- View batch: `/admin/batches/{id}`
- Trigger manual poll: `Poll now`

Requires:

```bash
OPENAI_API_KEY=...
BLOG_REPO_PATH=../datasaaslab-blog
```

---

## ⚙️ Environment Variables

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5
BLOG_REPO_PATH=../datasaaslab-blog
ADMIN_USER=admin
ADMIN_PASS=change-me
```

---

## 🤖 AI Usage Policy

AI generates drafts and suggestions only.

All content is:

- reviewed by a human
- technically validated
- edited before export

No client data or confidential information is stored in this repository.

---

## 📄 License

MIT
