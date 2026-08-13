from __future__ import annotations

import asyncio
import shutil
import tempfile
from contextlib import asynccontextmanager, suppress
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from .answering import get_answer_service, is_price_reference_question, is_price_sensitive
from .audit import record_audit
from .auth import create_access_token, get_current_user, require_roles, verify_password
from .config import get_settings
from .db import SessionLocal, get_db, init_db
from .evaluation import run_evaluation
from .ingestion import create_document_version, process_pending_jobs
from .models import (
    Approval,
    AuditEvent,
    Chunk,
    Document,
    EvalRun,
    InboxMessage,
    Inquiry,
    QuoteDraft,
    SupplierCost,
    User,
    utcnow,
)
from .pdf_service import generate_quote_pdf
from .permissions import ensure_customer_access, quote_for_user
from .schemas import (
    AnswerRequest,
    AnswerResponse,
    ApprovalDecision,
    InquiryCreate,
    InquiryData,
    InquiryPatch,
    InquiryView,
    LoginRequest,
    QuoteSubmit,
    QuoteView,
    SearchRequest,
    TokenResponse,
    UserView,
)
from .search import get_search_service
from .telemetry import setup_telemetry
from .workflow import process_inquiry


async def ingestion_loop() -> None:
    while True:
        await asyncio.sleep(2)
        await asyncio.to_thread(process_jobs_once)


def process_jobs_once() -> int:
    with SessionLocal() as db:
        return process_pending_jobs(db, limit=5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(ingestion_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


settings = get_settings()
app = FastAPI(
    title="CWG Quote Copilot API",
    version="0.1.0",
    description="Local-first enterprise quote copilot prototype using synthetic data.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
setup_telemetry(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "answer_provider": settings.answer_provider,
        "answer_model": settings.answer_model,
    }


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email, User.active.is_(True)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    return TokenResponse(access_token=create_access_token(user), user=UserView.model_validate(user))


@app.get("/auth/me", response_model=UserView)
def me(user: User = Depends(get_current_user)) -> UserView:
    return UserView.model_validate(user)


@app.get("/dashboard")
def dashboard(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    inquiry_query = select(func.count(Inquiry.id))
    if user.role == "sales":
        inquiry_query = inquiry_query.where(Inquiry.owner_user_id == user.id)
    quote_query = select(func.count(QuoteDraft.id))
    pending_query = select(func.count(QuoteDraft.id)).where(QuoteDraft.status == "pending_approval")
    return {
        "inquiries": db.scalar(inquiry_query) or 0,
        "quotes": db.scalar(quote_query) or 0,
        "pending_approvals": db.scalar(pending_query) or 0,
        "documents": db.scalar(select(func.count(Document.id))) or 0,
        "chunks": db.scalar(select(func.count(Chunk.id))) or 0,
        "role": user.role,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
    }


@app.get("/inbox")
def list_inbox(
    user: User = Depends(require_roles("sales", "manager")), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    messages = list(db.scalars(select(InboxMessage).order_by(desc(InboxMessage.received_at))))
    return [
        {
            "id": item.id,
            "sender": item.sender,
            "subject": item.subject,
            "body": item.body,
            "received_at": item.received_at,
            "customer_id": item.customer_id,
            "processed": item.processed,
        }
        for item in messages
    ]


@app.post("/inquiries", response_model=InquiryView)
def create_inquiry(
    payload: InquiryCreate,
    user: User = Depends(require_roles("sales", "manager")),
    db: Session = Depends(get_db),
) -> InquiryView:
    inquiry = Inquiry(
        inbox_message_id=payload.inbox_message_id,
        owner_user_id=user.id,
        raw_text=payload.raw_text,
        status="received",
    )
    db.add(inquiry)
    if payload.inbox_message_id:
        message = db.get(InboxMessage, payload.inbox_message_id)
        if message:
            message.processed = True
    db.flush()
    record_audit(
        db,
        trace_id=inquiry.trace_id,
        actor=user,
        action="inquiry.created",
        resource_type="inquiry",
        resource_id=inquiry.id,
    )
    db.commit()
    return InquiryView.model_validate(inquiry)


@app.get("/inquiries", response_model=list[InquiryView])
def list_inquiries(
    user: User = Depends(require_roles("sales", "manager")), db: Session = Depends(get_db)
) -> list[InquiryView]:
    query = select(Inquiry).order_by(desc(Inquiry.created_at))
    if user.role == "sales":
        query = query.where(Inquiry.owner_user_id == user.id)
    return [InquiryView.model_validate(item) for item in db.scalars(query)]


def get_owned_inquiry(db: Session, inquiry_id: str, user: User) -> Inquiry:
    inquiry = db.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=404, detail="询价不存在")
    if user.role == "sales" and inquiry.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该询价")
    ensure_customer_access(user, inquiry.customer_id)
    return inquiry


@app.get("/inquiries/{inquiry_id}", response_model=InquiryView)
def get_inquiry(
    inquiry_id: str,
    user: User = Depends(require_roles("sales", "manager")),
    db: Session = Depends(get_db),
) -> InquiryView:
    return InquiryView.model_validate(get_owned_inquiry(db, inquiry_id, user))


@app.patch("/inquiries/{inquiry_id}", response_model=InquiryView)
def patch_inquiry(
    inquiry_id: str,
    payload: InquiryPatch,
    user: User = Depends(require_roles("sales", "manager")),
    db: Session = Depends(get_db),
) -> InquiryView:
    inquiry = get_owned_inquiry(db, inquiry_id, user)
    data = InquiryData.model_validate(inquiry.extracted_json or {})
    updates = payload.model_dump(exclude_unset=True)
    for key in ("customer_id", "destination", "incoterm", "currency", "requested_delivery_date"):
        if key in updates:
            setattr(data, key, updates[key])
    if not data.items:
        from .schemas import InquiryItem

        data.items = [InquiryItem()]
    item = data.items[0]
    for key in ("sku", "quantity", "packaging"):
        if key in updates:
            setattr(item, key, updates[key])
    from .llm import required_missing_fields

    data.missing_fields = required_missing_fields(data)
    inquiry.extracted_json = data.model_dump(mode="json")
    inquiry.missing_fields = data.missing_fields
    inquiry.customer_id = data.customer_id
    inquiry.status = "received"
    inquiry.updated_at = utcnow()
    record_audit(
        db,
        trace_id=inquiry.trace_id,
        actor=user,
        action="inquiry.corrected",
        resource_type="inquiry",
        resource_id=inquiry.id,
        detail={"fields": sorted(updates)},
    )
    db.commit()
    return InquiryView.model_validate(inquiry)


@app.post("/inquiries/{inquiry_id}/process")
def run_inquiry(
    inquiry_id: str,
    user: User = Depends(require_roles("sales", "manager")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    get_owned_inquiry(db, inquiry_id, user)
    return process_inquiry(inquiry_id, user.id)


@app.get("/quotes", response_model=list[QuoteView])
def list_quotes(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[QuoteView]:
    query = (
        select(QuoteDraft)
        .join(Inquiry, QuoteDraft.inquiry_id == Inquiry.id)
        .order_by(desc(QuoteDraft.created_at))
    )
    if user.role == "sales":
        query = query.where(Inquiry.owner_user_id == user.id)
    return [quote_for_user(item, user) for item in db.scalars(query)]


def get_quote_with_access(db: Session, quote_id: str, user: User) -> QuoteDraft:
    quote = db.get(QuoteDraft, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="报价不存在")
    inquiry = db.get(Inquiry, quote.inquiry_id)
    if inquiry and user.role == "sales" and inquiry.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该报价")
    if inquiry:
        ensure_customer_access(user, inquiry.customer_id)
    return quote


@app.get("/quotes/{quote_id}", response_model=QuoteView)
def get_quote(
    quote_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> QuoteView:
    return quote_for_user(get_quote_with_access(db, quote_id, user), user)


@app.post("/quotes/{quote_id}/submit", response_model=QuoteView)
def submit_quote(
    quote_id: str,
    payload: QuoteSubmit,
    user: User = Depends(require_roles("sales", "manager")),
    db: Session = Depends(get_db),
) -> QuoteView:
    quote = get_quote_with_access(db, quote_id, user)
    if quote.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="当前状态不能重复提交")
    proposed = payload.proposed_unit_price or Decimal(quote.proposed_unit_price)
    hard_floor = Decimal(str(quote.internal_json["hard_floor"]))
    standard_minimum = Decimal(str(quote.internal_json["standard_minimum"]))
    if proposed < hard_floor:
        raise HTTPException(status_code=422, detail="报价低于硬底价，系统已阻断")
    quote.proposed_unit_price = proposed
    quote.public_json = {**quote.public_json, "unit_price": str(proposed)}
    quote.status = "pending_approval"
    quote.risk_flags = (
        ["低于标准最低价，需要经理填写例外理由"] if proposed < standard_minimum else []
    )
    quote.updated_at = utcnow()
    inquiry = db.get(Inquiry, quote.inquiry_id)
    if inquiry:
        inquiry.status = "pending_approval"
        trace_id = inquiry.trace_id
    else:
        trace_id = quote.id
    record_audit(
        db,
        trace_id=trace_id,
        actor=user,
        action="quote.submitted",
        resource_type="quote",
        resource_id=quote.id,
        detail={"price": str(proposed), "exception": bool(quote.risk_flags)},
    )
    db.commit()
    return quote_for_user(quote, user)


@app.post("/quotes/{quote_id}/approve", response_model=QuoteView)
def approve_quote(
    quote_id: str,
    payload: ApprovalDecision,
    user: User = Depends(require_roles("manager")),
    db: Session = Depends(get_db),
) -> QuoteView:
    quote = get_quote_with_access(db, quote_id, user)
    if quote.status != "pending_approval":
        raise HTTPException(status_code=409, detail="报价不在待审批状态")
    proposed = payload.approved_price or Decimal(quote.proposed_unit_price)
    hard_floor = Decimal(str(quote.internal_json["hard_floor"]))
    standard_minimum = Decimal(str(quote.internal_json["standard_minimum"]))
    if payload.decision == "approved" and proposed < hard_floor:
        raise HTTPException(status_code=422, detail="即使经理也不能批准低于硬底价的报价")
    if payload.decision == "approved" and proposed < standard_minimum and not payload.reason:
        raise HTTPException(status_code=422, detail="例外报价必须填写审批理由")
    if proposed != Decimal(quote.proposed_unit_price):
        quote.version += 1
        quote.proposed_unit_price = proposed
        quote.public_json = {**quote.public_json, "unit_price": str(proposed)}
    quote.status = payload.decision
    quote.updated_at = utcnow()
    inquiry = db.get(Inquiry, quote.inquiry_id)
    if inquiry:
        inquiry.status = payload.decision
    approval = Approval(
        quote_id=quote.id,
        approver_user_id=user.id,
        decision=payload.decision,
        reason=payload.reason,
        approved_price=proposed if payload.decision == "approved" else None,
    )
    db.add(approval)
    if payload.decision == "approved":
        path = generate_quote_pdf(quote)
        quote.pdf_path = str(path)
    trace_id = inquiry.trace_id if inquiry else quote.id
    record_audit(
        db,
        trace_id=trace_id,
        actor=user,
        action=f"quote.{payload.decision}",
        resource_type="quote",
        resource_id=quote.id,
        detail={"price": str(proposed), "reason": payload.reason},
    )
    db.commit()
    return quote_for_user(quote, user)


@app.get("/quotes/{quote_id}/pdf")
def download_quote_pdf(
    quote_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> FileResponse:
    quote = get_quote_with_access(db, quote_id, user)
    if quote.status != "approved" or not quote.pdf_path:
        raise HTTPException(status_code=409, detail="仅已审批报价可以下载最终PDF")
    return FileResponse(
        quote.pdf_path,
        media_type="application/pdf",
        filename=f"quote-{quote.id}-v{quote.version}.pdf",
    )


@app.get("/documents")
def list_documents(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    allowed = {
        "sales": ["public", "sales"],
        "procurement": ["public", "procurement"],
        "manager": ["public", "sales", "procurement", "management"],
    }[user.role]
    documents = list(
        db.scalars(
            select(Document)
            .options(joinedload(Document.versions))
            .where(Document.classification.in_(allowed))
            .order_by(desc(Document.created_at))
        ).unique()
    )
    return [
        {
            "id": document.id,
            "title": document.title,
            "document_type": document.document_type,
            "classification": document.classification,
            "sku": document.sku,
            "customer_id": document.customer_id,
            "versions": [
                {
                    "id": version.id,
                    "version": version.version_number,
                    "status": version.status,
                    "valid_from": version.valid_from,
                    "valid_to": version.valid_to,
                }
                for version in sorted(
                    document.versions, key=lambda item: item.version_number, reverse=True
                )
            ],
        }
        for document in documents
    ]


@app.post("/documents")
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    classification: str = Form(...),
    sku: str | None = Form(default=None),
    customer_id: str | None = Form(default=None),
    valid_from: date = Form(...),
    valid_to: date = Form(...),
    user: User = Depends(require_roles("procurement", "manager")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if user.role == "procurement" and classification not in {"public", "procurement"}:
        raise HTTPException(status_code=403, detail="采购账号不能创建该密级文档")
    if classification not in {"public", "sales", "procurement", "management"}:
        raise HTTPException(status_code=422, detail="无效密级")
    suffix = Path(file.filename or "upload.bin").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        shutil.copyfileobj(file.file, handle)
        temporary_path = Path(handle.name)
    try:
        version, created = create_document_version(
            db,
            source_path=temporary_path,
            title=title,
            document_type=document_type,
            classification=classification,
            valid_from=valid_from,
            valid_to=valid_to,
            customer_id=customer_id,
            sku=sku,
            metadata={"uploaded_by": user.id},
        )
        db.commit()
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "version_id": version.id,
        "created": created,
        "status": "pending" if created else version.status,
    }


@app.post("/search")
def search_knowledge(
    payload: SearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    ensure_customer_access(user, payload.customer_id)
    evidence = get_search_service().search(
        db,
        query=payload.query,
        user=user,
        top_k=payload.top_k,
        sku=payload.sku,
        customer_id=payload.customer_id,
        retrieval_mode=payload.retrieval_mode,
    )
    trace_id = str(__import__("uuid").uuid4())
    record_audit(
        db,
        trace_id=trace_id,
        actor=user,
        action="knowledge.searched",
        resource_type="search",
        detail={
            "query": payload.query,
            "retrieval_mode": payload.retrieval_mode,
            "embedding_model": settings.embedding_model,
            "results": [item.chunk_id for item in evidence],
        },
    )
    db.commit()
    return [item.model_dump(mode="json") for item in evidence]


@app.post("/answer", response_model=AnswerResponse)
def answer_knowledge(
    payload: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnswerResponse:
    ensure_customer_access(user, payload.customer_id)
    can_review_sensitive_references = user.role == "manager"
    evidence = []
    if not is_price_sensitive(payload.query) or (
        can_review_sensitive_references and is_price_reference_question(payload.query)
    ):
        evidence = get_search_service().search(
            db,
            query=payload.query,
            user=user,
            top_k=payload.top_k,
            sku=payload.sku,
            customer_id=payload.customer_id,
            retrieval_mode=payload.retrieval_mode,
        )
    response = get_answer_service().answer(
        query=payload.query,
        evidence=evidence,
        retrieval_mode=payload.retrieval_mode,
        allow_sensitive_references=can_review_sensitive_references,
    )
    trace_id = str(__import__("uuid").uuid4())
    record_audit(
        db,
        trace_id=trace_id,
        actor=user,
        action="knowledge.answered",
        resource_type="answer",
        detail={
            "query": payload.query,
            "retrieval_mode": payload.retrieval_mode,
            "answer_type": response.answer_type,
            "answer_model": response.model,
            "sensitive_reference_access": can_review_sensitive_references,
            "citations": [citation.chunk_id for citation in response.citations],
            "results": [item.chunk_id for item in evidence],
        },
    )
    db.commit()
    return response


@app.post("/eval-runs")
def create_eval_run(
    user: User = Depends(require_roles("manager")), db: Session = Depends(get_db)
) -> dict[str, Any]:
    evaluation_user = db.scalar(select(User).where(User.role == "sales", User.active.is_(True)))
    if evaluation_user is None:
        raise HTTPException(status_code=409, detail="缺少销售评测账号")
    run = run_evaluation(db, evaluation_user)
    record_audit(
        db,
        trace_id=run.id,
        actor=user,
        action="evaluation.completed",
        resource_type="eval_run",
        resource_id=run.id,
        detail={"evaluated_as": evaluation_user.role, "metrics": run.metrics_json},
    )
    db.commit()
    return {
        "id": run.id,
        "status": run.status,
        "metrics": run.metrics_json,
        "cases": run.cases_json,
    }


@app.get("/eval-runs")
def list_eval_runs(
    _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    runs = list(db.scalars(select(EvalRun).order_by(desc(EvalRun.created_at)).limit(20)))
    return [
        {
            "id": run.id,
            "status": run.status,
            "metrics": run.metrics_json,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        }
        for run in runs
    ]


@app.get("/audit-events")
def list_audit_events(
    _: User = Depends(require_roles("manager")), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    events = list(db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(200)))
    return [
        {
            "id": event.id,
            "trace_id": event.trace_id,
            "actor_user_id": event.actor_user_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "detail": event.detail_json,
            "created_at": event.created_at,
        }
        for event in events
    ]


@app.get("/supplier-costs")
def list_supplier_costs(
    _: User = Depends(require_roles("procurement", "manager")), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    costs = list(
        db.scalars(select(SupplierCost).order_by(SupplierCost.sku, desc(SupplierCost.valid_from)))
    )
    return [
        {
            "id": cost.id,
            "sku": cost.sku,
            "supplier": cost.supplier,
            "unit_cost": cost.unit_cost,
            "currency": cost.currency,
            "valid_from": cost.valid_from,
            "valid_to": cost.valid_to,
            "status": cost.status,
        }
        for cost in costs
    ]
