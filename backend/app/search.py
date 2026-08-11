from __future__ import annotations

import atexit
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import httpx
import jieba
import numpy as np
from qdrant_client import QdrantClient, models
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .models import Chunk, Document, DocumentVersion, User
from .schemas import Evidence

SKU_PATTERN = re.compile(r"[A-Za-z]+\d*[\-_]\d+[A-Za-z0-9\-_]*|[A-Za-z]+\d+", re.IGNORECASE)
COLLECTION = "cwg_chunks"
VECTOR_SIZE = 256


def tokenize(text: str) -> list[str]:
    exact = [value.upper() for value in SKU_PATTERN.findall(text)]
    cleaned = SKU_PATTERN.sub(" ", text.lower())
    words = [word.strip() for word in jieba.cut(cleaned) if word.strip() and not word.isspace()]
    return exact + words


class HashingEmbedder:
    size = VECTOR_SIZE
    model_name = "deterministic-hashing-256"

    def embed(self, text: str, *, purpose: str = "document") -> list[float]:
        vector = np.zeros(self.size, dtype=np.float32)
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.size
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return vector.tolist()

    def embed_many(self, texts: list[str], *, purpose: str = "document") -> list[list[float]]:
        return [self.embed(text, purpose=purpose) for text in texts]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.size = int(self.model.get_sentence_embedding_dimension())

    def embed(self, text: str, *, purpose: str = "document") -> list[float]:
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_many(self, texts: list[str], *, purpose: str = "document") -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


class OllamaEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        query_prefix: str = "",
        document_prefix: str = "",
    ) -> None:
        self.url = f"{base_url.rstrip('/')}/api/embed"
        self.model_name = model_name
        self.query_prefix = query_prefix.strip()
        self.document_prefix = document_prefix.strip()
        self.http = httpx.Client(timeout=120)
        probe = self.embed("dimension probe", purpose="query")
        self.size = len(probe)
        if not self.size:
            raise RuntimeError(f"Ollama embedding model {model_name} returned an empty vector")

    def _prepare(self, text: str, purpose: str) -> str:
        prefix = self.query_prefix if purpose == "query" else self.document_prefix
        return f"{prefix} {text}".strip() if prefix else text

    def embed(self, text: str, *, purpose: str = "document") -> list[float]:
        return self.embed_many([text], purpose=purpose)[0]

    def embed_many(self, texts: list[str], *, purpose: str = "document") -> list[list[float]]:
        response = self.http.post(
            self.url,
            json={
                "model": self.model_name,
                "input": [self._prepare(text, purpose) for text in texts],
                "truncate": True,
                "keep_alive": "30m",
            },
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if len(embeddings) != len(texts):
            raise RuntimeError("Ollama embedding response count does not match the request")
        return embeddings

    def close(self) -> None:
        self.http.close()


class HuggingFaceEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        query_prefix: str = "",
        document_prefix: str = "",
    ) -> None:
        if not api_key:
            raise RuntimeError("Hugging Face embedding mode requires EMBEDDING_API_KEY")
        self.url = f"https://router.huggingface.co/hf-inference/models/{model_name}"
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120,
        )
        self.model_name = model_name
        self.query_prefix = query_prefix.strip()
        self.document_prefix = document_prefix.strip()
        probe = self.embed("dimension probe", purpose="query")
        self.size = len(probe)
        if not self.size:
            raise RuntimeError(f"Hugging Face model {model_name} returned an empty vector")

    def _prepare(self, text: str, purpose: str) -> str:
        prefix = self.query_prefix if purpose == "query" else self.document_prefix
        return f"{prefix} {text}".strip() if prefix else text

    def embed(self, text: str, *, purpose: str = "document") -> list[float]:
        return self.embed_many([text], purpose=purpose)[0]

    def embed_many(self, texts: list[str], *, purpose: str = "document") -> list[list[float]]:
        response = self.http.post(
            self.url,
            json={
                "inputs": [self._prepare(text, purpose) for text in texts],
                "options": {"wait_for_model": True},
            },
        )
        response.raise_for_status()
        values = response.json()
        if len(values) != len(texts):
            raise RuntimeError("Hugging Face embedding response count does not match the request")
        return [self._pool_and_normalize(value) for value in values]

    @staticmethod
    def _pool_and_normalize(value: list[object]) -> list[float]:
        if not value:
            raise RuntimeError("Hugging Face returned an empty embedding")
        # BGE v1.5's SentenceTransformers config uses CLS pooling. Some hosted
        # endpoints already return a pooled vector, so accept both response forms.
        vector = value[0] if isinstance(value[0], list) else value
        result = np.asarray(vector, dtype=np.float32)
        if result.ndim != 1:
            raise RuntimeError("Hugging Face returned an unsupported embedding shape")
        norm = float(np.linalg.norm(result))
        if not norm:
            raise RuntimeError("Hugging Face returned a zero embedding")
        return (result / norm).tolist()

    def close(self) -> None:
        self.http.close()


def get_embedder():
    settings = get_settings()
    if settings.embedding_provider == "huggingface":
        api_key = settings.embedding_api_key or settings.llm_api_key or ""
        if not api_key:
            return HashingEmbedder()
        return HuggingFaceEmbedder(
            api_key=api_key,
            model_name=settings.embedding_model,
            query_prefix=settings.embedding_query_prefix,
            document_prefix=settings.embedding_document_prefix,
        )
    if settings.embedding_provider == "ollama":
        return OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model_name=settings.embedding_model,
            query_prefix=settings.embedding_query_prefix,
            document_prefix=settings.embedding_document_prefix,
        )
    if settings.embedding_provider == "sentence_transformers":
        return SentenceTransformerEmbedder(settings.embedding_model)
    return HashingEmbedder()


@dataclass(slots=True)
class LexicalEntry:
    chunk_id: str
    tokens: list[str]


class LexicalIndex:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[LexicalEntry] = []
        self.df: Counter[str] = Counter()
        self.avgdl = 0.0
        self._by_id: dict[str, LexicalEntry] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.entries = [LexicalEntry(**entry) for entry in payload.get("entries", [])]
        self.df = Counter(payload.get("df", {}))
        self.avgdl = float(payload.get("avgdl", 0))
        self._by_id = {entry.chunk_id: entry for entry in self.entries}

    def rebuild(self, chunks: Iterable[Chunk]) -> None:
        self.entries = [LexicalEntry(chunk.id, tokenize(chunk.content)) for chunk in chunks]
        self.df = Counter()
        for entry in self.entries:
            self.df.update(set(entry.tokens))
        self.avgdl = (
            sum(len(entry.tokens) for entry in self.entries) / len(self.entries)
            if self.entries
            else 0.0
        )
        self._by_id = {entry.chunk_id: entry for entry in self.entries}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "entries": [asdict(entry) for entry in self.entries],
                    "df": dict(self.df),
                    "avgdl": self.avgdl,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def search(
        self, query: str, *, allowed_ids: set[str], limit: int = 30
    ) -> list[tuple[str, float]]:
        query_tokens = tokenize(query)
        if not query_tokens or not self.entries:
            return []
        total_docs = len(self.entries)
        scores: list[tuple[str, float]] = []
        for chunk_id in allowed_ids:
            entry = self._by_id.get(chunk_id)
            if entry is None:
                continue
            frequencies = Counter(entry.tokens)
            score = 0.0
            for token in query_tokens:
                tf = frequencies[token]
                if not tf:
                    continue
                df = self.df[token]
                idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
                length_norm = 1.2 * (1 - 0.75 + 0.75 * len(entry.tokens) / max(self.avgdl, 1))
                score += idf * (tf * 2.2) / (tf + length_norm)
            if score:
                scores.append((chunk_id, score))
        return sorted(scores, key=lambda item: item[1], reverse=True)[:limit]


class HybridSearchService:
    def __init__(self) -> None:
        settings = get_settings()
        self.embedder = get_embedder()
        self.client = (
            QdrantClient(url=settings.qdrant_url)
            if settings.qdrant_url
            else QdrantClient(path=str(settings.qdrant_path))
        )
        self.lexical = LexicalIndex(settings.index_dir / "bm25.json")
        self.reranker = None
        if settings.reranker_provider == "sentence_transformers":
            from sentence_transformers import CrossEncoder

            self.reranker = CrossEncoder(settings.reranker_model)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self.client.collection_exists(COLLECTION):
            info = self.client.get_collection(COLLECTION)
            vector_config = info.config.params.vectors
            current_size = getattr(vector_config, "size", None)
            if current_size == self.embedder.size:
                return
            self.client.delete_collection(COLLECTION)
        self.client.create_collection(
            COLLECTION,
            vectors_config=models.VectorParams(
                size=self.embedder.size,
                distance=models.Distance.COSINE,
            ),
        )

    def rebuild(self, db: Session) -> None:
        chunks = list(db.scalars(select(Chunk)))
        self.lexical.rebuild(chunks)

    @staticmethod
    def _payload(chunk: Chunk, version: DocumentVersion) -> dict[str, object]:
        document = version.document
        classification_roles = {
            "public": ["sales", "procurement", "manager"],
            "sales": ["sales", "manager"],
            "procurement": ["procurement", "manager"],
            "management": ["manager"],
        }
        return {
            "chunk_id": chunk.id,
            "version_id": version.id,
            "document_id": document.id,
            "title": document.title,
            "content": chunk.content,
            "page": chunk.page,
            "section": chunk.section,
            "sku": document.sku or "",
            "customer_scope": document.customer_id or "global",
            "classification": document.classification,
            "allowed_roles": classification_roles.get(document.classification, ["manager"]),
            "status": version.status,
            "valid_from": version.valid_from.toordinal() if version.valid_from else 0,
            "valid_to": version.valid_to.toordinal() if version.valid_to else 9999999,
            "embedding_model": get_settings().embedding_model,
        }

    def upsert_chunk(self, chunk: Chunk, version: DocumentVersion) -> None:
        self.client.upsert(
            COLLECTION,
            points=[
                models.PointStruct(
                    id=chunk.id,
                    vector=self.embedder.embed(chunk.content, purpose="document"),
                    payload=self._payload(chunk, version),
                )
            ],
            wait=True,
        )

    def reindex_all(self, db: Session, *, batch_size: int = 32) -> int:
        chunks = list(
            db.scalars(
                select(Chunk).options(
                    joinedload(Chunk.version).joinedload(DocumentVersion.document)
                )
            )
        )
        if self.client.collection_exists(COLLECTION):
            self.client.delete_collection(COLLECTION)
        self._ensure_collection()
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self.embedder.embed_many(
                [chunk.content for chunk in batch], purpose="document"
            )
            self.client.upsert(
                COLLECTION,
                points=[
                    models.PointStruct(
                        id=chunk.id,
                        vector=vector,
                        payload=self._payload(chunk, chunk.version),
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ],
                wait=True,
            )
        self.lexical.rebuild(chunks)
        return len(chunks)

    def search(
        self,
        db: Session,
        *,
        query: str,
        user: User,
        top_k: int = 10,
        sku: str | None = None,
        customer_id: str | None = None,
        retrieval_mode: str = "hybrid",
    ) -> list[Evidence]:
        today = date.today().toordinal()
        query_skus = list(dict.fromkeys(value.upper() for value in SKU_PATTERN.findall(query)))
        effective_sku = sku or (query_skus[0] if len(query_skus) == 1 else None)
        allowed_classifications = {
            "sales": ["public", "sales"],
            "procurement": ["public", "procurement"],
            "manager": ["public", "sales", "procurement", "management"],
        }[user.role]
        allowed_query = (
            select(Chunk.id)
            .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.classification.in_(allowed_classifications),
                DocumentVersion.status == "approved",
                or_(
                    DocumentVersion.valid_from.is_(None), DocumentVersion.valid_from <= date.today()
                ),
                or_(DocumentVersion.valid_to.is_(None), DocumentVersion.valid_to >= date.today()),
            )
        )
        if user.role == "sales":
            allowed_query = allowed_query.where(
                or_(Document.customer_id.is_(None), Document.customer_id.in_(user.customer_scope))
            )
        if effective_sku:
            allowed_query = allowed_query.where(Document.sku == effective_sku)
        allowed_ids = set(db.scalars(allowed_query))

        allowed_customers = ["global"]
        if user.role == "sales":
            allowed_customers.extend(user.customer_scope)
        must = [
            models.FieldCondition(key="allowed_roles", match=models.MatchAny(any=[user.role])),
            models.FieldCondition(key="status", match=models.MatchValue(value="approved")),
            models.FieldCondition(key="valid_from", range=models.Range(lte=today)),
            models.FieldCondition(key="valid_to", range=models.Range(gte=today)),
        ]
        if user.role == "sales":
            must.append(
                models.FieldCondition(
                    key="customer_scope", match=models.MatchAny(any=list(set(allowed_customers)))
                )
            )
        if effective_sku:
            must.append(
                models.FieldCondition(key="sku", match=models.MatchValue(value=effective_sku))
            )
        dense_query = SKU_PATTERN.sub(" ", query).strip() if effective_sku else query
        vector_hits = self.client.query_points(
            collection_name=COLLECTION,
            query=self.embedder.embed(dense_query, purpose="query"),
            query_filter=models.Filter(must=must),
            limit=max(30, top_k * 3),
            with_payload=True,
        ).points
        vector_results = [
            (str(hit.id), float(hit.score)) for hit in vector_hits if str(hit.id) in allowed_ids
        ]
        lexical_query = dense_query if effective_sku else query
        lexical_results = self.lexical.search(
            lexical_query, allowed_ids=allowed_ids, limit=max(30, top_k * 3)
        )

        rrf: defaultdict[str, float] = defaultdict(float)
        dense_ranks = {
            chunk_id: {"rank": rank, "score": score}
            for rank, (chunk_id, score) in enumerate(vector_results, start=1)
        }
        bm25_ranks = {
            chunk_id: {"rank": rank, "score": score}
            for rank, (chunk_id, score) in enumerate(lexical_results, start=1)
        }
        active_channels = {
            "hybrid": (vector_results, lexical_results),
            "dense": (vector_results,),
            "bm25": (lexical_results,),
        }.get(retrieval_mode, (vector_results, lexical_results))
        for results in active_channels:
            for rank, (chunk_id, _) in enumerate(results, start=1):
                rrf[chunk_id] += 1.0 / (60 + rank)
        query_tokens = set(tokenize(lexical_query))
        hit_by_id = {str(hit.id): hit for hit in vector_hits}
        ranked: list[tuple[str, float]] = []
        trace_by_id: dict[str, dict[str, object]] = {}
        max_rrf = max(rrf.values(), default=1.0)
        for chunk_id, score in rrf.items():
            payload = hit_by_id.get(chunk_id).payload if chunk_id in hit_by_id else {}
            lexical_entry = self.lexical._by_id.get(chunk_id)
            content_tokens = (
                set(lexical_entry.tokens)
                if lexical_entry
                else set(tokenize(str((payload or {}).get("content", ""))))
            )
            overlap = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
            final_score = 0.75 * score / max_rrf + 0.25 * overlap
            ranked.append((chunk_id, final_score))
            trace_by_id[chunk_id] = {
                "dense_rank": dense_ranks.get(chunk_id, {}).get("rank"),
                "dense_score": dense_ranks.get(chunk_id, {}).get("score"),
                "bm25_rank": bm25_ranks.get(chunk_id, {}).get("rank"),
                "bm25_score": bm25_ranks.get(chunk_id, {}).get("score"),
                "rrf_score": round(score, 8),
                "reranker": "heuristic-token-overlap",
                "mode": retrieval_mode,
                "sku_filter": effective_sku,
                "dense_query": dense_query,
                "lexical_query": lexical_query,
            }
        ranked.sort(key=lambda item: item[1], reverse=True)

        candidate_ids = [chunk_id for chunk_id, _ in ranked[: max(top_k * 3, top_k)]]
        chunks = {
            chunk.id: chunk
            for chunk in db.scalars(
                select(Chunk)
                .options(joinedload(Chunk.version).joinedload(DocumentVersion.document))
                .where(Chunk.id.in_(candidate_ids))
            )
        }
        if self.reranker and chunks:
            rerank_scores = self.reranker.predict(
                [
                    [query, chunks[chunk_id].content]
                    for chunk_id in candidate_ids
                    if chunk_id in chunks
                ]
            )
            ranked = sorted(
                zip(
                    [chunk_id for chunk_id in candidate_ids if chunk_id in chunks],
                    [float(score) for score in rerank_scores],
                    strict=True,
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            for chunk_id, score in ranked:
                trace_by_id[chunk_id]["reranker"] = get_settings().reranker_model
                trace_by_id[chunk_id]["reranker_score"] = score
        evidence: list[Evidence] = []
        for chunk_id, score in ranked[:top_k]:
            chunk = chunks.get(chunk_id)
            if chunk is None:
                continue
            document = chunk.version.document
            evidence.append(
                Evidence(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    title=document.title,
                    content=chunk.content,
                    page=chunk.page,
                    score=round(score, 6),
                    metadata={
                        "sku": document.sku,
                        "customer_id": document.customer_id,
                        "classification": document.classification,
                        "version": chunk.version.version_number,
                        "valid_to": chunk.version.valid_to.isoformat()
                        if chunk.version.valid_to
                        else None,
                        "retrieval": trace_by_id.get(chunk_id, {}),
                        "embedding_model": self.embedder.model_name,
                    },
                )
            )
        return evidence


_service: HybridSearchService | None = None


def get_search_service() -> HybridSearchService:
    global _service
    if _service is None:
        _service = HybridSearchService()
        atexit.register(_service.client.close)
        close_embedder = getattr(_service.embedder, "close", None)
        if close_embedder:
            atexit.register(close_embedder)
    return _service
