from datetime import datetime, timezone
from uuid import UUID

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.generation import RESPONSE_SCHEMA, build_prompt, parse_response_json, upsert_artifact
from app.models import ArtifactLang, Run, RunStatus


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def generate_run(self, run_id: str) -> dict:
    with SessionLocal() as session:
        run = session.scalar(select(Run).options(selectinload(Run.topic)).where(Run.id == UUID(run_id)))
        if run is None:
            return {"status": "not_found", "run_id": run_id}

        if run.status in (RunStatus.RUNNING, RunStatus.SUCCEEDED):
            return {"status": "skipped", "reason": f"run already {run.status.value}", "run_id": run_id}

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.error = None
        session.commit()

        try:
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.responses.create(
                model=run.model or settings.openai_model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": "You are a precise content generation engine."}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": build_prompt(run.topic)}],
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": RESPONSE_SCHEMA["name"],
                        "strict": RESPONSE_SCHEMA["strict"],
                        "schema": RESPONSE_SCHEMA["schema"],
                    }
                },
            )

            payload = parse_response_json(response)
            run.meta = payload["meta"]

            upsert_artifact(session, run.id, ArtifactLang.FR, payload["artifacts"]["fr"])
            upsert_artifact(session, run.id, ArtifactLang.EN, payload["artifacts"]["en"])

            run.status = RunStatus.SUCCEEDED
            run.finished_at = datetime.now(timezone.utc)
            run.error = None
            session.commit()

            return {"status": "succeeded", "run_id": run_id}

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            run.error = str(exc)
            session.commit()
            raise
