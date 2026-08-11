from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / ".env.example"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_secret: str = "development-only-change-me"
    database_url: str = f"sqlite:///{ROOT / 'storage' / 'cwg.db'}"
    storage_root: Path = ROOT / "storage"
    qdrant_path: Path = ROOT / "storage" / "qdrant"
    qdrant_url: str | None = None
    llm_provider: str = "mock"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    answer_provider: str = "ollama"
    answer_model: str = "deepseek-r1:1.5b"
    answer_api_base_url: str | None = None
    answer_api_key: str | None = None
    answer_timeout_seconds: int = 120
    embedding_provider: str = "hashing"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_api_key: str | None = None
    embedding_query_prefix: str = ""
    embedding_document_prefix: str = ""
    reranker_provider: str = "heuristic"
    reranker_model: str = "BAAI/bge-reranker-base"
    document_parser: str = "builtin"
    defer_indexing: bool = False
    otel_exporter_otlp_endpoint: str | None = None
    otel_project_name: str = "cwg-quote-copilot"
    frontend_origin: str = "http://localhost:3000"
    access_token_minutes: int = 480

    @property
    def documents_dir(self) -> Path:
        return self.storage_root / "documents"

    @property
    def quotes_dir(self) -> Path:
        return self.storage_root / "quotes"

    @property
    def index_dir(self) -> Path:
        return self.storage_root / "index"

    def ensure_directories(self) -> None:
        for path in (
            self.storage_root,
            self.documents_dir,
            self.quotes_dir,
            self.qdrant_path,
            self.index_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
