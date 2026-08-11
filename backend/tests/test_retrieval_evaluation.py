import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.evaluation import run_evaluation
from app.models import Document, DocumentVersion, User
from app.search import HuggingFaceEmbedder, get_search_service


def test_seed_contains_expected_document_versions() -> None:
    with SessionLocal() as db:
        documents = db.scalar(select(func.count()).select_from(Document))
        versions = db.scalar(select(func.count()).select_from(DocumentVersion))
        superseded = db.scalar(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.status == "superseded")
        )
    assert documents >= 100
    assert versions >= 121
    assert superseded >= 10


def test_rag_acceptance_metrics() -> None:
    with SessionLocal() as db:
        sales = db.scalar(select(User).where(User.role == "sales"))
        run = run_evaluation(db, sales)
    assert run.metrics_json["case_count"] == 100
    assert run.metrics_json["recall_at_10"] >= 0.90
    assert run.metrics_json["exact_sku_hit_at_5"] >= 0.95
    assert run.metrics_json["citation_accuracy"] == 1
    assert run.metrics_json["unauthorized_exposure_rate"] == 0
    assert run.metrics_json["expired_usage_rate"] == 0


def test_hybrid_results_expose_dense_bm25_and_rrf_trace() -> None:
    with SessionLocal() as db:
        sales = db.scalar(select(User).where(User.role == "sales"))
        evidence = get_search_service().search(
            db,
            query="长途发货时怎样避免水汽和磕碰",
            user=sales,
            sku="S4-1000",
            top_k=5,
            retrieval_mode="hybrid",
        )
    assert evidence
    assert evidence[0].metadata["embedding_model"] == "nomic-embed-text:latest"
    trace = evidence[0].metadata["retrieval"]
    assert trace["mode"] == "hybrid"
    assert trace["dense_rank"] is not None
    assert trace["bm25_rank"] is not None
    assert trace["rrf_score"] > 0


def test_hugging_face_embedder_uses_normalized_cls_pooling() -> None:
    vector = HuggingFaceEmbedder._pool_and_normalize([[3.0, 4.0], [9.0, 9.0]])

    assert vector == pytest.approx([0.6, 0.8])
