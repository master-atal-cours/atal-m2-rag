"""Catalog : répond aux questions sur la base documentaire elle-même.

TP4 — « quels documents viennent de l'Insee ? » se répond avec la liste des documents
et leurs métadonnées, pas avec le contenu des passages.
"""

from __future__ import annotations

from .src.core import Answer, Index, Message
from .src.llm import LLM

CATALOG_PROMPT = """Tu es un chatbot de questions-réponses sur la réglementation de l'IA en France. Voici la liste complète des {count} documents de la base documentaire (chemin | format | titre | source | date). Réponds à la question de l'utilisateur à partir de cette liste uniquement.

{catalog}"""


class Catalog:
    def __init__(self, llm: LLM, index: Index):
        self.llm = llm
        self.index = index

    def answer(self, conversation: list[Message]) -> Answer | None:
        """Répond à partir de la liste des documents.

        TP4 : une ligne par document de ``self.index.documents`` (métadonnées : clés "id",
        "format", "title", "source", "date"), présentée au LLM avec CATALOG_PROMPT, suivie
        de la conversation. Mettez la liste des documents dans la trace (``"documents"``).
        """
        # TP4 : à compléter
        return None
