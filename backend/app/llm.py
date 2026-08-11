from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import get_settings
from .generate_demo_data import CUSTOMERS
from .schemas import InquiryData, InquiryItem


class LLMAdapter(ABC):
    @abstractmethod
    def extract_inquiry(self, text: str) -> InquiryData:
        raise NotImplementedError

    @abstractmethod
    def generate_quote_draft(self, context: dict[str, Any]) -> str:
        raise NotImplementedError


class MockLLM(LLMAdapter):
    def extract_inquiry(self, text: str) -> InquiryData:
        sku_match = re.search(r"(?<![A-Z0-9])(S4-\d{4})(?![A-Z0-9])", text, re.IGNORECASE)
        quantity_match = re.search(
            r"(?:报价|采购|需要)?\s*(\d{2,6})\s*(?:件|套|pcs)", text, re.IGNORECASE
        )
        incoterm_match = re.search(
            r"(?<![A-Z0-9])(DDP|DAP|FOB|CIF|EXW)(?![A-Z0-9])", text, re.IGNORECASE
        )
        currency_match = re.search(
            r"(?:币种)?\s*(CNY|RMB|USD|EUR)(?![A-Z0-9])", text, re.IGNORECASE
        )
        packaging_match = re.search(r"(纸箱|木箱|托盘|防静电[^，。]{0,8})包装", text)
        destination_match = re.search(r"(?:发往|运往|目的地为)([^，。]{2,20})", text)
        customer_name_match = re.search(r"我们是([^。；\n]+)", text)
        customer_name = customer_name_match.group(1).strip() if customer_name_match else None
        customer = next((item for item in CUSTOMERS if item["name"] == customer_name), None)
        currency = currency_match.group(1).upper() if currency_match else None
        if currency == "RMB":
            currency = "CNY"
        item = InquiryItem(
            sku=sku_match.group(1).upper() if sku_match else None,
            description="车载显示模组" if sku_match else None,
            quantity=int(quantity_match.group(1)) if quantity_match else None,
            packaging=packaging_match.group(1) if packaging_match else None,
        )
        data = InquiryData(
            customer_id=customer["id"] if customer else None,
            customer_name=customer_name,
            destination=destination_match.group(1).strip() if destination_match else None,
            incoterm=incoterm_match.group(1).upper() if incoterm_match else None,
            currency=currency,
            requested_delivery_date="2026-09-30" if "九月底" in text or "9月底" in text else None,
            items=[item],
        )
        data.missing_fields = required_missing_fields(data)
        return data

    def generate_quote_draft(self, context: dict[str, Any]) -> str:
        return (
            f"尊敬的{context['customer_name']}：\n\n"
            f"感谢贵司询价。现就{context['sku']}产品提供报价草稿："
            f"数量{context['quantity']}件，单价{context['unit_price']} {context['currency']}，"
            f"贸易条款{context['incoterm']}，交付地点为{context['destination']}。\n\n"
            f"本报价自批准之日起30日内有效，具体交期以订单确认结果为准。"
            "该内容为内部审批草稿，批准前不构成对外承诺。"
        )


class OpenAICompatibleLLM(LLMAdapter):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.llm_base_url or not settings.llm_api_key or not settings.llm_model:
            raise RuntimeError("OpenAI兼容模式缺少LLM_BASE_URL、LLM_API_KEY或LLM_MODEL")
        self.url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    def _complete(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def extract_inquiry(self, text: str) -> InquiryData:
        schema = InquiryData.model_json_schema()
        content = self._complete(
            [
                {
                    "role": "system",
                    "content": (
                        "从客户询价中提取结构化字段。只提取明确出现的信息，禁止猜测；"
                        f"严格输出符合此JSON Schema的对象：{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": text},
            ],
            json_mode=True,
        )
        data = InquiryData.model_validate_json(content)
        data.missing_fields = required_missing_fields(data)
        return data

    def generate_quote_draft(self, context: dict[str, Any]) -> str:
        safe_context = json.dumps(context, ensure_ascii=False)
        return self._complete(
            [
                {
                    "role": "system",
                    "content": "根据给定客户可见字段生成中文报价草稿，不补充未给出的承诺、成本或底价。",
                },
                {"role": "user", "content": safe_context},
            ]
        )


def required_missing_fields(data: InquiryData) -> list[str]:
    missing: list[str] = []
    for field in ("customer_id", "destination", "incoterm", "currency"):
        if not getattr(data, field):
            missing.append(field)
    if not data.items:
        return missing + ["items"]
    item = data.items[0]
    for field in ("sku", "quantity", "packaging"):
        if not getattr(item, field):
            missing.append(field)
    return missing


def get_llm() -> LLMAdapter:
    if get_settings().llm_provider == "openai_compatible":
        return OpenAICompatibleLLM()
    return MockLLM()
