from __future__ import annotations

from datetime import date
from decimal import ROUND_UP, Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .models import CustomerPolicy, FxRate, HistoricalQuote, LogisticsRate, Product, SupplierCost
from .schemas import PricingResult

MONEY = Decimal("0.01")


class PricingError(ValueError):
    pass


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_UP)


def active_supplier_cost(db: Session, sku: str, as_of: date) -> SupplierCost:
    costs = list(
        db.scalars(
            select(SupplierCost)
            .where(
                SupplierCost.sku == sku,
                SupplierCost.status == "approved",
                SupplierCost.valid_from <= as_of,
                SupplierCost.valid_to >= as_of,
            )
            .order_by(SupplierCost.priority, desc(SupplierCost.valid_from))
        )
    )
    if not costs:
        raise PricingError("没有当前有效且已批准的供应商成本")
    if len(costs) > 1 and costs[0].priority == costs[1].priority:
        raise PricingError("存在同优先级的有效成本，需采购人员确认")
    return costs[0]


def fx_rate(db: Session, base: str, quote: str, as_of: date) -> Decimal:
    if base == quote:
        return Decimal(1)
    rate = db.scalar(
        select(FxRate.rate)
        .where(
            FxRate.base_currency == base,
            FxRate.quote_currency == quote,
            FxRate.as_of <= as_of,
        )
        .order_by(desc(FxRate.as_of))
    )
    if rate is None:
        raise PricingError(f"缺少{base}/{quote}有效汇率")
    return Decimal(rate)


def calculate_pricing(
    db: Session,
    *,
    sku: str,
    customer_id: str,
    quantity: int,
    destination: str,
    incoterm: str,
    currency: str,
    as_of: date | None = None,
) -> tuple[PricingResult, dict[str, object]]:
    as_of = as_of or date.today()
    product = db.get(Product, sku)
    if product is None or not product.active:
        raise PricingError("产品不存在或已停用")
    policy = db.get(CustomerPolicy, customer_id)
    if policy is None or not policy.active:
        raise PricingError("客户价格政策不存在或已停用")
    cost = active_supplier_cost(db, sku, as_of)
    logistics = db.scalar(
        select(LogisticsRate)
        .where(
            LogisticsRate.destination == destination,
            LogisticsRate.incoterm == incoterm,
            LogisticsRate.status == "approved",
            LogisticsRate.valid_from <= as_of,
            LogisticsRate.valid_to >= as_of,
        )
        .order_by(desc(LogisticsRate.valid_from))
    )
    if logistics is None:
        raise PricingError("没有匹配目的地和贸易条款的有效物流费率")

    supplier_cost_cny = Decimal(cost.unit_cost)
    packaging_cny = Decimal(product.packaging_cost)
    freight_cny = (Decimal(logistics.base_fee) / Decimal(quantity)) + (
        Decimal(logistics.fee_per_kg) * Decimal(product.weight_kg)
    )
    duty_cny = (supplier_cost_cny + packaging_cny + freight_cny) * Decimal(logistics.duty_rate)
    landed_cost_cny = supplier_cost_cny + packaging_cny + freight_cny + duty_cny
    standard_min_cny = landed_cost_cny / (Decimal(1) - Decimal(policy.standard_margin))
    margin_hard_floor_cny = landed_cost_cny / (Decimal(1) - Decimal(policy.hard_margin))
    hard_floor_cny = max(margin_hard_floor_cny, Decimal(policy.management_floor))
    suggested_cny = max(Decimal(product.list_price), standard_min_cny)
    rate = fx_rate(db, "CNY", currency, as_of)

    components = {
        "supplier_cost": money(supplier_cost_cny * rate),
        "packaging": money(packaging_cny * rate),
        "freight": money(freight_cny * rate),
        "duty": money(duty_cny * rate),
    }
    result = PricingResult(
        landed_cost=money(landed_cost_cny * rate),
        standard_minimum=money(standard_min_cny * rate),
        hard_floor=money(hard_floor_cny * rate),
        suggested_price=money(suggested_cny * rate),
        currency=currency,
        approval_level="standard",
        components=components,
    )
    history = db.scalar(
        select(HistoricalQuote)
        .where(
            HistoricalQuote.customer_id == customer_id,
            HistoricalQuote.sku == sku,
            HistoricalQuote.status == "approved",
        )
        .order_by(desc(HistoricalQuote.quoted_at))
    )
    internal = {
        "supplier": cost.supplier,
        "cost_record_id": cost.id,
        "landed_cost": str(result.landed_cost),
        "standard_minimum": str(result.standard_minimum),
        "hard_floor": str(result.hard_floor),
        "components": {key: str(value) for key, value in result.components.items()},
        "standard_margin": str(policy.standard_margin),
        "hard_margin": str(policy.hard_margin),
        "historical_reference": str(history.unit_price) if history else None,
        "as_of": as_of.isoformat(),
    }
    return result, internal


def classify_submitted_price(price: Decimal, pricing: PricingResult) -> str:
    if price < pricing.hard_floor:
        return "blocked"
    if price < pricing.standard_minimum:
        return "exception"
    return "standard"
