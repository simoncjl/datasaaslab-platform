import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, ArtifactLang, Topic

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


def build_prompt(topic: Topic) -> str:
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


def parse_response_json(response: Any) -> dict[str, Any]:
    parsed = getattr(response, "output_parsed", None)
    if isinstance(parsed, dict):
        return parsed

    output_text = getattr(response, "output_text", None)
    if output_text:
        return json.loads(output_text)

    if hasattr(response, "model_dump"):
        raw = response.model_dump()
        return parse_response_json_from_body(raw)

    raise ValueError("OpenAI response did not include parseable JSON output")


def parse_response_json_from_body(body: dict[str, Any]) -> dict[str, Any]:
    output_text = body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return json.loads(output_text)

    for output in body.get("output", []) or []:
        for content in output.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str) and text.strip().startswith("{"):
                return json.loads(text)

    raise ValueError("Batch response body did not include parseable JSON output")


def upsert_artifact(session: Session, run_id: UUID, lang: ArtifactLang, payload: dict[str, Any]) -> None:
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
