"""Chunker : découpe un document en passages.

TP1 — découpage fixe : des morceaux de CHUNK_SIZE caractères du texte brut.
TP2 — découpage structurel : on suit les titres, paragraphes et tableaux du document.

Pour voir le résultat : onglet « Index » de l'interface, choisir un document.
"""

from __future__ import annotations

from .src.core import Chunk
from .src.documents import Document

CHUNK_SIZE = 1000  # TP1 : taille d'un morceau, en caractères
CHUNK_OVERLAP = 0  # TP1 : recouvrement entre deux morceaux consécutifs
MAX_CHARS = 1200  # TP2 : taille maximale du corps d'un passage


def split_fixed(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Découpe un texte en morceaux de ``size`` caractères.

    Deux morceaux consécutifs se recouvrent de ``overlap`` caractères. Les
    morceaux vides (uniquement des espaces) sont ignorés.

    >>> split_fixed("abcdefghij", size=4, overlap=1)
    ['abcd', 'defg', 'ghij']
    """
    # TP1 : à compléter
    return []


def serialize_row(header: list[str], row: list[str]) -> str:
    """Une ligne de tableau sous forme « colonne: valeur | colonne: valeur »."""
    return " | ".join(f"{h}: {v}" if h else v for h, v in zip(header, row) if v)


class Chunker:
    def chunk(self, doc: Document) -> list[Chunk]:
        """Renvoie les passages d'un document : ``Chunk(text=..., doc_id=doc.id, meta={...})``.

        TP1 : découper le texte brut (``doc.raw_text``) avec split_fixed().

        TP2 : suivre les blocs du document (``doc.blocks``). Chaque bloc a un ``kind`` :
        "heading" (avec un ``level``), "text" ou "table" (avec ``rows`` : rows[0] est
        l'en-tête). Algorithme suggéré :

        - garder la pile des titres en cours : à chaque titre de niveau L, retirer
          de la pile les titres de niveau >= L, puis empiler le nouveau ;
        - accumuler les paragraphes tant que le passage reste sous MAX_CHARS ;
          à chaque nouveau titre, émettre le passage en cours ;
        - pour un tableau, émettre des passages de lignes complètes (serialize_row),
          toujours sous MAX_CHARS ;
        - un paragraphe plus long que MAX_CHARS est découpé avec split_fixed() ;
        - préfixer chaque passage par son chemin : titre du document > titres de la pile ;
        - renseigner ``meta`` : {"title": doc.title, "section": ..., "page": ...}.
        """
        # TP1 : à compléter, puis TP2 : à remplacer
        return []
