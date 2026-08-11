from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    customer_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255), index=True)
    document_type: Mapped[str] = mapped_column(String(64), index=True)
    owner_role: Mapped[str] = mapped_column(String(32), default="manager")
    classification: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True, default="draft")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    document: Mapped[Document] = relationship(back_populates="versions")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[DocumentVersion] = relationship(back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    packaging_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    list_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SupplierCost(Base):
    __tablename__ = "supplier_costs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), index=True)
    supplier: Mapped[str] = mapped_column(String(255))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="approved", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)


class LogisticsRate(Base):
    __tablename__ = "logistics_rates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    destination: Mapped[str] = mapped_column(String(120), index=True)
    incoterm: Mapped[str] = mapped_column(String(16), index=True)
    base_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    fee_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    duty_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="approved")


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    base_currency: Mapped[str] = mapped_column(String(8), index=True)
    quote_currency: Mapped[str] = mapped_column(String(8), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    as_of: Mapped[date] = mapped_column(Date, index=True)


class CustomerPolicy(Base):
    __tablename__ = "customer_policies"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(255))
    standard_margin: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    hard_margin: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    management_floor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class HistoricalQuote(Base):
    __tablename__ = "historical_quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8))
    incoterm: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer)
    quoted_at: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(32), default="approved")
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sender: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class Inquiry(Base):
    __tablename__ = "inquiries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    inbox_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("inbox_messages.id"), nullable=True
    )
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(64), index=True, default="received")
    raw_text: Mapped[str] = mapped_column(Text)
    extracted_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    trace_id: Mapped[str] = mapped_column(String(36), default=new_id, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuoteDraft(Base):
    __tablename__ = "quote_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    inquiry_id: Mapped[str] = mapped_column(ForeignKey("inquiries.id"), unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    proposed_unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    public_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    internal_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    draft_text: Mapped[str] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quote_drafts.id"), index=True)
    approver_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(32), default="running")
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cases_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
