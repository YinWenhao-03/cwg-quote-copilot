from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserView(ORMModel):
    id: str
    email: str
    display_name: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class InquiryItem(BaseModel):
    sku: str | None = None
    description: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    packaging: str | None = None


class InquiryData(BaseModel):
    customer_id: str | None = None
    customer_name: str | None = None
    destination: str | None = None
    incoterm: str | None = None
    currency: str | None = None
    requested_delivery_date: str | None = None
    items: list[InquiryItem] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class InquiryCreate(BaseModel):
    raw_text: str = Field(min_length=5)
    inbox_message_id: str | None = None


class InquiryPatch(BaseModel):
    customer_id: str | None = None
    destination: str | None = None
    incoterm: str | None = None
    currency: str | None = None
    requested_delivery_date: str | None = None
    sku: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    packaging: str | None = None


class InquiryView(ORMModel):
    id: str
    inbox_message_id: str | None
    customer_id: str | None
    status: str
    raw_text: str
    extracted_json: dict[str, Any]
    missing_fields: list[str]
    trace_id: str
    created_at: datetime


class Evidence(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    page: int | None = None
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class PricingResult(BaseModel):
    landed_cost: Decimal
    standard_minimum: Decimal
    hard_floor: Decimal
    suggested_price: Decimal
    currency: str
    approval_level: Literal["standard", "exception", "blocked"]
    components: dict[str, Decimal]


class QuoteView(ORMModel):
    id: str
    inquiry_id: str
    version: int
    status: str
    currency: str
    quantity: int
    proposed_unit_price: Decimal
    public_json: dict[str, Any]
    internal_json: dict[str, Any] | None = None
    evidence_json: list[dict[str, Any]]
    risk_flags: list[str]
    draft_text: str
    pdf_path: str | None
    created_at: datetime


class QuoteSubmit(BaseModel):
    proposed_unit_price: Decimal | None = Field(default=None, gt=0)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = None
    approved_price: Decimal | None = Field(default=None, gt=0)


class DocumentUploadMeta(BaseModel):
    title: str
    document_type: str
    classification: Literal["public", "sales", "procurement", "management"]
    customer_id: str | None = None
    sku: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    top_k: int = Field(default=10, ge=1, le=50)
    sku: str | None = None
    customer_id: str | None = None
    retrieval_mode: Literal["hybrid", "dense", "bm25"] = "hybrid"


class AnswerRequest(SearchRequest):
    top_k: int = Field(default=6, ge=1, le=10)


class AnswerCitation(BaseModel):
    index: int
    chunk_id: str
    document_id: str
    title: str
    page: int | None = None
    snippet: str


class AnswerResponse(BaseModel):
    answer: str
    answer_type: Literal["grounded", "insufficient", "requires_pricing_workflow"]
    citations: list[AnswerCitation]
    evidence: list[Evidence]
    grounded: bool
    model: str
    retrieval_mode: Literal["hybrid", "dense", "bm25"]


class EvalMetrics(BaseModel):
    recall_at_5: float
    recall_at_10: float
    hit_at_5: float
    exact_sku_hit_at_5: float
    mrr: float
    ndcg_at_5: float
    citation_accuracy: float
    unauthorized_exposure_rate: float
    expired_usage_rate: float
