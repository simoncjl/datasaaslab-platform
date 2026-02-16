from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BatchStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ArtifactLang(str, Enum):
    FR = "fr"
    EN = "en"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fr_content: Mapped[dict] = mapped_column("fr", JSONB, nullable=False, default=dict)
    en_content: Mapped[dict] = mapped_column("en", JSONB, nullable=False, default=dict)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    constraints_json: Mapped[dict] = mapped_column("constraints", JSONB, nullable=False, default=dict)
    author_inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    runs: Mapped[list["Run"]] = relationship(back_populates="topic", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_topics_slug", "slug", unique=True),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        SQLEnum(RunStatus, name="run_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=RunStatus.QUEUED,
    )
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    topic: Mapped[Topic] = relationship(back_populates="runs")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    batches: Mapped[list["Batch"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_runs_topic_id_status", "topic_id", "status"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    lang: Mapped[ArtifactLang] = mapped_column(
        SQLEnum(ArtifactLang, name="artifact_lang", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    frontmatter: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    body_mdx: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed: Mapped[bool] = mapped_column(nullable=False, default=False)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="artifacts")

    __table_args__ = (
        Index("ix_artifacts_run_id_lang", "run_id", "lang"),
    )


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[BatchStatus] = mapped_column(
        SQLEnum(BatchStatus, name="batch_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=BatchStatus.QUEUED,
    )
    openai_batch_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="batches")
