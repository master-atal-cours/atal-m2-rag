"""Client d'embeddings, avec cache sur disque.                           [FOURNI]

    client = EmbeddingClient()
    client.embed(["texte 1", "texte 2"])   # np.ndarray (2, d), vecteurs bruts (non normalisés)

Chaque texte n'est envoyé qu'une fois au serveur : les vecteurs sont conservés
dans index/.cache/embeddings.sqlite.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

import numpy as np

from .config import ROOT, Settings, load_settings

CACHE_DIR = ROOT / "index" / ".cache"
MAX_CHARS = 8000  # textes plus longs tronqués avant l'envoi au modèle


class EmbeddingError(RuntimeError):
    """Erreur de communication avec le serveur d'embeddings."""


class EmbeddingClient:
    def __init__(self, settings: Settings | None = None, cache_dir: Path = CACHE_DIR):
        self.settings = settings or load_settings()
        local = self.settings.embedding_provider == "local"
        self.model_name = self.settings.local_embedding_model if local else self.settings.embedding_model
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(cache_dir / "embeddings.sqlite", check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS vectors (model TEXT, key TEXT, vector BLOB, PRIMARY KEY (model, key))"
        )
        self._lock = threading.Lock()
        self._client = None
        self._local_model = None

    def embed(self, texts: list[str], progress: bool = True) -> np.ndarray:
        """Vecteurs bruts d'une liste de textes : tableau (n, d)."""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        texts = [t[:MAX_CHARS] if t.strip() else "(vide)" for t in texts]
        keys = [hashlib.sha1(t.encode("utf-8")).hexdigest() for t in texts]
        cached = self._lookup(keys)
        todo: dict[str, str] = {}
        for key, text in zip(keys, texts):
            if key not in cached:
                todo.setdefault(key, text)
        if todo:
            items = list(todo.items())
            batch = self.settings.batch_size
            batches = range(0, len(items), batch)
            if progress and len(items) > batch:
                from rich.progress import track

                batches = track(batches, description=f"Embeddings ({len(items)} textes)")
            for start in batches:
                part = items[start : start + batch]
                vectors = self._compute([t for _, t in part])
                self._store([k for k, _ in part], vectors)
                cached.update({k: v for (k, _), v in zip(part, vectors)})
        return np.stack([cached[k] for k in keys]).astype(np.float32)

    # ── Implémentation ───────────────────────────────────────────────────────

    def _compute(self, texts: list[str]) -> np.ndarray:
        if self.settings.embedding_provider == "local":
            if self._local_model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as e:
                    raise EmbeddingError(
                        "provider = \"local\" nécessite sentence-transformers : "
                        "uv sync --extra local (ou pip install -e \".[local]\")"
                    ) from e
                self._local_model = SentenceTransformer(self.model_name, device="cpu")
            return np.asarray(self._local_model.encode(texts, batch_size=self.settings.batch_size))
        import openai

        if self._client is None:
            self._client = openai.OpenAI(
                base_url=self.settings.embeddings.base_url,
                api_key=self.settings.embeddings.api_key or "EMPTY",
                timeout=self.settings.timeout,
            )
        try:
            response = self._client.embeddings.create(model=self.model_name, input=texts)
        except openai.APIConnectionError as e:
            raise EmbeddingError(
                f"Impossible de joindre l'API d'embeddings ({self.settings.embeddings.base_url}). "
                "Vérifiez config.local.toml ([api] ou [embeddings])."
            ) from e
        except openai.NotFoundError as e:
            raise EmbeddingError(f"Modèle d'embeddings « {self.model_name} » inconnu du serveur.") from e
        data = sorted(response.data, key=lambda d: d.index)
        return np.asarray([d.embedding for d in data], dtype=np.float32)

    def _lookup(self, keys: list[str]) -> dict[str, np.ndarray]:
        found: dict[str, np.ndarray] = {}
        unique = list(set(keys))
        with self._lock:
            for start in range(0, len(unique), 500):
                part = unique[start : start + 500]
                rows = self._db.execute(
                    f"SELECT key, vector FROM vectors WHERE model = ? AND key IN ({','.join('?' * len(part))})",
                    [self.model_name, *part],
                ).fetchall()
                found.update({k: np.frombuffer(v, dtype=np.float32) for k, v in rows})
        return found

    def _store(self, keys: list[str], vectors: np.ndarray) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO vectors VALUES (?, ?, ?)",
                [(self.model_name, k, np.asarray(v, dtype=np.float32).tobytes()) for k, v in zip(keys, vectors)],
            )
            self._db.commit()
