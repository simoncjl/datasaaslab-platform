import json
from datetime import datetime, timezone
from uuid import UUID

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models import Artifact, ArtifactLang, Run, RunStatus


RESPONSE_SCHEMA = {
    "name": "run_generation_result",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "meta": {
                "type": "object",
                "additionalProperties": True,
            },
            "artifacts": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fr": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "frontmatter": {"type": "object", "additionalProperties": True},
                            "body_mdx": {"type": "string"},
                        },
                        "required": ["frontmatter", "body_mdx"],
                    },
                    "en": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "frontmatter": {"type": "object", "additionalProperties": True},
                            "body_mdx": {"type": "string"},
                        },
                        "required": ["frontmatter", "body_mdx"],
                    },
                },
                "required": ["fr", "en"],
            },
        },
        "required": ["meta", "artifacts"],
    },
}


def _build_prompt(topic) -> str:
    payload = {
        "topic": {
            "id": str(topic.id),
            "slug": topic.slug,
            "tags": topic.tags,
            "fr": topic.fr_content,
            "en": topic.en_content,
            "context": topic.context,
            "constraints": topic.constraints_json,
            "author_inputs": topic.author_inputs,
        },
        "instructions": {
            "goal": "Generate two artifacts (fr/en) in MDX with frontmatter.",
            "output": "Must exactly match the JSON schema.",
        },
    }
    return json.dumps(payload, ensure_ascii=True)


def _parse_response_json(response) -> dict:
    parsed = getattr(response, "output_parsed", None)
    if isinstance(parsed, dict):
        return parsed

    output_text = getattr(response, "output_text", None)
    if output_text:
        return json.loads(output_text)

    if hasattr(response, "model_dump"):
        raw = response.model_dump()
        text = raw.get("output_text")
        if text:
            return json.loads(text)

    raise ValueError("OpenAI response did not include parseable JSON output")


def _upsert_artifact(session, run_id: UUID, lang: ArtifactLang, payload: dict) -> None:
    artifact = session.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.lang == lang))
    if artifact is None:
        artifact = Artifact(
            run_id=run_id,
            lang=lang,
            frontmatter=payload["frontmatter"],
            body_mdx=payload["body_mdx"],
            reviewed=False,
            review_notes=None,
        )
        session.add(artifact)
        return

    artifact.frontmatter = payload["frontmatter"]
    artifact.body_mdx = payload["body_mdx"]
    artifact.reviewed = False
    artifact.review_notes = None


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
                        "content": [{"type": "input_text", "text": _build_prompt(run.topic)}],
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

            payload = _parse_response_json(response)
            run.meta = payload["meta"]

            _upsert_artifact(session, run.id, ArtifactLang.FR, payload["artifacts"]["fr"])
            _upsert_artifact(session, run.id, ArtifactLang.EN, payload["artifacts"]["en"])

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
