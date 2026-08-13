from app.answering import (
    GroundedAnswerService,
    _fallback_claims,
    _validated_claims,
    get_answer_service,
    is_price_decision_question,
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


def test_amount_and_approval_wording_is_recognized_as_live_pricing() -> None:
    query = "S4-1000报800元是否可以提交审批"

    assert is_price_sensitive(query)
    assert not is_price_reference_question(query)
    response = get_answer_service().answer(
        query=query,
        evidence=[evidence("批量异常须在二十四小时内提交8D问题单。")],
        retrieval_mode="hybrid",
    )

    assert response.answer_type == "requires_pricing_workflow"
    assert response.model == "deterministic-pricing-router"
    assert response.evidence == []


def test_quote_email_is_routed_instead_of_echoed_as_a_knowledge_answer() -> None:
    query = (
        "你好，我们是远航智能汽车。请对S4-1001报价320件，纸箱包装，"
        "发往宁波，贸易条款DAP，币种CNY，希望九月底前交付。"
    )

    assert is_price_sensitive(query)
    response = get_answer_service().answer(
        query=query,
        evidence=[evidence(query)],
        retrieval_mode="hybrid",
    )

    assert response.answer_type == "requires_pricing_workflow"
    assert response.evidence == []


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


def test_manager_live_price_question_uses_pricing_without_document_evidence() -> None:
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
    assert response.evidence == []
    assert "报价计算" in response.answer


def test_hypothetical_price_decision_is_calculated_and_tracks_user_provenance() -> None:
    query = (
        "不要告诉我底价是多少，只回答：如果供应商成本是650元、硬底价是780元，"
        "那么销售报800元是否可以提交审批？同时说明这些数字分别来自哪些内部文件。"
    )

    assert is_price_decision_question(query)
    assert not is_price_reference_question(query)
    response = get_answer_service().answer(
        query=query,
        evidence=[evidence("任何低于硬底价的报价均应由系统直接阻断。")],
        retrieval_mode="hybrid",
        allow_sensitive_references=True,
    )

    assert response.answer_type == "calculated"
    assert response.model == "deterministic-price-comparison"
    assert "800 元高于或等于硬底价 780 元" in response.answer
    assert "可以提交审批" in response.answer
    assert "缺少标准最低价" in response.answer
    assert "均来自你本次问题中的假设" in response.answer
    assert "不是知识库内部文件" in response.answer
    assert response.citations == []
    assert response.evidence == []


def test_hypothetical_price_below_hard_floor_is_blocked() -> None:
    response = get_answer_service().answer(
        query="如果硬底价为780元，销售报760元是否可以提交审批？",
        evidence=[],
        retrieval_mode="hybrid",
        allow_sensitive_references=True,
    )

    assert response.answer_type == "calculated"
    assert "系统应直接阻断" in response.answer
    assert "不能提交审批" in response.answer


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
