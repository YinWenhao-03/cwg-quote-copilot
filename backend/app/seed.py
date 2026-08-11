from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from pathlib import Path

from sqlalchemy import select

from .auth import hash_password
from .db import SessionLocal, init_db
from .generate_demo_data import CUSTOMERS, PRODUCTS, generate_demo_files
from .ingestion import create_document_version, process_pending_jobs
from .models import (
    CustomerPolicy,
    FxRate,
    HistoricalQuote,
    InboxMessage,
    LogisticsRate,
    Product,
    SupplierCost,
    User,
)

DEMO_USERS = [
    ("sales@cwg.local", "销售演示账号", "sales", "SalesDemo!2026"),
    ("procurement@cwg.local", "采购演示账号", "procurement", "ProcDemo!2026"),
    ("manager@cwg.local", "经理演示账号", "manager", "ManagerDemo!2026"),
]


def seed_database() -> None:
    init_db()
    manifest = generate_demo_files()
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)) is not None:
            print("Database already contains seed data; processing pending jobs only.")
        else:
            users: dict[str, User] = {}
            for email, display_name, role, password in DEMO_USERS:
                user = User(
                    email=email,
                    display_name=display_name,
                    role=role,
                    password_hash=hash_password(password),
                    customer_scope=[customer["id"] for customer in CUSTOMERS]
                    if role == "sales"
                    else [],
                )
                db.add(user)
                users[role] = user
            db.flush()

            for product in PRODUCTS:
                db.add(
                    Product(
                        sku=product["sku"],
                        name=product["name"],
                        description="面向国内及出口车企的车载智能座舱显示模组。",
                        weight_kg=Decimal(str(product["weight_kg"])),
                        packaging_cost=Decimal(str(product["packaging_cost"])),
                        list_price=Decimal(str(product["list_price"])),
                        currency="CNY",
                    )
                )
                index = int(str(product["sku"]).split("-")[-1]) - 1000
                db.add_all(
                    [
                        SupplierCost(
                            sku=product["sku"],
                            supplier=f"Supplier-{index % 3 + 1}",
                            unit_cost=Decimal(str(650 + index * 23)),
                            currency="CNY",
                            valid_from=date(2026, 7, 1),
                            valid_to=date(2026, 12, 31),
                            status="approved",
                            priority=10,
                        ),
                        SupplierCost(
                            sku=product["sku"],
                            supplier=f"Supplier-{index % 3 + 1}",
                            unit_cost=Decimal(str(590 + index * 20)),
                            currency="CNY",
                            valid_from=date(2025, 1, 1),
                            valid_to=date(2025, 12, 31),
                            status="expired",
                            priority=10,
                        ),
                    ]
                )

            for customer_index, customer in enumerate(CUSTOMERS):
                db.add(
                    CustomerPolicy(
                        customer_id=customer["id"],
                        customer_name=customer["name"],
                        standard_margin=Decimal("0.25"),
                        hard_margin=Decimal("0.15"),
                        management_floor=Decimal(str(760 + customer_index * 30)),
                        owner_user_id=users["sales"].id,
                    )
                )
                db.add(
                    LogisticsRate(
                        destination=customer["destination"],
                        incoterm=customer["incoterm"],
                        base_fee=Decimal(1200),
                        fee_per_kg=Decimal(str(8 + customer_index * 2)),
                        duty_rate=Decimal("0.04") if customer_index == 2 else Decimal("0.01"),
                        currency="CNY",
                        valid_from=date(2026, 1, 1),
                        valid_to=date(2026, 12, 31),
                        status="approved",
                    )
                )

            db.add_all(
                [
                    FxRate(
                        base_currency="CNY",
                        quote_currency="CNY",
                        rate=Decimal(1),
                        as_of=date(2026, 8, 11),
                    ),
                    FxRate(
                        base_currency="CNY",
                        quote_currency="USD",
                        rate=Decimal("0.139"),
                        as_of=date(2026, 8, 11),
                    ),
                    FxRate(
                        base_currency="CNY",
                        quote_currency="EUR",
                        rate=Decimal("0.128"),
                        as_of=date(2026, 8, 11),
                    ),
                ]
            )

            for index in range(25):
                product = PRODUCTS[index % len(PRODUCTS)]
                customer = CUSTOMERS[index % len(CUSTOMERS)]
                db.add(
                    HistoricalQuote(
                        customer_id=customer["id"],
                        sku=product["sku"],
                        unit_price=Decimal(
                            str(round(float(product["list_price"]) * (0.95 + index % 5 * 0.02), 2))
                        ),
                        currency="CNY",
                        incoterm=customer["incoterm"],
                        quantity=200 + index * 20,
                        quoted_at=date(2025, 1 + index % 10, 10),
                        status="approved",
                    )
                )

            for entry in manifest:
                path = Path(str(entry["path"]))
                create_document_version(
                    db,
                    source_path=path,
                    title=str(entry["title"]),
                    document_type=str(entry["document_type"]),
                    classification=str(entry["classification"]),
                    status=str(entry["status"]),
                    valid_from=date.fromisoformat(str(entry["valid_from"])),
                    valid_to=date.fromisoformat(str(entry["valid_to"])),
                    customer_id=str(entry["customer_id"]) if entry.get("customer_id") else None,
                    sku=str(entry["sku"]) if entry.get("sku") else None,
                    metadata={"synthetic": True},
                )
                if entry.get("inbox"):
                    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
                    body = message.get_body(preferencelist=("plain",))
                    db.add(
                        InboxMessage(
                            sender=str(message.get("From", "")),
                            subject=str(message.get("Subject", "")),
                            body=body.get_content() if body else "",
                            customer_id=str(entry.get("customer_id") or ""),
                        )
                    )
            db.commit()

        while True:
            processed = process_pending_jobs(db, limit=20, raise_errors=True)
            if not processed:
                break
        print("CWG demo database and search index are ready.")
        print(
            json.dumps(
                {email: password for email, _, _, password in DEMO_USERS},
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    seed_database()
