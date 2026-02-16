import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.generation import RESPONSE_SCHEMA, build_prompt, parse_response_json_from_body, upsert_artifact
from app.models import ArtifactLang, Batch, BatchItem, BatchStatus, Run, RunStatus, Topic


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _build_request_line(run: Run, topic: Topic, model: str) -> dict[str, Any]:
    return {
        "custom_id": f"run:{run.id}",
        "method": "POST",
        "url": "/v1/responses",
        "body": {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": "You are a precise content generation engine."}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": build_prompt(topic)}],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": RESPONSE_SCHEMA["name"],
                    "strict": RESPONSE_SCHEMA["strict"],
                    "schema": RESPONSE_SCHEMA["schema"],
                }
            },
        },
    }


def create_openai_batch(db: Session, topic_ids: list[UUID], model: str | None) -> Batch:
    topics = list(db.scalars(select(Topic).where(Topic.id.in_(topic_ids))))
    topic_map = {topic.id: topic for topic in topics}
    missing = [str(topic_id) for topic_id in topic_ids if topic_id not in topic_map]
    if missing:
        raise ValueError(f"Topic IDs not found: {', '.join(missing)}")

    batch_model = model or settings.openai_model
    batch = Batch(status=BatchStatus.QUEUED, model=batch_model)
    db.add(batch)
    db.flush()

    lines: list[dict[str, Any]] = []
    for topic_id in topic_ids:
        topic = topic_map[topic_id]
        run = Run(topic_id=topic.id, status=RunStatus.QUEUED, model=batch_model, meta={})
        db.add(run)
        db.flush()

        line = _build_request_line(run, topic, batch_model)
        lines.append(line)

        db.add(
            BatchItem(
                batch_id=batch.id,
                run_id=run.id,
                topic_id=topic.id,
                custom_id=line["custom_id"],
                status=BatchStatus.QUEUED,
            )
        )

    db.commit()
    db.refresh(batch)

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
            tmp_path = tmp.name
            for line in lines:
                tmp.write(json.dumps(line, ensure_ascii=True) + "\n")

        client = _client()
        with open(tmp_path, "rb") as file_handle:
            uploaded = client.files.create(file=file_handle, purpose="batch")

        batch_job = client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/responses",
            completion_window="24h",
        )

        batch.openai_batch_id = batch_job.id
        batch.status = BatchStatus.RUNNING
        batch.error = None
        db.commit()
        db.refresh(batch)
        return batch

    except Exception as exc:
        batch.status = BatchStatus.FAILED
        batch.error = str(exc)

        for item in batch.items:
            item.status = BatchStatus.FAILED
            item.error = f"Batch submission failed: {exc}"
            run = item.run
            run.status = RunStatus.FAILED
            run.error = str(exc)
            run.finished_at = datetime.now(timezone.utc)

        db.commit()
        raise
    finally:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _extract_file_text(file_content: Any) -> str:
    text = getattr(file_content, "text", None)
    if isinstance(text, str):
        return text

    read_method = getattr(file_content, "read", None)
    if callable(read_method):
        data = read_method()
        if isinstance(data, bytes):
            return data.decode("utf-8")
        if isinstance(data, str):
            return data

    if isinstance(file_content, bytes):
        return file_content.decode("utf-8")

    raise ValueError("Unable to decode OpenAI batch output file")


def _to_batch_status(openai_status: str) -> BatchStatus:
    if openai_status in {"validating", "in_progress", "finalizing"}:
        return BatchStatus.RUNNING
    if openai_status == "completed":
        return BatchStatus.SUCCEEDED
    return BatchStatus.FAILED


def poll_openai_batch(db: Session, batch_id: UUID) -> Batch:
    batch = db.scalar(select(Batch).options(selectinload(Batch.items).selectinload(BatchItem.run)).where(Batch.id == batch_id))
    if batch is None:
        raise ValueError("Batch not found")
    if not batch.openai_batch_id:
        raise ValueError("Batch has no openai_batch_id")

    client = _client()
    remote = client.batches.retrieve(batch.openai_batch_id)
    remote_status = getattr(remote, "status", "")

    if remote_status in {"validating", "in_progress", "finalizing"}:
        batch.status = BatchStatus.RUNNING
        db.commit()
        db.refresh(batch)
        return batch

    if remote_status != "completed":
        batch.status = BatchStatus.FAILED
        batch.error = f"OpenAI batch ended with status={remote_status}"
        for item in batch.items:
            if item.status not in (BatchStatus.SUCCEEDED, BatchStatus.FAILED):
                item.status = BatchStatus.FAILED
                item.error = batch.error
                item.run.status = RunStatus.FAILED
                item.run.error = batch.error
                item.run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(batch)
        return batch

    output_file_id = getattr(remote, "output_file_id", None)
    if not output_file_id:
        batch.status = BatchStatus.FAILED
        batch.error = "OpenAI batch completed without output_file_id"
        db.commit()
        db.refresh(batch)
        return batch

    file_content = client.files.content(output_file_id)
    lines_text = _extract_file_text(file_content)

    results_by_custom_id: dict[str, dict[str, Any]] = {}
    for line in lines_text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        custom_id = row.get("custom_id")
        if custom_id:
            results_by_custom_id[custom_id] = row

    now = datetime.now(timezone.utc)
    succeeded_count = 0

    for item in batch.items:
        row = results_by_custom_id.get(item.custom_id)
        if row is None:
            item.status = BatchStatus.FAILED
            item.error = "No batch output row for custom_id"
            item.run.status = RunStatus.FAILED
            item.run.error = item.error
            item.run.finished_at = now
            continue

        error = row.get("error")
        response = row.get("response") or {}
        status_code = response.get("status_code")
        body = response.get("body") or {}
        item.response_code = status_code

        if error:
            item.status = BatchStatus.FAILED
            item.error = str(error)
            item.run.status = RunStatus.FAILED
            item.run.error = item.error
            item.run.finished_at = now
            continue

        if isinstance(status_code, int) and status_code >= 400:
            item.status = BatchStatus.FAILED
            item.error = json.dumps(body)[:2000]
            item.run.status = RunStatus.FAILED
            item.run.error = item.error
            item.run.finished_at = now
            continue

        try:
            payload = parse_response_json_from_body(body)
            item.run.meta = payload["meta"]
            upsert_artifact(db, item.run.id, ArtifactLang.FR, payload["artifacts"]["fr"])
            upsert_artifact(db, item.run.id, ArtifactLang.EN, payload["artifacts"]["en"])
            item.run.status = RunStatus.SUCCEEDED
            if item.run.started_at is None:
                item.run.started_at = now
            item.run.finished_at = now
            item.run.error = None
            item.status = BatchStatus.SUCCEEDED
            item.error = None
            succeeded_count += 1
        except Exception as exc:
            item.status = BatchStatus.FAILED
            item.error = str(exc)
            item.run.status = RunStatus.FAILED
            item.run.error = str(exc)
            item.run.finished_at = now

    if succeeded_count == len(batch.items):
        batch.status = BatchStatus.SUCCEEDED
        batch.error = None
    else:
        batch.status = BatchStatus.FAILED
        batch.error = f"{len(batch.items) - succeeded_count} of {len(batch.items)} items failed"

    db.commit()
    db.refresh(batch)
    return batch
