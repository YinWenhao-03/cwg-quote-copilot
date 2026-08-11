from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from .audit import record_audit
from .db import SessionLocal
from .llm import get_llm, required_missing_fields
from .models import CustomerPolicy, Inquiry, Product, QuoteDraft, User, utcnow
from .pricing import PricingError, calculate_pricing
from .schemas import InquiryData
from .search import get_search_service


class QuoteState(TypedDict, total=False):
    inquiry_id: str
    actor_id: str
    status: str
    extracted: dict[str, Any]
    quote_id: str
    error: str


def extract_node(state: QuoteState) -> QuoteState:
    with SessionLocal() as db:
        inquiry = db.get(Inquiry, state["inquiry_id"])
        if inquiry is None:
            return {**state, "status": "blocked", "error": "询价不存在"}
        inquiry.status = "extracting"
        extracted = get_llm().extract_inquiry(inquiry.raw_text)
        current = (
            InquiryData.model_validate(inquiry.extracted_json) if inquiry.extracted_json else None
        )
        if current:
            merged = extracted.model_dump()
            existing = current.model_dump()
            for key in (
                "customer_id",
                "customer_name",
                "destination",
                "incoterm",
                "currency",
                "requested_delivery_date",
            ):
                if existing.get(key):
                    merged[key] = existing[key]
            if current.items:
                merged["items"] = [current.items[0].model_dump()]
            extracted = InquiryData.model_validate(merged)
        extracted.missing_fields = required_missing_fields(extracted)
        inquiry.extracted_json = extracted.model_dump(mode="json")
        inquiry.missing_fields = extracted.missing_fields
        inquiry.customer_id = extracted.customer_id
        inquiry.updated_at = utcnow()
        record_audit(
            db,
            trace_id=inquiry.trace_id,
            actor=db.get(User, state["actor_id"]),
            action="inquiry.extracted",
            resource_type="inquiry",
            resource_id=inquiry.id,
            detail={"missing_fields": extracted.missing_fields},
        )
        db.commit()
        return {**state, "extracted": extracted.model_dump(mode="json")}


def validate_node(state: QuoteState) -> QuoteState:
    data = InquiryData.model_validate(state["extracted"])
    with SessionLocal() as db:
        inquiry = db.get(Inquiry, state["inquiry_id"])
        if inquiry is None:
            return {**state, "status": "blocked", "error": "询价不存在"}
        if data.missing_fields:
            inquiry.status = "needs_clarification"
            db.commit()
            return {**state, "status": "needs_clarification"}
        product = db.get(Product, data.items[0].sku)
        if product is None or not product.active:
            inquiry.status = "needs_product_resolution"
            db.commit()
            return {**state, "status": "needs_product_resolution"}
        return {**state, "status": "ready"}


def route_after_validate(state: QuoteState) -> str:
    return "enrich" if state.get("status") == "ready" else "end"


def enrich_node(state: QuoteState) -> QuoteState:
    data = InquiryData.model_validate(state["extracted"])
    item = data.items[0]
    with SessionLocal() as db:
        inquiry = db.get(Inquiry, state["inquiry_id"])
        actor = db.get(User, state["actor_id"])
        if inquiry is None or actor is None:
            return {**state, "status": "blocked", "error": "询价或用户不存在"}
        inquiry.status = "pricing"
        try:
            pricing, internal = calculate_pricing(
                db,
                sku=str(item.sku),
                customer_id=str(data.customer_id),
                quantity=int(item.quantity or 0),
                destination=str(data.destination),
                incoterm=str(data.incoterm),
                currency=str(data.currency),
            )
        except PricingError as exc:
            inquiry.status = "blocked"
            record_audit(
                db,
                trace_id=inquiry.trace_id,
                actor=actor,
                action="pricing.blocked",
                resource_type="inquiry",
                resource_id=inquiry.id,
                detail={"reason": str(exc)},
            )
            db.commit()
            return {**state, "status": "blocked", "error": str(exc)}

        evidence = get_search_service().search(
            db,
            query=f"{item.sku} {data.destination} 包装要求 合同 报价",
            user=actor,
            top_k=5,
            sku=item.sku,
            customer_id=data.customer_id,
        )
        record_audit(
            db,
            trace_id=inquiry.trace_id,
            actor=actor,
            action="retrieval.completed",
            resource_type="inquiry",
            resource_id=inquiry.id,
            detail={"chunk_ids": [item.chunk_id for item in evidence], "sku": item.sku},
        )
        record_audit(
            db,
            trace_id=inquiry.trace_id,
            actor=actor,
            action="pricing.calculated",
            resource_type="inquiry",
            resource_id=inquiry.id,
            detail={
                "cost_record_id": internal["cost_record_id"],
                "as_of": internal["as_of"],
                "currency": data.currency,
            },
        )
        policy = db.get(CustomerPolicy, data.customer_id)
        public_context = {
            "customer_id": data.customer_id,
            "customer_name": policy.customer_name if policy else data.customer_name,
            "sku": item.sku,
            "quantity": item.quantity,
            "packaging": item.packaging,
            "destination": data.destination,
            "incoterm": data.incoterm,
            "currency": data.currency,
            "unit_price": str(pricing.suggested_price),
            "standard_minimum": str(pricing.standard_minimum),
            "requested_delivery_date": data.requested_delivery_date,
        }
        quote = db.scalar(select(QuoteDraft).where(QuoteDraft.inquiry_id == inquiry.id))
        if quote is None:
            quote = QuoteDraft(
                inquiry_id=inquiry.id,
                currency=str(data.currency),
                quantity=int(item.quantity or 0),
                proposed_unit_price=pricing.suggested_price,
                public_json=public_context,
                internal_json=internal,
                evidence_json=[item.model_dump(mode="json") for item in evidence],
                risk_flags=[],
                draft_text="",
            )
            db.add(quote)
        else:
            quote.version += 1
            quote.currency = str(data.currency)
            quote.quantity = int(item.quantity or 0)
            quote.proposed_unit_price = pricing.suggested_price
            quote.public_json = public_context
            quote.internal_json = internal
            quote.evidence_json = [item.model_dump(mode="json") for item in evidence]
            quote.status = "draft"
            quote.pdf_path = None
            quote.updated_at = utcnow()
        db.flush()
        quote.draft_text = get_llm().generate_quote_draft(public_context)
        inquiry.status = "pricing"
        record_audit(
            db,
            trace_id=inquiry.trace_id,
            actor=actor,
            action="quote.draft_generated",
            resource_type="quote",
            resource_id=quote.id,
            detail={"evidence_count": len(evidence), "version": quote.version},
        )
        db.commit()
        return {**state, "quote_id": quote.id, "status": "draft"}


builder = StateGraph(QuoteState)
builder.add_node("extract", extract_node)
builder.add_node("validate", validate_node)
builder.add_node("enrich", enrich_node)
builder.add_edge(START, "extract")
builder.add_edge("extract", "validate")
builder.add_conditional_edges("validate", route_after_validate, {"enrich": "enrich", "end": END})
builder.add_edge("enrich", END)
quote_graph = builder.compile()


def process_inquiry(inquiry_id: str, actor_id: str) -> QuoteState:
    return quote_graph.invoke({"inquiry_id": inquiry_id, "actor_id": actor_id})
