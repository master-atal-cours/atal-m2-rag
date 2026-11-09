"""Types communs, construction de l'index et ressources partagées.        [FOURNI]

- ``Chunk``  : un passage du corpus ;
- ``Hit``    : un passage retrouvé, avec son score ;
- ``Answer`` : la réponse du système (texte en flux, passages utilisés, trace) ;
- ``Index``  : tous les passages, leurs vecteurs et les métadonnées des documents ;
- ``Resources`` : ce qui ne change pas quand vous modifiez votre code (LLM, client
  d'embeddings, documents lus, base SQL des tableaux).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Iterator

import numpy as np

from .config import Settings, load_settings
from .documents import Document, load_corpus
from .embeddings import EmbeddingClient
from .llm import LLM
from .tables import TableStore

if TYPE_CHECKING:
    from ..chunker import Chunker
    from ..encoder import Encoder

Message = dict[str, str]  # {"role": "system" | "user" | "assistant", "content": "..."}


@dataclass
class Chunk:
    """Un passage du corpus."""

    text: str  # texte indexé et montré au LLM
    doc_id: str  # document d'origine, ex. "cnil/guide-securite-donnees-personnelles.pdf"
    meta: dict[str, Any] = field(default_factory=dict)  # section, page, title…
    id: str = ""  # attribué à l'indexation : "<doc_id>#<position>"


@dataclass
class Hit:
    """Un passage retrouvé, avec son score."""

    chunk: Chunk
    score: float
    details: dict[str, float] = field(default_factory=dict)  # scores intermédiaires : dense, bm25…


@dataclass
class Answer:
    """Réponse du système.

    ``stream`` produit le texte au fil de la génération ; ``text`` attend la fin.
    ``sources`` : les passages fournis au LLM ; ``trace`` : ce qui aide à comprendre
    la réponse (requête réécrite, route, requête SQL…), affiché dans l'interface.
    """

    stream: Iterable[str] | None = None
    sources: list[Hit] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    _text: str | None = None

    @classmethod
    def from_text(cls, text: str, **kwargs: Any) -> "Answer":
        answer = cls(**kwargs)
        answer._text = text
        return answer

    def __iter__(self) -> Iterator[str]:
        if self._text is not None:
            yield self._text
            return
        parts = []
        for token in self.stream or []:
            parts.append(token)
            yield token
        self._text = "".join(parts)

    @property
    def text(self) -> str:
        if self._text is None:
            for _ in self:
                pass
        return self._text or ""


@dataclass
class Index:
    """Les passages du corpus et leurs vecteurs.

    - ``chunks[i]`` : le passage n° i, dans l'ordre des documents ;
    - ``vectors[i]`` : son vecteur (matrice n × d, vide tant que l'encodeur ne fait rien) ;
    - ``position[chunk.id]`` : l'indice i d'un passage (pour trouver ses voisins) ;
    - ``documents[doc_id]`` : métadonnées d'un document (title, format, date, status, source…).
    """

    chunks: list[Chunk]
    vectors: np.ndarray
    documents: dict[str, dict[str, Any]]
    position: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.position = {chunk.id: i for i, chunk in enumerate(self.chunks)}


def build_index(documents: list[Document], chunker: "Chunker", encoder: "Encoder", verbose: bool = True) -> Index:
    """Découpe chaque document avec ``chunker``, puis encode les passages avec ``encoder``.

    Les embeddings sont en cache : seuls les passages nouveaux ou modifiés sont envoyés au serveur.
    """
    start = time.time()
    chunks: list[Chunk] = []
    for doc in documents:
        for position, chunk in enumerate(chunker.chunk(doc) or []):
            chunk.doc_id = chunk.doc_id or doc.id
            chunk.meta.setdefault("position", position)
            chunk.id = f"{chunk.doc_id}#{position}"
            chunks.append(chunk)
    vectors = encoder.encode_passages([c.text for c in chunks]) if chunks else None
    if vectors is None or len(vectors) != len(chunks):
        vectors = np.zeros((len(chunks), 0), dtype=np.float32)
    infos = {
        doc.id: {
            "id": doc.id,
            "title": doc.title,
            "format": doc.format,
            "chars": len(doc.raw_text),
            "chunks": sum(1 for c in chunks if c.doc_id == doc.id),
            **doc.meta,
        }
        for doc in documents
    }
    if verbose:
        dim = vectors.shape[1] if vectors.ndim == 2 else 0
        print(f"Index : {len(chunks)} passages, vecteurs de dimension {dim} ({time.time() - start:.0f} s)")
    return Index(chunks, np.asarray(vectors, dtype=np.float32), infos)


class Resources:
    """Ce qui est chargé une seule fois, même quand on recharge le code."""

    def __init__(self, settings: Settings | None = None, verbose: bool = True):
        self.settings = settings or load_settings()
        self.llm = LLM(self.settings)
        self.embeddings = EmbeddingClient(self.settings)
        if verbose:
            print("Lecture des documents…")
        self.documents = load_corpus(verbose=verbose)
        self.tables = TableStore(self.documents)
        self.top_k = self.settings.top_k
