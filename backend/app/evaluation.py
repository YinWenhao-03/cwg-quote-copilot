from __future__ import annotations

import math
from datetime import date
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Chunk, Document, DocumentVersion, EvalRun, User, utcnow
from .search import get_search_service


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    return len(set(retrieved[:k]) & relevant) / len(relevant) if relevant else 0.0


def ndcg_at_k(retrieved: list[str], relevance: dict[str, int], k: int) -> float:
    def dcg(ids: list[str]) -> float:
        return sum(
            (2 ** relevance.get(chunk_id, 0) - 1) / math.log2(rank + 1)
            for rank, chunk_id in enumerate(ids[:k], start=1)
        )

    ideal = sorted(relevance, key=relevance.get, reverse=True)
    ideal_score = dcg(ideal)
    return dcg(retrieved) / ideal_score if ideal_score else 0.0


def build_eval_cases(db: Session) -> list[dict[str, Any]]:
    rows = list(
        db.execute(
            select(Chunk, Document)
            .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                DocumentVersion.status == "approved",
                Document.document_type.in_(["product_manual", "quality_guide"]),
            )
        )
    )
    by_sku: dict[str, list[tuple[Chunk, Document]]] = {}
    for chunk, document in rows:
        if document.sku:
            by_sku.setdefault(document.sku, []).append((chunk, document))
    templates = [
        "{sku}的包装要求是什么",
        "请查找{sku}出口运输和质量检验要求",
        "{sku}每箱装多少件",
        "关于{sku}的当前产品资料",
        "{sku}高低温检验怎么做",
    ]
    cases: list[dict[str, Any]] = []
    for sku, items in by_sku.items():
        gold_ids = [chunk.id for chunk, _ in items]
        for template in templates:
            cases.append(
                {
                    "query": template.format(sku=sku),
                    "sku": sku,
                    "gold_ids": gold_ids,
                    "relevance": {
                        chunk.id: 3 if doc.document_type == "product_manual" else 2
                        for chunk, doc in items
                    },
                    "tag": "exact_sku"
                    if "当前产品" in template or "每箱" in template
                    else "semantic",
                }
            )
    return cases[:100]


def run_evaluation(db: Session, user: User) -> EvalRun:
    run = EvalRun(status="running")
    db.add(run)
    db.flush()
    cases = build_eval_cases(db)
    details: list[dict[str, Any]] = []
    recall5: list[float] = []
    recall10: list[float] = []
    hit5: list[float] = []
    mrr: list[float] = []
    ndcg5: list[float] = []
    unauthorized = 0
    expired = 0
    valid_citations = 0
    retrieved_total = 0
    allowed_classifications = {
        "sales": {"public", "sales"},
        "procurement": {"public", "procurement"},
        "manager": {"public", "sales", "procurement", "management"},
    }[user.role]
    for case in cases:
        evidence = get_search_service().search(
            db,
            query=case["query"],
            user=user,
            top_k=10,
            sku=case["sku"],
        )
        retrieved = [item.chunk_id for item in evidence]
        relevant = set(case["gold_ids"])
        r5 = recall_at_k(retrieved, relevant, 5)
        r10 = recall_at_k(retrieved, relevant, 10)
        rr = reciprocal_rank(retrieved, relevant)
        ndcg = ndcg_at_k(retrieved, case["relevance"], 5)
        recall5.append(r5)
        recall10.append(r10)
        hit5.append(float(bool(set(retrieved[:5]) & relevant)))
        mrr.append(rr)
        ndcg5.append(ndcg)
        for item in evidence:
            retrieved_total += 1
            if item.chunk_id and item.document_id and item.title and item.metadata.get("version"):
                valid_citations += 1
            if item.metadata.get("classification") not in allowed_classifications:
                unauthorized += 1
            valid_to = item.metadata.get("valid_to")
            if valid_to and date.fromisoformat(valid_to) < date.today():
                expired += 1
        details.append(
            {
                "query": case["query"],
                "tag": case["tag"],
                "recall_at_5": round(r5, 4),
                "recall_at_10": round(r10, 4),
                "hit_at_5": float(bool(set(retrieved[:5]) & relevant)),
                "mrr": round(rr, 4),
                "retrieved_ids": retrieved,
            }
        )
    run.metrics_json = {
        "case_count": len(cases),
        "recall_at_5": round(mean(recall5), 4) if recall5 else 0,
        "recall_at_10": round(mean(recall10), 4) if recall10 else 0,
        "hit_at_5": round(mean(hit5), 4) if hit5 else 0,
        "exact_sku_hit_at_5": round(
            mean(item["hit_at_5"] for item in details if item["tag"] == "exact_sku"), 4
        )
        if details
        else 0,
        "mrr": round(mean(mrr), 4) if mrr else 0,
        "ndcg_at_5": round(mean(ndcg5), 4) if ndcg5 else 0,
        "citation_accuracy": round(valid_citations / retrieved_total, 6) if retrieved_total else 0,
        "unauthorized_exposure_rate": round(unauthorized / retrieved_total, 6)
        if retrieved_total
        else 0,
        "expired_usage_rate": round(expired / retrieved_total, 6) if retrieved_total else 0,
    }
    run.cases_json = details
    run.status = "completed"
    run.completed_at = utcnow()
    db.commit()
    return run
