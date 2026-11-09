"""Search : retrouve les passages les plus pertinents pour une requête.

TP1 — recherche dense : similarité cosinus entre la requête et chaque passage.
TP2 — recherche hybride : dense + BM25 (mots exacts), fusionnées par Reciprocal
      Rank Fusion : score(d) = Σ 1 / (RRF_K + rang(d)).

Pour tester : onglet « Index » de l'interface, champ « Recherche ».
"""

from __future__ import annotations

from .encoder import Encoder
from .src.core import Hit, Index

CANDIDATES = 50  # TP2 : nombre de résultats pris dans chaque classement avant la fusion
RRF_K = 60  # TP2 : constante de la Reciprocal Rank Fusion


class Search:
    def __init__(self, index: Index, encoder: Encoder):
        self.index = index
        self.encoder = encoder
        # TP2 : construire ici l'index BM25 sur le texte des passages :
        # BM25Okapi (rank_bm25) prend une liste de textes découpés en mots (src/text.py : tokenize)

    def find(self, query: str, k: int) -> list[Hit]:
        """Renvoie les k meilleurs passages, du plus au moins pertinent.

        TP1 : ``self.encoder.encode_query(query)`` donne le vecteur de la requête,
        ``self.index.vectors`` la matrice (n, d) des passages et ``self.index.chunks[i]``
        le passage n° i. Score = produit scalaire ; pensez à ``np.argsort``.
        Renvoyez des ``Hit(chunk, score, {"dense": score})``.

        TP2 : prendre les CANDIDATES meilleurs en dense et en BM25
        (``self.bm25.get_scores(tokenize(query))``), sommer 1 / (RRF_K + rang) sur les deux
        classements (rang à partir de 1), garder les k meilleurs. Les deux scores bruts
        vont dans ``Hit.details`` : {"dense": ..., "bm25": ...}.
        """
        # TP1 : à compléter, puis TP2 : à remplacer
        return []
