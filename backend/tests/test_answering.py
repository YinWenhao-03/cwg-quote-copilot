from app.answering import (
    GroundedAnswerService,
    _fallback_claims,
    _validated_claims,
    get_answer_service,
    is_price_reference_question,
    is_price_sensitive,
)
from app.schemas import Evidence


def evidence(content: str) -> Evidence:
    return Evidence(
        chunk_id="chunk-1",
        document_id="doc-1",
        title="S4-1000 包装指南",
        content=content,
        score=0.9,
        metadata={},
    )


def test_claim_validation_accepts_supported_fact_and_rejects_new_number() -> None:
    items = [evidence("每10件使用防静电内袋，放入加强纸箱，并增加防潮袋和缓冲材料。")]
    payload = {
        "claims": [
            {"text": "每10件使用防静电内袋并放入加强纸箱。", "evidence_ids": [1]},
            {"text": "每20件使用一个木箱。", "evidence_ids": [1]},
        ]
    }

    claims = _validated_claims(payload, items)

    assert [claim.text for claim in claims] == ["每10件使用防静电内袋并放入加强纸箱。"]


def test_price_questions_are_routed_away_from_document_answering() -> None:
    assert is_price_sensitive("这个客户最低可以报多少钱")
    response = get_answer_service().answer(
        query="这个客户最低可以报多少钱",
        evidence=[evidence("去年的历史报价是100元。")],
        retrieval_mode="hybrid",
    )

    assert response.answer_type == "requires_pricing_workflow"
    assert response.citations == []
    assert response.evidence == []
    assert response.model == "deterministic-pricing-router"


def test_manager_can_answer_price_policy_questions_from_management_evidence() -> None:
    query = "管理层底价政策和例外报价规则是什么"
    assert is_price_reference_question(query)
    service = GroundedAnswerService()
    service.provider = "disabled-for-test"
    response = service.answer(
        query=query,
        evidence=[
            evidence("管理层底价政策规定：例外报价必须由经理填写理由并保留审计记录。")
        ],
        retrieval_mode="hybrid",
        allow_sensitive_references=True,
    )
    service.close()

    assert response.answer_type == "grounded"
    assert response.citations
    assert response.evidence


def test_manager_live_price_question_still_uses_pricing_and_keeps_related_evidence() -> None:
    query = "这个客户当前最低可以报多少钱"
    assert not is_price_reference_question(query)
    related = [evidence("低于标准最低价的例外报价必须由经理填写理由。")]
    response = get_answer_service().answer(
        query=query,
        evidence=related,
        retrieval_mode="hybrid",
        allow_sensitive_references=True,
    )

    assert response.answer_type == "requires_pricing_workflow"
    assert response.evidence == related
    assert "实时定价" in response.answer


def test_fallback_keeps_relevant_fact_and_reports_its_real_source() -> None:
    items = [
        evidence("出口运输增加防潮袋、边角保护和跌落标签。"),
        evidence("S4-1003 产品技术资料"),
    ]

    claims = _fallback_claims("S4-1003出口运输的包装要求是什么", items)
    assert [claim.text for claim in claims] == ["出口运输增加防潮袋、边角保护和跌落标签。"]

    service = GroundedAnswerService()
    service.provider = "disabled-for-test"
    response = service.answer(
        query="S4-1003出口运输的包装要求是什么",
        evidence=items,
        retrieval_mode="hybrid",
    )
    service.close()

    assert response.answer == "1. 出口运输增加防潮袋、边角保护和跌落标签。 [1]"
    assert response.model == "extractive-fallback"
