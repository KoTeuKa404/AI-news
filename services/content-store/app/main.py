from __future__ import annotations

import ipaddress
import re
import socket
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Generator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import BIGINT, Boolean, DateTime, Index, Integer, Numeric, String, create_engine, desc, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTENT_STORE_", extra="ignore")

    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "n8n"
    db_user: str = "n8n"
    db_password: str = "change_me"
    min_confidence: float = 0.70
    min_quality_score: float = 0.70
    processing_max_attempts: int = 3
    processing_retry_delay_seconds: int = 300
    processing_stale_seconds: int = 1800
    fetch_timeout_seconds: int = 10
    fetch_max_bytes: int = 1_500_000
    allowed_source_hosts: str = ""
    default_client_id: str = "telegram-default"


settings = Settings()


class Base(DeclarativeBase):
    pass


class ContentCandidate(Base):
    __tablename__ = "content_candidates"
    __table_args__ = (
        Index("idx_content_candidates_status", "status", "created_at"),
        Index("idx_content_candidates_source_url", "source_url"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String, nullable=False, default=lambda: settings.default_client_id)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_title: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_text: Mapped[str | None] = mapped_column(String, nullable=True)
    relevant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    draft_title: Mapped[str | None] = mapped_column(String, nullable=True)
    draft_text: Mapped[str | None] = mapped_column(String, nullable=True)
    final_title: Mapped[str | None] = mapped_column(String, nullable=True)
    final_text: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    risks: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    suggested_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="processing")
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_message_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    published_chat_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_analysis: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ModerationEvent(Base):
    __tablename__ = "moderation_events"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(BIGINT, nullable=False, index=True)
    moderator_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    original_title: Mapped[str | None] = mapped_column(String, nullable=True)
    original_text: Mapped[str | None] = mapped_column(String, nullable=True)
    edited_title: Mapped[str | None] = mapped_column(String, nullable=True)
    edited_text: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ClientStyleProfile(Base):
    __tablename__ = "client_style_profiles"

    client_id: Mapped[str] = mapped_column(String, primary_key=True)
    client_name: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_text: Mapped[str | None] = mapped_column(String, nullable=True)
    rules: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class StyleReviewPrediction(Base):
    __tablename__ = "style_review_predictions"
    __table_args__ = (Index("idx_style_review_predictions_candidate", "candidate_id", "created_at"),)

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="low")
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    likely_edits: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    risk_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(String, nullable=False, default="")
    ai_model: Mapped[str] = mapped_column(String, nullable=False, default="local-main")
    raw_review: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MetricEvent(Base):
    __tablename__ = "pipeline_metric_events"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    candidate_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ErrorEvent(Base):
    __tablename__ = "pipeline_error_events"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    workflow_name: Mapped[str | None] = mapped_column(String, nullable=True)
    node_name: Mapped[str | None] = mapped_column(String, nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def database_url() -> URL:
    return URL.create("postgresql+psycopg", username=settings.db_user, password=settings.db_password, host=settings.db_host, port=settings.db_port, database=settings.db_name)


engine = create_engine(database_url(), pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def wait_for_database() -> None:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(select(1))
            return
        except Exception as error:  # pragma: no cover
            last_error = error
            time.sleep(1)
    raise RuntimeError(f"PostgreSQL is unavailable: {last_error}")


def ensure_schema() -> None:
    statements = [
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS client_id TEXT NOT NULL DEFAULT 'telegram-default'",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS source_published_at TIMESTAMPTZ",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS source_text TEXT",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS final_title TEXT",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS final_text TEXT",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS reason TEXT",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS risks JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS suggested_tags JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS processing_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS last_error TEXT",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS moderated_at TIMESTAMPTZ",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS channel_published_at TIMESTAMPTZ",
        "ALTER TABLE content_candidates ADD COLUMN IF NOT EXISTS published_chat_id BIGINT",
        "UPDATE content_candidates SET source_published_at = published_at WHERE source_published_at IS NULL AND published_at IS NOT NULL",
        "UPDATE content_candidates SET updated_at = COALESCE(updated_at, created_at, NOW()) WHERE updated_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_content_candidates_processing ON content_candidates(status, next_retry_at)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    wait_for_database()
    Base.metadata.create_all(engine)
    ensure_schema()
    yield
    engine.dispose()


app = FastAPI(title="3M Content Store", version="2.0.0", lifespan=lifespan)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class ReserveRequest(BaseModel):
    dedupe_key: str = Field(min_length=1, max_length=2048)
    client_id: str = Field(default="telegram-default", min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=100)
    source_title: str = Field(min_length=1, max_length=2000)
    source_url: str = Field(min_length=1, max_length=4000)
    source_published_at: datetime | None = None
    published_at: datetime | None = None
    source_text: str = Field(default="", max_length=20000)


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dedupe_key: str
    client_id: str = "telegram-default"
    status: str
    is_new: bool = False
    processing_attempts: int = 0


class AnalysisRequest(BaseModel):
    relevant: bool
    confidence: float = Field(ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)
    draft_title: str = Field(default="", max_length=500)
    draft_text: str = Field(default="", max_length=12000)
    reason: str = Field(default="", max_length=4000)
    risks: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)
    language_ok: bool = True
    ai_model: str = "local-main"
    raw_analysis: dict[str, Any] = Field(default_factory=dict)
    regenerate: bool = False


class AnalysisResponse(BaseModel):
    id: int
    accepted: bool
    status: str


class ModerationResponse(BaseModel):
    id: int
    client_id: str = "telegram-default"
    status: str
    can_publish: bool = False
    draft_title: str | None = None
    draft_text: str | None = None
    reason: str | None = None
    risks: list[str] = Field(default_factory=list)
    confidence: float | None = None
    quality_score: float | None = None
    source_url: str
    source_title: str | None = None
    source_text: str = ""
    published_message_id: int | None = None
    published_chat_id: int | None = None


class PublishRequest(BaseModel):
    message_id: int = Field(ge=0)
    chat_id: int | None = None


class ModeratorRequest(BaseModel):
    moderator_id: int | None = None


class RejectRequest(ModeratorRequest):
    reason: str = Field(default="інше", max_length=500)


class ReleaseRequest(BaseModel):
    error: str = Field(default="Telegram publication failed", max_length=4000)


class EditRequest(ModeratorRequest):
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=12000)


class SourceFetchRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=4000)
    fallback_text: str = Field(default="", max_length=20000)


class SourceFetchResponse(BaseModel):
    ok: bool
    source_url: str
    article_text: str = ""
    error: str | None = None
    content_length: int = 0


class ErrorRequest(BaseModel):
    workflow_name: str | None = None
    node_name: str | None = None
    execution_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)
    details: dict[str, Any] = Field(default_factory=dict)


class StyleReviewRequest(BaseModel):
    client_id: str = Field(default="telegram-default", min_length=1, max_length=200)
    risk_level: str = Field(default="low", min_length=1, max_length=30)
    confidence: float = Field(default=0, ge=0, le=1)
    likely_edits: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=4000)
    ai_model: str = Field(default="local-main", max_length=200)
    raw_review: dict[str, Any] = Field(default_factory=dict)


def _candidate_response(candidate: ContentCandidate, *, can_publish: bool = False) -> ModerationResponse:
    return ModerationResponse(
        id=candidate.id,
        client_id=candidate.client_id,
        status=candidate.status,
        can_publish=can_publish,
        draft_title=candidate.final_title or candidate.draft_title,
        draft_text=candidate.final_text or candidate.draft_text,
        reason=candidate.reason,
        risks=candidate.risks or [],
        confidence=float(candidate.confidence) if candidate.confidence is not None else None,
        quality_score=float(candidate.quality_score) if candidate.quality_score is not None else None,
        source_url=candidate.source_url,
        source_title=candidate.source_title,
        source_text=candidate.source_text or "",
        published_message_id=candidate.published_message_id,
        published_chat_id=candidate.published_chat_id,
    )


def _metric(session: Session, event_type: str, candidate_id: int | None = None, **details: Any) -> None:
    session.add(MetricEvent(event_type=event_type, candidate_id=candidate_id, details=details))


def _moderation_event(session: Session, candidate: ContentCandidate, action: str, moderator_id: int | None = None, reject_reason: str | None = None, edited_title: str | None = None, edited_text: str | None = None) -> None:
    session.add(ModerationEvent(candidate_id=candidate.id, moderator_id=moderator_id, action=action, reject_reason=reject_reason, original_title=candidate.draft_title, original_text=candidate.draft_text, edited_title=edited_title, edited_text=edited_text))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "content-store", "version": "2.0.0"}


@app.post("/v1/candidates/reserve", response_model=CandidateResponse)
def reserve_candidate(payload: ReserveRequest, session: Session = Depends(get_session)) -> CandidateResponse:
    created = now_utc()
    source_published_at = payload.source_published_at or payload.published_at
    statement = (
        pg_insert(ContentCandidate)
        .values(dedupe_key=payload.dedupe_key, client_id=payload.client_id.strip() or settings.default_client_id, source=payload.source, source_title=payload.source_title, source_url=payload.source_url, source_published_at=source_published_at, source_text=payload.source_text, status="processing", processing_started_at=created, processing_attempts=1, created_at=created, updated_at=created, raw_analysis={}, risks=[], suggested_tags=[])
        .on_conflict_do_nothing(index_elements=[ContentCandidate.dedupe_key])
        .returning(ContentCandidate.id)
    )
    candidate_id = session.execute(statement).scalar_one_or_none()
    if candidate_id is None:
        session.rollback()
        existing = session.scalar(select(ContentCandidate).where(ContentCandidate.dedupe_key == payload.dedupe_key).with_for_update())
        if not existing:
            raise HTTPException(status_code=409, detail="Dedupe reservation conflict")
        stale_processing = existing.status == "processing" and existing.processing_started_at is not None and existing.processing_started_at <= created - timedelta(seconds=settings.processing_stale_seconds)
        retry_due = existing.next_retry_at is None or existing.next_retry_at <= created
        retryable = existing.status == "failed" or stale_processing
        if retryable and retry_due:
            if existing.processing_attempts >= settings.processing_max_attempts:
                existing.status = "failed"
                existing.last_error = existing.last_error or "Processing attempts exhausted"
                existing.updated_at = created
                session.commit()
            else:
                existing.status = "processing"
                existing.processing_started_at = created
                existing.processing_attempts += 1
                existing.next_retry_at = None
                existing.last_error = None
                existing.updated_at = created
                _metric(session, "reserved_retry", existing.id, attempt=existing.processing_attempts)
                session.commit()
                return CandidateResponse(id=existing.id, dedupe_key=existing.dedupe_key, client_id=existing.client_id, status=existing.status, is_new=True, processing_attempts=existing.processing_attempts)
        return CandidateResponse(id=existing.id, dedupe_key=existing.dedupe_key, client_id=existing.client_id, status=existing.status, is_new=False, processing_attempts=existing.processing_attempts)
    candidate = session.get(ContentCandidate, candidate_id)
    _metric(session, "reserved_new", candidate_id)
    session.commit()
    return CandidateResponse(id=candidate.id, dedupe_key=candidate.dedupe_key, client_id=candidate.client_id, status=candidate.status, is_new=True, processing_attempts=candidate.processing_attempts)


@app.post("/v1/source/fetch", response_model=SourceFetchResponse)
def fetch_source(payload: SourceFetchRequest) -> SourceFetchResponse:
    try:
        article = _fetch_public_article(payload.source_url)
        if article:
            return SourceFetchResponse(ok=True, source_url=payload.source_url, article_text=article, content_length=len(article))
        return SourceFetchResponse(ok=False, source_url=payload.source_url, article_text=payload.fallback_text, error="Article text was empty", content_length=len(payload.fallback_text))
    except Exception as error:
        return SourceFetchResponse(ok=False, source_url=payload.source_url, article_text=payload.fallback_text, error=str(error)[:1000], content_length=len(payload.fallback_text))


@app.patch("/v1/candidates/{candidate_id}/analysis", response_model=AnalysisResponse)
def complete_analysis(candidate_id: int, payload: AnalysisRequest, session: Session = Depends(get_session)) -> AnalysisResponse:
    candidate = session.get(ContentCandidate, candidate_id, with_for_update=True)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if candidate.status != "processing":
        if not payload.regenerate or candidate.status != "pending_review":
            return AnalysisResponse(id=candidate.id, accepted=candidate.status == "pending_review", status=candidate.status)
        candidate.status = "processing"
        candidate.processing_started_at = now_utc()
        candidate.updated_at = candidate.processing_started_at
        _moderation_event(session, candidate, "regenerate")
    title = payload.draft_title.strip()
    body = payload.draft_text.strip()
    accepted = payload.relevant and payload.language_ok and payload.confidence >= settings.min_confidence and payload.quality_score >= settings.min_quality_score and bool(title) and bool(body) and bool(payload.reason.strip()) and _is_http_url(candidate.source_url) and len(title) <= 500 and len(body) <= 12000
    candidate.relevant = payload.relevant
    candidate.confidence = payload.confidence
    candidate.quality_score = payload.quality_score
    candidate.draft_title = title or None
    candidate.draft_text = body or None
    candidate.final_title = title or None
    candidate.final_text = body or None
    candidate.reason = payload.reason.strip() or None
    candidate.risks = payload.risks
    candidate.suggested_tags = payload.suggested_tags
    candidate.ai_model = payload.ai_model
    candidate.raw_analysis = payload.raw_analysis
    candidate.status = "pending_review" if accepted else "filtered"
    candidate.processing_started_at = None
    candidate.updated_at = now_utc()
    candidate.next_retry_at = None
    candidate.last_error = None if accepted else "Deterministic quality/language gate rejected the AI result"
    _metric(session, "ai_completed", candidate.id, accepted=accepted)
    _metric(session, "pending_review" if accepted else "filtered", candidate.id)
    session.commit()
    return AnalysisResponse(id=candidate.id, accepted=accepted, status=candidate.status)


@app.post("/v1/candidates/{candidate_id}/fail", response_model=AnalysisResponse)
def fail_candidate(candidate_id: int, payload: ReleaseRequest, session: Session = Depends(get_session)) -> AnalysisResponse:
    candidate = session.get(ContentCandidate, candidate_id, with_for_update=True)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    current = now_utc()
    candidate.status = "failed"
    candidate.last_error = payload.error
    candidate.next_retry_at = current + timedelta(seconds=settings.processing_retry_delay_seconds) if candidate.processing_attempts < settings.processing_max_attempts else None
    candidate.updated_at = current
    _metric(session, "failed", candidate.id, error=payload.error, retry_scheduled=candidate.next_retry_at is not None, attempts=candidate.processing_attempts)
    session.commit()
    return AnalysisResponse(id=candidate.id, accepted=False, status=candidate.status)


@app.get("/v1/candidates/{candidate_id}", response_model=ModerationResponse)
def get_candidate(candidate_id: int, session: Session = Depends(get_session)) -> ModerationResponse:
    candidate = session.get(ContentCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _candidate_response(candidate)


@app.get("/v1/clients/{client_id}/style-context")
def get_style_context(client_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = session.get(ClientStyleProfile, client_id)
    rows = session.execute(
        select(ModerationEvent, ContentCandidate.source_title)
        .join(ContentCandidate, ContentCandidate.id == ModerationEvent.candidate_id)
        .where(ContentCandidate.client_id == client_id)
        .order_by(desc(ModerationEvent.created_at))
        .limit(30)
    ).all()
    recent_edits: list[dict[str, Any]] = []
    recent_rejections: list[dict[str, Any]] = []
    seen_edits: set[tuple[Any, ...]] = set()
    seen_rejections: set[tuple[Any, ...]] = set()
    approvals = 0
    for event, source_title in rows:
        if event.action == "edit" and len(recent_edits) < 10:
            edit_key = (event.candidate_id, event.original_title, event.edited_title, event.edited_text)
            if edit_key in seen_edits:
                continue
            seen_edits.add(edit_key)
            recent_edits.append({
                "source_title": str(source_title or "")[:300],
                "original_title": str(event.original_title or "")[:500],
                "original_text": str(event.original_text or "")[:1600],
                "edited_title": str(event.edited_title or "")[:500],
                "edited_text": str(event.edited_text or "")[:1600],
            })
        elif event.action == "reject" and len(recent_rejections) < 10:
            rejection_key = (event.candidate_id, event.reject_reason)
            if rejection_key in seen_rejections:
                continue
            seen_rejections.add(rejection_key)
            recent_rejections.append({
                "source_title": str(source_title or "")[:300],
                "reason": str(event.reject_reason or "інше")[:500],
            })
        elif event.action == "approve":
            approvals += 1
    return {
        "client_id": client_id,
        "client_name": profile.client_name if profile else None,
        "profile_text": profile.profile_text if profile else "",
        "rules": profile.rules if profile else [],
        "history_count": len(rows),
        "approved_count_in_sample": approvals,
        "recent_edits": recent_edits,
        "recent_rejections": recent_rejections,
    }


@app.post("/v1/candidates/{candidate_id}/style-review")
def save_style_review(candidate_id: int, payload: StyleReviewRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    candidate = session.get(ContentCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    client_id = candidate.client_id or payload.client_id or settings.default_client_id
    prediction = StyleReviewPrediction(
        candidate_id=candidate.id,
        client_id=client_id,
        risk_level=payload.risk_level.strip().lower() or "low",
        confidence=payload.confidence,
        likely_edits=[str(value).strip()[:500] for value in payload.likely_edits if str(value).strip()][:10],
        risk_flags=[str(value).strip()[:500] for value in payload.risk_flags if str(value).strip()][:10],
        summary=payload.summary.strip()[:4000],
        ai_model=payload.ai_model.strip()[:200] or "local-main",
        raw_review=payload.raw_review,
    )
    session.add(prediction)
    _metric(session, "style_reviewed", candidate.id, client_id=client_id, risk_level=prediction.risk_level)
    session.commit()
    return {"id": prediction.id, "candidate_id": candidate.id, "client_id": client_id, "saved": True}


@app.post("/v1/candidates/{candidate_id}/approve", response_model=ModerationResponse)
def approve_candidate(candidate_id: int, payload: ModeratorRequest | None = None, session: Session = Depends(get_session)) -> ModerationResponse:
    moderator_id = payload.moderator_id if payload else None
    changed = session.execute(update(ContentCandidate).where(ContentCandidate.id == candidate_id, ContentCandidate.status == "pending_review").values(status="publishing", moderated_at=now_utc(), updated_at=now_utc(), last_error=None)).rowcount
    candidate = session.get(ContentCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if changed:
        _moderation_event(session, candidate, "approve", moderator_id=moderator_id)
        _metric(session, "approved", candidate.id)
    session.commit()
    return _candidate_response(candidate, can_publish=bool(changed))


@app.post("/v1/candidates/{candidate_id}/publish", response_model=ModerationResponse)
def mark_published(candidate_id: int, payload: PublishRequest, session: Session = Depends(get_session)) -> ModerationResponse:
    candidate = session.get(ContentCandidate, candidate_id, with_for_update=True)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status == "published":
        if candidate.published_message_id is None:
            candidate.published_message_id = payload.message_id
            candidate.published_chat_id = payload.chat_id
            candidate.channel_published_at = now_utc()
            candidate.updated_at = now_utc()
            session.commit()
        return _candidate_response(candidate)
    if candidate.status != "publishing":
        raise HTTPException(status_code=409, detail="Candidate is not being published")
    candidate.status = "published"
    candidate.published_message_id = payload.message_id
    candidate.published_chat_id = payload.chat_id
    candidate.channel_published_at = now_utc()
    candidate.updated_at = now_utc()
    candidate.last_error = None
    _metric(session, "published", candidate.id)
    session.commit()
    return _candidate_response(candidate)


@app.post("/v1/candidates/{candidate_id}/release", response_model=ModerationResponse)
def release_publication(candidate_id: int, payload: ReleaseRequest | None = None, session: Session = Depends(get_session)) -> ModerationResponse:
    candidate = session.get(ContentCandidate, candidate_id, with_for_update=True)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status == "publishing" and candidate.published_message_id is None:
        candidate.status = "pending_review"
        candidate.last_error = payload.error if payload else "Telegram publication failed"
        candidate.updated_at = now_utc()
        _metric(session, "publication_released", candidate.id, error=candidate.last_error)
        session.commit()
    return _candidate_response(candidate)


@app.post("/v1/candidates/{candidate_id}/reject", response_model=ModerationResponse)
def reject_candidate(candidate_id: int, payload: RejectRequest | None = None, session: Session = Depends(get_session)) -> ModerationResponse:
    moderator_id = payload.moderator_id if payload else None
    reason = (payload.reason if payload else "інше").strip() or "інше"
    changed = session.execute(update(ContentCandidate).where(ContentCandidate.id == candidate_id, ContentCandidate.status == "pending_review").values(status="rejected", moderated_at=now_utc(), updated_at=now_utc(), last_error=reason)).rowcount
    candidate = session.get(ContentCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if changed:
        _moderation_event(session, candidate, "reject", moderator_id=moderator_id, reject_reason=reason)
        _metric(session, "rejected", candidate.id, reason=reason)
    session.commit()
    return _candidate_response(candidate)


@app.patch("/v1/candidates/{candidate_id}/edit", response_model=ModerationResponse)
def edit_candidate(candidate_id: int, payload: EditRequest, session: Session = Depends(get_session)) -> ModerationResponse:
    candidate = session.get(ContentCandidate, candidate_id, with_for_update=True)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status != "pending_review":
        raise HTTPException(status_code=409, detail="Only pending candidates can be edited")
    candidate.final_title = payload.title.strip()
    candidate.final_text = payload.text.strip()
    candidate.updated_at = now_utc()
    _moderation_event(session, candidate, "edit", moderator_id=payload.moderator_id, edited_title=candidate.final_title, edited_text=candidate.final_text)
    session.commit()
    return _candidate_response(candidate)


@app.post("/v1/errors")
def log_error(payload: ErrorRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    event = ErrorEvent(**payload.model_dump())
    session.add(event)
    session.commit()
    return {"ok": True, "id": event.id}


@app.get("/v1/metrics/summary")
def metrics_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    status_rows = session.execute(select(ContentCandidate.status, func.count(ContentCandidate.id)).group_by(ContentCandidate.status)).all()
    event_rows = session.execute(select(MetricEvent.event_type, func.count(MetricEvent.id)).group_by(MetricEvent.event_type)).all()
    return {"candidates_by_status": {str(key): int(value) for key, value in status_rows}, "events": {str(key): int(value) for key, value in event_rows}}


class _ArticleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.skip_tags = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "figure"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.skip_tags:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.parts.append(value)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _allowed_hosts() -> set[str]:
    return {host.strip().lower() for host in settings.allowed_source_hosts.split(",") if host.strip()}


def _validate_public_url(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only http/https URLs are allowed")
    if parts.username or parts.password:
        raise ValueError("Credentials in source URLs are not allowed")
    host = parts.hostname.rstrip(".").lower()
    allowed = _allowed_hosts()
    if allowed and host not in allowed:
        raise ValueError("Source host is not allowlisted")
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as error:
        raise ValueError("Invalid source port") from error
    if port not in {80, 443}:
        raise ValueError("Only ports 80 and 443 are allowed")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Localhost is not allowed")
    try:
        addresses = {result[4][0] for result in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise ValueError("Source host could not be resolved") from error
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("Private or local network destinations are not allowed")


def _is_http_url(value: str) -> bool:
    try:
        _validate_public_url(value)
        return True
    except (ValueError, OSError):
        return False


def _fetch_public_article(source_url: str) -> str:
    _validate_public_url(source_url)
    opener = build_opener(_SafeRedirectHandler())
    request = Request(source_url, headers={"User-Agent": "3M-Agency-ContentBot/1.0", "Accept": "text/html,application/xhtml+xml"})
    with opener.open(request, timeout=settings.fetch_timeout_seconds) as response:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not any(kind in content_type for kind in ("text/html", "application/xhtml", "text/plain")):
            raise ValueError("Source is not an HTML/text document")
        body = response.read(settings.fetch_max_bytes + 1)
        if len(body) > settings.fetch_max_bytes:
            raise ValueError("Source response is too large")
        encoding = response.headers.get_content_charset() or "utf-8"
        decoded = body.decode(encoding, errors="replace")
    parser = _ArticleTextParser()
    parser.feed(decoded)
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:20000]
