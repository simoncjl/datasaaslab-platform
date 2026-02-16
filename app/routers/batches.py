from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.batch_pipeline import create_openai_batch
from app.batch_tasks import poll_batch
from app.dependencies import get_db
from app.models import Batch
from app.schemas import BatchCreate, BatchOut, BatchPollResponse

router = APIRouter(tags=["batches"])


@router.post("/batches", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)) -> Batch:
    if not payload.topic_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="topic_ids must not be empty")

    try:
        batch = create_openai_batch(db, payload.topic_ids, payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Batch submission failed: {exc}") from exc

    return db.scalar(select(Batch).options(selectinload(Batch.items)).where(Batch.id == batch.id))


@router.get("/batches/{id}", response_model=BatchOut)
def get_batch(id: UUID, db: Session = Depends(get_db)) -> Batch:
    batch = db.scalar(select(Batch).options(selectinload(Batch.items)).where(Batch.id == id))
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return batch


@router.post("/batches/{id}/poll", response_model=BatchPollResponse)
def trigger_batch_poll(id: UUID, db: Session = Depends(get_db)) -> BatchPollResponse:
    batch = db.get(Batch, id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    if not batch.openai_batch_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Batch has no openai_batch_id")

    task = poll_batch.delay(str(id))
    refreshed = db.scalar(select(Batch).options(selectinload(Batch.items)).where(Batch.id == id))
    return BatchPollResponse(batch=refreshed, task_id=task.id)
