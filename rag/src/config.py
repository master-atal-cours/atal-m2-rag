"""Lecture de la configuration (config.toml puis config.local.toml).     [FOURNI]"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILES = [ROOT / "config.toml", ROOT / "config.local.toml"]


@dataclass
class Endpoint:
    """Adresse d'une API compatible OpenAI."""

    host: str = "localhost"
    port: int = 11434
    path: str = "/v1"
    api_key: str = "EMPTY"
    https: bool = False

    @property
    def base_url(self) -> str:
        scheme = "https" if self.https else "http"
        path = "/" + self.path.strip("/") if self.path.strip("/") else ""
        return f"{scheme}://{self.host}:{self.port}{path}"


@dataclass
class Settings:
    api: Endpoint = field(default_factory=Endpoint)
    llm_model: str = "qwen3.5:9b"
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout: float = 180.0
    extra_body: dict[str, Any] = field(default_factory=dict)

    embeddings: Endpoint = field(default_factory=Endpoint)
    embedding_model: str = "bge-m3"
    batch_size: int = 32
    embedding_provider: str = "api"
    local_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    top_k: int = 5


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings() -> Settings:
    data: dict[str, Any] = {}
    for path in CONFIG_FILES:
        if path.exists():
            with path.open("rb") as f:
                data = _merge(data, tomllib.load(f))

    api = data.get("api", {})
    env = os.environ
    api_endpoint = Endpoint(
        host=env.get("RAG_HOST", api.get("host", "localhost")),
        port=int(env.get("RAG_PORT", api.get("port", 11434))),
        path=api.get("path", "/v1"),
        api_key=env.get("RAG_API_KEY", api.get("api_key", "EMPTY")),
        https=bool(api.get("https", False)),
    )
    llm = data.get("llm", {})
    emb = data.get("embeddings", {})
    emb_endpoint = Endpoint(
        host=emb.get("host", api_endpoint.host),
        port=int(emb.get("port", api_endpoint.port)),
        path=emb.get("path", api_endpoint.path),
        api_key=emb.get("api_key", api_endpoint.api_key),
        https=bool(emb.get("https", api_endpoint.https)),
    )
    rag = data.get("rag", {})
    return Settings(
        api=api_endpoint,
        llm_model=env.get("RAG_LLM_MODEL", llm.get("model", "qwen3.5:9b")),
        temperature=float(llm.get("temperature", 0.0)),
        max_tokens=int(llm.get("max_tokens", 1024)),
        timeout=float(llm.get("timeout", 180)),
        extra_body=dict(llm.get("extra_body", {})),
        embeddings=emb_endpoint,
        embedding_model=env.get("RAG_EMBEDDING_MODEL", emb.get("model", "bge-m3")),
        batch_size=int(emb.get("batch_size", 32)),
        embedding_provider=emb.get("provider", "api"),
        local_embedding_model=emb.get("local_model", Settings.local_embedding_model),
        top_k=int(rag.get("top_k", 5)),
    )
