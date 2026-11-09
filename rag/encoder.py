"""Encoder : transforme des textes en vecteurs (embeddings).

TP1 — appeler le modèle d'embeddings et normaliser les vecteurs.

``self.client.embed(textes)`` renvoie les vecteurs bruts, un par texte (tableau n × d),
calculés par le serveur et mis en cache.
"""

from __future__ import annotations

import numpy as np

from .src.embeddings import EmbeddingClient


class Encoder:
    def __init__(self, client: EmbeddingClient):
        self.client = client

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        """Vecteurs des passages : tableau (n, d), une ligne par texte.

        TP1 : normaliser chaque ligne (norme L2 = 1, ``np.linalg.norm``) : le produit
        scalaire de deux vecteurs est alors leur similarité cosinus.
        """
        # TP1 : à compléter
        return np.zeros((len(texts), 0), dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        """Vecteur d'une requête : tableau (d,), normalisé comme les passages."""
        # TP1 : à compléter
        return np.zeros(0, dtype=np.float32)
