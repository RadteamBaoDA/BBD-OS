from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from core.database import Base


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"
    __table_args__ = (UniqueConstraint("source_id", "batch_key", name="uq_ingestion_batches_source_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False)
    batch_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_ingestion_runs_status"),
        Index("ix_ingestion_runs_source_created", "source_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ingestion_batches.id", ondelete="CASCADE"), unique=True, nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class IngestionStage(Base):
    __tablename__ = "ingestion_stages"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", name="uq_ingestion_stages_run_key"),
        CheckConstraint("status IN ('pending', 'queued', 'running', 'retrying', 'succeeded', 'failed')", name="ck_ingestion_stages_status"),
        Index("ix_ingestion_stages_pending", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    stage_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SourceObservation(Base):
    __tablename__ = "source_observations"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "provider_id", "record_hash", "observed_at",
            name="uq_source_observations_batch_record_observed",
        ),
        Index("ix_source_observations_source_observed", "source_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ingestion_batches.id", ondelete="CASCADE"), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(512), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceIngestionState(Base):
    __tablename__ = "source_ingestion_state"

    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    lease_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL"))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CollectorCredential(Base):
    __tablename__ = "collector_credentials"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, server_default="ingestion:write")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventOutbox(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'queued', 'delivered', 'failed')", name="ck_event_outbox_status"),
        Index("ix_event_outbox_dispatch", "status", "dispatched_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    producer: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
