from app.llm import MockLLM


def test_mock_llm_extracts_ascii_tokens_next_to_chinese() -> None:
    data = MockLLM().extract_inquiry(
        "我们是远航智能汽车。请对S4-1001报价320件，纸箱包装，发往宁波，贸易条款DAP，币种CNY。"
    )
    assert data.items[0].sku == "S4-1001"
    assert data.items[0].quantity == 320
    assert data.incoterm == "DAP"
    assert data.currency == "CNY"
    assert data.missing_fields == []


def test_mock_llm_does_not_guess_missing_currency() -> None:
    data = MockLLM().extract_inquiry(
        "我们是华东汽车科技。请对S4-1000报价300件，纸箱包装，发往上海，贸易条款DDP。"
    )
    assert "currency" in data.missing_fields
