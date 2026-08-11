from __future__ import annotations

import json
import re
from dataclasses import dataclass
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
)
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class GroundedClaim:
    text: str
    evidence_ids: list[int]


def is_price_sensitive(query: str) -> bool:
    return any(term in query for term in PRICE_TERMS)


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
            "每条事实必须给出直接支持它的证据编号。证据不足时 claims 为空。\n\n"
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
                "messages": [{"role": "user", "content": self._prompt(query, evidence)}],
                "temperature": 0,
                "max_tokens": 700,
                "stream": False,
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
    ) -> AnswerResponse:
        if is_price_sensitive(query):
            return AnswerResponse(
                answer=(
                    "这类价格问题不能从知识库文档直接作答。请在报价工作台补齐客户、SKU、"
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
