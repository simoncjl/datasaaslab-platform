from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import ArtifactLang, BatchStatus, RunStatus


class TopicCreate(BaseModel):
    slug: str
    tags: dict[str, Any] = Field(default_factory=dict)
    fr: dict[str, Any] = Field(default_factory=dict)
    en: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    author_inputs: dict[str, Any] = Field(default_factory=dict)


class TopicPatch(BaseModel):
    slug: str | None = None
    tags: dict[str, Any] | None = None
    fr: dict[str, Any] | None = None
    en: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    author_inputs: dict[str, Any] | None = None


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    tags: dict[str, Any]
    fr_content: dict[str, Any] = Field(serialization_alias="fr")
    en_content: dict[str, Any] = Field(serialization_alias="en")
    context: dict[str, Any]
    constraints_json: dict[str, Any] = Field(serialization_alias="constraints")
    author_inputs: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    model: str | None = None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic_id: UUID
    status: RunStatus
    model: str | None
    error: str | None
    meta: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArtifactPatch(BaseModel):
    frontmatter: dict[str, Any] | None = None
    body_mdx: str | None = None
    reviewed: bool | None = None
    review_notes: str | None = None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    lang: ArtifactLang
    frontmatter: dict[str, Any]
    body_mdx: str
    reviewed: bool
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class RunCreateResponse(BaseModel):
    run: RunOut
    task_id: str


class ExportResponse(BaseModel):
    run_id: UUID
    slug: str
    files: dict[str, str]


class ExportConflictResponse(BaseModel):
    detail: str
    reasons: list[str]


class BatchCreate(BaseModel):
    topic_ids: list[UUID]
    model: str | None = None


class BatchItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    run_id: UUID
    topic_id: UUID
    custom_id: str
    status: BatchStatus
    response_code: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model: str | None
    status: BatchStatus
    openai_batch_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    items: list[BatchItemOut] = Field(default_factory=list)


class BatchPollResponse(BaseModel):
    batch: BatchOut
    task_id: str
