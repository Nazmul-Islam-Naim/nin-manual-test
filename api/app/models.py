from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Manual(Base):
    __tablename__ = "manuals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(8))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # never returned
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)  # naive, stored as UTC


class TestRun(Base):
    __test__ = False  # not a pytest class
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    manual_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuals.id"), index=True)
    base_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(16))  # created|parsing|parsed|running|done|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sweep_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # menu sweep truncation note
    created_at: Mapped[datetime] = mapped_column(DateTime)  # naive, stored as UTC
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # naive UTC, execution start
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # naive UTC, done/failed
    max_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # effective time limit


class TestCase(Base):
    __test__ = False
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer)


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_cases.id"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    unclear: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # validation case: kind, category, field, form, source


class FieldRule(Base):
    """Field-level rule extracted from the manual (replaced on re-parse)."""
    __tablename__ = "field_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id"), index=True)
    field: Mapped[str] = mapped_column(Text)
    rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid: Mapped[list] = mapped_column(JSON)
    invalid: Mapped[list] = mapped_column(JSON)


class StepResult(Base):
    """Outcome of one executed step (one row per step). Spec 005 adopts this table."""
    __tablename__ = "step_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("steps.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16))  # running|passed|failed|warning
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    console_errors: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # relative to STORAGE_DIR
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # sanitized, no fragment
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # console_messages, failed_requests, excerpt
