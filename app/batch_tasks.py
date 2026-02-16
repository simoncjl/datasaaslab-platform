from uuid import UUID

from app.batch_pipeline import poll_openai_batch
from app.celery_app import celery_app
from app.db import SessionLocal


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def poll_batch(self, batch_id: str) -> dict:
    with SessionLocal() as db:
        batch = poll_openai_batch(db, UUID(batch_id))
        return {
            "batch_id": str(batch.id),
            "status": batch.status.value,
            "openai_batch_id": batch.openai_batch_id,
            "error": batch.error,
        }
