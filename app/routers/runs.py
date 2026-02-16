from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Artifact, Run, RunStatus, Topic
from app.schemas import ArtifactOut, ArtifactPatch, RunCreate, RunCreateResponse, RunOut
from app.tasks import generate_run

router = APIRouter(tags=["runs"])


@router.post("/topics/{id}/runs", response_model=RunCreateResponse, status_code=status.HTTP_201_CREATED)
def create_topic_run(id: UUID, payload: RunCreate, db: Session = Depends(get_db)) -> RunCreateResponse:
    topic = db.get(Topic, id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    run = Run(topic_id=topic.id, status=RunStatus.QUEUED, model=payload.model, meta={})
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        task = generate_run.delay(str(run.id))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Run created but task enqueue failed: {exc}",
        ) from exc
    return RunCreateResponse(run=run, task_id=task.id)


@router.get("/runs/{id}", response_model=RunOut)
def get_run(id: UUID, db: Session = Depends(get_db)) -> Run:
    run = db.get(Run, id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("/runs/{id}/artifacts", response_model=list[ArtifactOut])
def list_run_artifacts(id: UUID, db: Session = Depends(get_db)) -> list[Artifact]:
    run = db.get(Run, id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return list(db.scalars(select(Artifact).where(Artifact.run_id == id).order_by(Artifact.created_at.asc())))


@router.patch("/artifacts/{id}", response_model=ArtifactOut)
def patch_artifact(id: UUID, payload: ArtifactPatch, db: Session = Depends(get_db)) -> Artifact:
    artifact = db.get(Artifact, id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(artifact, key, value)

    db.commit()
    db.refresh(artifact)
    return artifact
