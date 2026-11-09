"""Rewriter : transforme le dernier message en requête de recherche autonome.

TP3 — dans une conversation, le dernier message n'est pas autonome (« Et en 2020 ? »,
« Qui l'a fondée ? »). Le LLM le réécrit à partir de l'historique.
"""

from __future__ import annotations

from .src.core import Message
from .src.llm import LLM

REWRITE_PROMPT = """Tu reformules la dernière question d'une conversation en une requête de recherche courte et autonome (une phrase de moins de 25 mots), compréhensible sans l'historique.
Remplace les pronoms et les ellipses (« elle », « et en 2020 ? ») par ce qu'ils désignent, et conserve les noms propres, numéros, dates et noms de documents.
La requête exprime ce que demande la dernière question : n'y recopie pas le contenu des réponses précédentes.
Ne réponds pas à la question. Renvoie uniquement la requête."""


class QueryRewriter:
    def __init__(self, llm: LLM):
        self.llm = llm

    def rewrite(self, conversation: list[Message]) -> str:
        """Requête de recherche pour le dernier message.

        TP3 : sans historique (un seul message), renvoyer la question telle quelle.
        Sinon, demander au LLM (``self.llm.chat``) de la réécrire avec REWRITE_PROMPT,
        en lui donnant les derniers échanges et la dernière question.
        """
        # TP3 : à compléter
        return conversation[-1]["content"]
