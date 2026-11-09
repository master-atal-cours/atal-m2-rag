"""Context : choisit et ordonne les passages montrés au LLM.

TP3 — ajouter les voisins utiles des meilleurs passages, dédoublonner, remettre
dans l'ordre des documents, respecter un budget de caractères.
"""

from __future__ import annotations

from .src.core import Hit, Index

NEIGHBOURS = 1  # voisins ajoutés de chaque côté d'un passage retrouvé…
EXPAND_TOP = 2  # … pour les EXPAND_TOP meilleurs passages seulement
MAX_CONTEXT_CHARS = 8_000  # budget de caractères pour les sources


class ContextBuilder:
    def __init__(self, index: Index):
        self.index = index

    def build(self, hits: list[Hit]) -> list[Hit]:
        """Élargit et ordonne les passages retrouvés.

        TP3 :
        1. pour les EXPAND_TOP meilleurs passages, ajouter leurs NEIGHBOURS voisins de
           chaque côté (``self.index.position[chunk.id]`` donne l'indice d'un passage dans
           ``self.index.chunks``) ; un voisin n'est utile que s'il prolonge la même section
           du même document (``chunk.doc_id`` et ``chunk.meta["section"]`` identiques) ;
        2. supprimer les doublons ;
        3. ordonner : documents par meilleur score décroissant, puis passages dans
           l'ordre du document ;
        4. s'arrêter avant de dépasser MAX_CONTEXT_CHARS.
        """
        # TP3 : à compléter
        return hits
