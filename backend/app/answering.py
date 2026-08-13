from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any

import httpx
import jieba

from .config import get_settings
from .schemas import AnswerCitation, AnswerResponse, Evidence

PRICE_TERMS = (
    "最低价",
    "底价",
    "成本",
    "报价",
    "价格",
    "多少钱",
    "毛利",
    "利润",
    "单价",
    "售价",
)
PRICE_REFERENCE_TERMS = (
    "政策",
    "规则",
    "制度",
    "流程",
    "资料",
    "文件",
    "依据",
    "历史",
    "定义",
    "含义",
    "说明",
    "要求",
)
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
MONEY_AMOUNT_PATTERN = re.compile(
    r"(?:报|卖|单价|售价|金额)?\s*"
    r"(?:人民币|CNY|RMB|USD|EUR|¥|￥|\$|€)?\s*"
    r"\d+(?:\.\d+)?\s*"
    r"(?:元|块|人民币|CNY|RMB|USD|EUR|¥|￥|\$|€)",
    re.IGNORECASE,
)
QUOTE_ACTION_PATTERN = re.compile(r"(?:提交|发起|通过|进入).{0,6}(?:审批|报价)|(?:能否|是否|可否).{0,8}(?:报|卖|审批)")
QUOTE_INQUIRY_PATTERN = re.compile(
    r"(?:请|希望|需要).{0,20}(?:报价|报个价)|"
    r"S\d+-\d+.{0,20}\d+\s*(?:件|套|个).{0,30}(?:DAP|DDP|FOB|CIF)",
    re.IGNORECASE,
)
SUPPLIER_COST_PATTERN = re.compile(
    r"供应商成本(?:是|为|[:：=])?\s*(?:人民币|CNY|RMB|¥|￥)?\s*"
    r"(\d+(?:\.\d+)?)\s*(?:元|块|人民币|CNY|RMB|¥|￥)",
    re.IGNORECASE,
)
HARD_FLOOR_PATTERN = re.compile(
    r"硬底价(?:是|为|[:：=])?\s*(?:人民币|CNY|RMB|¥|￥)?\s*"
    r"(\d+(?:\.\d+)?)\s*(?:元|块|人民币|CNY|RMB|¥|￥)",
    re.IGNORECASE,
)
STANDARD_MINIMUM_PATTERN = re.compile(
    r"标准最低价(?:是|为|[:：=])?\s*(?:人民币|CNY|RMB|¥|￥)?\s*"
    r"(\d+(?:\.\d+)?)\s*(?:元|块|人民币|CNY|RMB|¥|￥)",
    re.IGNORECASE,
)
OFFERED_PRICE_PATTERN = re.compile(
    r"(?:销售)?(?:报|报价(?:是|为)?|提交价(?:是|为)?|售价(?:是|为)?)\s*"
    r"(?:人民币|CNY|RMB|¥|￥)?\s*(\d+(?:\.\d+)?)\s*"
    r"(?:元|块|人民币|CNY|RMB|¥|￥)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class GroundedClaim:
    text: str
    evidence_ids: list[int]


@dataclass(slots=True)
class PriceDecisionInput:
    offered_price: Decimal
    hard_floor: Decimal
    supplier_cost: Decimal | None = None
    standard_minimum: Decimal | None = None


def is_price_sensitive(query: str) -> bool:
    if any(term in query for term in PRICE_TERMS):
        return True
    if QUOTE_INQUIRY_PATTERN.search(query):
        return True
    return bool(MONEY_AMOUNT_PATTERN.search(query) and QUOTE_ACTION_PATTERN.search(query))


def parse_price_decision(query: str) -> PriceDecisionInput | None:
    offered = OFFERED_PRICE_PATTERN.search(query)
    hard_floor = HARD_FLOOR_PATTERN.search(query)
    if not offered or not hard_floor or not QUOTE_ACTION_PATTERN.search(query):
        return None
    supplier_cost = SUPPLIER_COST_PATTERN.search(query)
    standard_minimum = STANDARD_MINIMUM_PATTERN.search(query)
    return PriceDecisionInput(
        offered_price=Decimal(offered.group(1)),
        hard_floor=Decimal(hard_floor.group(1)),
        supplier_cost=Decimal(supplier_cost.group(1)) if supplier_cost else None,
        standard_minimum=(
            Decimal(standard_minimum.group(1)) if standard_minimum else None
        ),
    )


def is_price_decision_question(query: str) -> bool:
    return parse_price_decision(query) is not None


def is_price_reference_question(query: str) -> bool:
    """Return true for price-policy/document questions, not a live price request."""
    return (
        is_price_sensitive(query)
        and not is_price_decision_question(query)
        and any(term in query for term in PRICE_REFERENCE_TERMS)
    )


def _format_amount(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _price_decision_answer(decision: PriceDecisionInput) -> str:
    offered = _format_amount(decision.offered_price)
    hard_floor = _format_amount(decision.hard_floor)
    if decision.offered_price < decision.hard_floor:
        conclusion = (
            f"按你提供的假设，销售报价 {offered} 元低于硬底价 {hard_floor} 元，"
            "系统应直接阻断，不能提交审批。"
        )
    elif (
        decision.standard_minimum is not None
        and decision.offered_price < decision.standard_minimum
    ):
        standard = _format_amount(decision.standard_minimum)
        conclusion = (
            f"按你提供的假设，销售报价 {offered} 元不低于硬底价 {hard_floor} 元，"
            f"但低于标准最低价 {standard} 元，因此可以提交审批，但属于例外报价，"
            "需要经理填写理由。"
        )
    else:
        conclusion = (
            f"按你提供的假设，销售报价 {offered} 元高于或等于硬底价 {hard_floor} 元，"
            "不会被硬底价规则直接阻断，可以提交审批。"
        )
        if decision.standard_minimum is None:
            conclusion += "但缺少标准最低价，暂时无法判断是否属于需要经理说明理由的例外报价。"

    sources = [f"硬底价 {hard_floor} 元", f"销售报价 {offered} 元"]
    if decision.supplier_cost is not None:
        sources.insert(0, f"供应商成本 {_format_amount(decision.supplier_cost)} 元")
    if decision.standard_minimum is not None:
        sources.append(f"标准最低价 {_format_amount(decision.standard_minimum)} 元")
    return (
        f"{conclusion}\n\n"
        f"数字来源：{'、'.join(sources)}均来自你本次问题中的假设，不是知识库内部文件。"
        "系统未检索或引用内部价格文件；如需判断真实报价，请进入报价工作台读取当前有效数据。"
    )


def _parse_json_payload(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    match = JSON_BLOCK_PATTERN.search(raw)
    if match:
        raw = match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token.strip().lower()
        for token in jieba.cut(text)
        if len(token.strip()) > 1 and not token.isspace()
    }


def _claim_is_supported(claim: str, cited_text: str) -> bool:
    claim_numbers = set(NUMBER_PATTERN.findall(claim))
    if any(number not in cited_text for number in claim_numbers):
        return False
    claim_tokens = _meaningful_tokens(claim)
    if not claim_tokens:
        return False
    cited_tokens = _meaningful_tokens(cited_text)
    token_overlap = len(claim_tokens & cited_tokens) / len(claim_tokens)
    claim_chars = {char for char in claim if "\u4e00" <= char <= "\u9fff"}
    cited_chars = {char for char in cited_text if "\u4e00" <= char <= "\u9fff"}
    char_overlap = len(claim_chars & cited_chars) / max(len(claim_chars), 1)
    return token_overlap >= 0.45 or char_overlap >= 0.72


def _validated_claims(payload: dict[str, Any], evidence: list[Evidence]) -> list[GroundedClaim]:
    claims: list[GroundedClaim] = []
    for raw_claim in payload.get("claims", [])[:5]:
        if not isinstance(raw_claim, dict):
            continue
        text = str(raw_claim.get("text", "")).strip().strip("-• ")
        raw_ids = raw_claim.get("evidence_ids", [])
        if not text or not isinstance(raw_ids, list):
            continue
        evidence_ids = sorted(
            {
                int(value)
                for value in raw_ids
                if isinstance(value, int) and 1 <= value <= len(evidence)
            }
        )
        if not evidence_ids:
            continue
        cited_text = "\n".join(evidence[index - 1].content for index in evidence_ids)
        if _claim_is_supported(text, cited_text):
            claims.append(GroundedClaim(text=text.rstrip("。") + "。", evidence_ids=evidence_ids))
    return claims


def _fallback_claims(query: str, evidence: list[Evidence]) -> list[GroundedClaim]:
    query_tokens = {
        token
        for token in _meaningful_tokens(query)
        if not (token.isascii() and any(char.isdigit() for char in token))
    }
    candidates: list[tuple[float, float, int, str]] = []
    for index, item in enumerate(evidence[:3], start=1):
        segments = re.split(r"(?<=[。！？；])|[\r\n]+", item.content)
        for segment in segments:
            segment = segment.strip(" -•\t")
            if len(segment) < 8:
                continue
            segment_tokens = _meaningful_tokens(segment)
            overlap = len(query_tokens & segment_tokens) / max(len(query_tokens), 1)
            candidates.append((overlap + item.score * 0.05, overlap, index, segment))
    candidates.sort(reverse=True, key=lambda value: value[0])
    claims: list[GroundedClaim] = []
    used: set[str] = set()
    for _, overlap, index, segment in candidates:
        if overlap < 0.12:
            continue
        normalized = re.sub(r"\s+", "", segment)
        if normalized in used:
            continue
        used.add(normalized)
        claims.append(GroundedClaim(text=segment, evidence_ids=[index]))
        if len(claims) == 2:
            break
    return claims


def _citation(index: int, evidence: Evidence) -> AnswerCitation:
    snippet = re.sub(r"\s+", " ", evidence.content).strip()
    return AnswerCitation(
        index=index,
        chunk_id=evidence.chunk_id,
        document_id=evidence.document_id,
        title=evidence.title,
        page=evidence.page,
        snippet=snippet[:180] + ("..." if len(snippet) > 180 else ""),
    )


class GroundedAnswerService:
    def __init__(self) -> None:
        settings = get_settings()
        self.provider = settings.answer_provider
        self.model = settings.answer_model
        self.ollama_url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        api_base_url = settings.answer_api_base_url or settings.llm_base_url
        self.api_url = f"{api_base_url.rstrip('/')}/chat/completions" if api_base_url else None
        self.api_key = settings.answer_api_key or settings.llm_api_key
        self.http = httpx.Client(timeout=settings.answer_timeout_seconds)

    @staticmethod
    def _prompt(query: str, evidence: list[Evidence]) -> str:
        context = "\n\n".join(
            f"[{index}] 文档：{item.title}\n{item.content[:1800]}"
            for index, item in enumerate(evidence, start=1)
        )
        return (
            "请回答下面的企业知识库问题。只能复述证据中明确写出的事实，"
            "不得补充常识、推测、评价或证据中没有的结论。把答案拆成独立事实，"
            "每条事实必须给出直接支持它的证据编号。答案必须直接回应用户的主要问题；"
            "如果证据只能支持相关规则却不能回答问题，claims 为空。证据不足时 claims 为空。\n\n"
            f"问题：{query}\n\n证据：\n{context}\n\n"
            '只输出 JSON：{"claims":[{"text":"一条事实","evidence_ids":[1]}]}。'
        )

    def _ollama_claims(self, query: str, evidence: list[Evidence]) -> list[GroundedClaim]:
        response = self.http.post(
            self.ollama_url,
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": self._prompt(query, evidence)}],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0, "num_predict": 700},
                "keep_alive": "30m",
            },
        )
        response.raise_for_status()
        raw = response.json().get("message", {}).get("content", "")
        return _validated_claims(_parse_json_payload(raw), evidence)

    def _api_claims(self, query: str, evidence: list[Evidence]) -> list[GroundedClaim]:
        if not self.api_url or not self.api_key:
            raise RuntimeError("API answer mode requires an API base URL and key")
        response = self.http.post(
            self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是企业知识库 JSON API，只输出合法 JSON。",
                    },
                    {"role": "user", "content": self._prompt(query, evidence)},
                ],
                "temperature": 0,
                "max_tokens": 400,
                "stream": False,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        return _validated_claims(_parse_json_payload(raw), evidence)

    def answer(
        self,
        *,
        query: str,
        evidence: list[Evidence],
        retrieval_mode: str,
        allow_sensitive_references: bool = False,
    ) -> AnswerResponse:
        price_decision = parse_price_decision(query)
        if price_decision is not None:
            return AnswerResponse(
                answer=_price_decision_answer(price_decision),
                answer_type="calculated",
                citations=[],
                evidence=[],
                grounded=True,
                model="deterministic-price-comparison",
                retrieval_mode=retrieval_mode,
            )
        sensitive = is_price_sensitive(query)
        can_answer_from_documents = allow_sensitive_references and is_price_reference_question(
            query
        )
        if sensitive and not can_answer_from_documents:
            return AnswerResponse(
                answer=(
                    "这类价格问题需要进入报价计算。请补齐客户、SKU、"
                    "数量、目的地和贸易条款，系统会使用当前有效成本、物流、汇率及权限规则"
                    "进行确定性计算；历史报价和过期价格不会作为当前价格依据。"
                ),
                answer_type="requires_pricing_workflow",
                citations=[],
                evidence=[],
                grounded=True,
                model="deterministic-pricing-router",
                retrieval_mode=retrieval_mode,
            )
        if not evidence:
            return AnswerResponse(
                answer="现有有效且有权限的资料不足以回答这个问题。",
                answer_type="insufficient",
                citations=[],
                evidence=[],
                grounded=False,
                model=self.model,
                retrieval_mode=retrieval_mode,
            )

        claims: list[GroundedClaim] = []
        used_fallback = False
        if self.provider == "ollama":
            try:
                claims = self._ollama_claims(query, evidence)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                claims = []
        elif self.provider == "openai_compatible":
            try:
                claims = self._api_claims(query, evidence)
            except (
                httpx.HTTPError,
                json.JSONDecodeError,
                KeyError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                claims = []
        if not claims:
            claims = _fallback_claims(query, evidence)
            used_fallback = True
        if not claims:
            return AnswerResponse(
                answer="检索到了相关资料，但证据不足以形成可靠答案。",
                answer_type="insufficient",
                citations=[],
                evidence=evidence,
                grounded=False,
                model=self.model,
                retrieval_mode=retrieval_mode,
            )

        lines = []
        cited_indices: set[int] = set()
        for order, claim in enumerate(claims, start=1):
            markers = "".join(f"[{index}]" for index in claim.evidence_ids)
            lines.append(f"{order}. {claim.text} {markers}")
            cited_indices.update(claim.evidence_ids)
        citations = [_citation(index, evidence[index - 1]) for index in sorted(cited_indices)]
        return AnswerResponse(
            answer="\n".join(lines),
            answer_type="grounded",
            citations=citations,
            evidence=evidence,
            grounded=True,
            model="extractive-fallback" if used_fallback else self.model,
            retrieval_mode=retrieval_mode,
        )

    def close(self) -> None:
        self.http.close()


@lru_cache
def get_answer_service() -> GroundedAnswerService:
    return GroundedAnswerService()
