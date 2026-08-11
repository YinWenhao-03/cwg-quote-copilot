from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import SupplierCost
from app.pricing import calculate_pricing


def test_pricing_uses_current_approved_cost_and_decimal_formula() -> None:
    with SessionLocal() as db:
        result, internal = calculate_pricing(
            db,
            sku="S4-1000",
            customer_id="CUST-BMW-CN",
            quantity=300,
            destination="上海",
            incoterm="DDP",
            currency="CNY",
            as_of=date(2026, 8, 11),
        )
        cost = db.scalar(
            select(SupplierCost).where(
                SupplierCost.sku == "S4-1000", SupplierCost.status == "approved"
            )
        )
    assert Decimal(cost.unit_cost) == Decimal("650.00")
    assert result.landed_cost == Decimal("679.13")
    assert result.standard_minimum == Decimal("905.50")
    assert result.hard_floor == Decimal("798.97")
    assert internal["cost_record_id"] == cost.id


def test_hard_floor_never_exceeds_standard_minimum_in_seed_policy() -> None:
    with SessionLocal() as db:
        result, _ = calculate_pricing(
            db,
            sku="S4-1005",
            customer_id="CUST-GEELY",
            quantity=400,
            destination="宁波",
            incoterm="DAP",
            currency="CNY",
            as_of=date(2026, 8, 11),
        )
    assert result.hard_floor < result.standard_minimum <= result.suggested_price
