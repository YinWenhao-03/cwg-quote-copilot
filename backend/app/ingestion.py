from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from .audit import record_audit
from .config import get_settings
from .document_parser import DocumentParser, chunk_blocks, stable_chunk_id
from .models import Chunk, Document, DocumentVersion, IngestionJob
from .search import get_search_service


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_document_version(
    db: Session,
    *,
    source_path: Path,
    title: str,
    document_type: str,
    classification: str,
    status: str = "approved",
    valid_from: date | None = None,
    valid_to: date | None = None,
    customer_id: str | None = None,
    sku: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[DocumentVersion, bool]:
    content_hash = file_sha256(source_path)
    existing = db.scalar(
        select(DocumentVersion).where(DocumentVersion.content_hash == content_hash)
    )
    if existing:
        return existing, False

    document = db.scalar(
        select(Document).where(
            Document.title == title,
            Document.document_type == document_type,
            Document.customer_id == customer_id,
            Document.sku == sku,
        )
    )
    if document is None:
        document = Document(
            title=title,
            document_type=document_type,
            classification=classification,
            customer_id=customer_id,
            sku=sku,
            owner_role="manager" if classification == "management" else classification,
        )
        db.add(document)
        db.flush()

    version_number = (
        db.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        or 0
    )
    if status == "approved":
        for old_version in db.scalars(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.status == "approved",
            )
        ):
            old_version.status = "superseded"

    destination = (
        get_settings().documents_dir
        / document.id
        / f"v{version_number + 1}{source_path.suffix.lower()}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number + 1,
        content_hash=content_hash,
        source_path=str(destination),
        status=status,
        valid_from=valid_from,
        valid_to=valid_to,
        metadata_json=metadata or {},
    )
    db.add(version)
    db.flush()
    db.add(IngestionJob(version_id=version.id, status="pending"))
    record_audit(
        db,
        trace_id=version.id,
        action="document.version_created",
        resource_type="document_version",
        resource_id=version.id,
        detail={"title": title, "version": version.version_number},
    )
    return version, True


def process_job(db: Session, job: IngestionJob) -> None:
    job.status = "processing"
    job.attempts += 1
    job.updated_at = datetime.now(UTC)
    db.commit()
    try:
        version = db.scalar(
            select(DocumentVersion)
            .options(joinedload(DocumentVersion.document))
            .where(DocumentVersion.id == job.version_id)
        )
        if version is None:
            raise ValueError("Document version not found")
        parser = DocumentParser()
        parsed = parser.parse(Path(version.source_path))
        parsed_chunks = chunk_blocks(parsed)
        db.execute(delete(Chunk).where(Chunk.version_id == version.id))
        chunks: list[Chunk] = []
        for ordinal, parsed_chunk in enumerate(parsed_chunks, start=1):
            chunk = Chunk(
                id=stable_chunk_id(version.id, ordinal, parsed_chunk.content),
                version_id=version.id,
                ordinal=ordinal,
                content=parsed_chunk.content,
                page=parsed_chunk.page,
                section=parsed_chunk.section,
                metadata_json=version.metadata_json,
            )
            db.add(chunk)
            chunks.append(chunk)
        db.flush()
        if not get_settings().defer_indexing:
            search = get_search_service()
            for chunk in chunks:
                search.upsert_chunk(chunk, version)
        job.status = "completed"
        job.error_message = None
        record_audit(
            db,
            trace_id=version.id,
            action="document.indexed",
            resource_type="document_version",
            resource_id=version.id,
            detail={"chunks": len(chunks)},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        current_job = db.get(IngestionJob, job.id)
        if current_job:
            current_job.status = "failed" if current_job.attempts >= 3 else "pending"
            current_job.error_message = str(exc)
            current_job.available_at = datetime.now(UTC) + timedelta(
                seconds=5 * current_job.attempts
            )
            current_job.updated_at = datetime.now(UTC)
            db.commit()
        raise


def process_pending_jobs(db: Session, *, limit: int = 10, raise_errors: bool = False) -> int:
    jobs = list(
        db.scalars(
            select(IngestionJob)
            .where(
                IngestionJob.status == "pending",
                IngestionJob.available_at <= datetime.now(UTC),
            )
            .order_by(IngestionJob.created_at)
            .limit(limit)
        )
    )
    completed = 0
    for job in jobs:
        try:
            process_job(db, job)
            completed += 1
        except Exception:
            if raise_errors:
                raise
    if completed and not get_settings().defer_indexing:
        get_search_service().rebuild(db)
    return completed
