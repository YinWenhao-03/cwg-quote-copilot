from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from .models import QuoteDraft, User
from .schemas import QuoteView


def ensure_customer_access(user: User, customer_id: str | None) -> None:
    if user.role == "sales" and customer_id and customer_id not in user.customer_scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该客户")


def quote_for_user(quote: QuoteDraft, user: User) -> QuoteView:
    internal: dict[str, Any] | None = None
    if user.role == "manager":
        internal = quote.internal_json
    elif user.role == "procurement":
        source = quote.internal_json
        internal = {
            "supplier": source.get("supplier"),
            "cost_record_id": source.get("cost_record_id"),
            "landed_cost": source.get("landed_cost"),
            "components": source.get("components"),
            "as_of": source.get("as_of"),
        }
    return QuoteView(
        id=quote.id,
        inquiry_id=quote.inquiry_id,
        version=quote.version,
        status=quote.status,
        currency=quote.currency,
        quantity=quote.quantity,
        proposed_unit_price=quote.proposed_unit_price,
        public_json=quote.public_json,
        internal_json=internal,
        evidence_json=quote.evidence_json,
        risk_flags=quote.risk_flags,
        draft_text=quote.draft_text,
        pdf_path=quote.pdf_path,
        created_at=quote.created_at,
    )
