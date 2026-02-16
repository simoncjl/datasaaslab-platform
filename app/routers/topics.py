from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Topic
from app.schemas import TopicCreate, TopicOut, TopicPatch

router = APIRouter(prefix="/topics", tags=["topics"])


@router.post("", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(payload: TopicCreate, db: Session = Depends(get_db)) -> Topic:
    topic = Topic(
        slug=payload.slug,
        tags=payload.tags,
        fr_content=payload.fr,
        en_content=payload.en,
        context=payload.context,
        constraints_json=payload.constraints,
        author_inputs=payload.author_inputs,
    )
    db.add(topic)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Topic slug already exists") from exc
    db.refresh(topic)
    return topic


@router.get("", response_model=list[TopicOut])
def list_topics(db: Session = Depends(get_db)) -> list[Topic]:
    return list(db.scalars(select(Topic).order_by(Topic.created_at.desc())))


@router.get("/{id}", response_model=TopicOut)
def get_topic(id: UUID, db: Session = Depends(get_db)) -> Topic:
    topic = db.get(Topic, id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


@router.patch("/{id}", response_model=TopicOut)
def patch_topic(id: UUID, payload: TopicPatch, db: Session = Depends(get_db)) -> Topic:
    topic = db.get(Topic, id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    updates = payload.model_dump(exclude_unset=True)
    if "slug" in updates:
        topic.slug = updates["slug"]
    if "tags" in updates:
        topic.tags = updates["tags"]
    if "fr" in updates:
        topic.fr_content = updates["fr"]
    if "en" in updates:
        topic.en_content = updates["en"]
    if "context" in updates:
        topic.context = updates["context"]
    if "constraints" in updates:
        topic.constraints_json = updates["constraints"]
    if "author_inputs" in updates:
        topic.author_inputs = updates["author_inputs"]

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Topic slug already exists") from exc
    db.refresh(topic)
    return topic
