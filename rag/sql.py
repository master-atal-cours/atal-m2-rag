"""SQL : répond aux questions de calcul sur les tableaux du corpus (text-to-SQL).

TP4 — une agrégation (« combien de contrôles en 2025 ? ») porte sur des centaines de
lignes : aucun ensemble de passages ne les contient toutes. Le LLM écrit une requête
SQL, exécutée en lecture seule sur une base construite à partir des tableaux du corpus.
"""

from __future__ import annotations

from .src.core import Answer, Message
from .src.llm import LLM
from .src.tables import SQLError, TableStore, format_result  # noqa: F401

SQL_PROMPT = """Tu écris une requête SQL (dialecte SQLite) qui répond à la question de l'utilisateur, à partir des tables ci-dessous.
- Utilise uniquement ces tables et ces colonnes, avec leur nom exact.
- Pour comparer du texte, utilise LIKE '%...%' avec les valeurs possibles indiquées.
- Une seule requête SELECT. Réponds uniquement avec la requête, sans explication.

Tables :
{schema}"""

DATA_ANSWER_PROMPT = """Tu es un chatbot de questions-réponses sur la réglementation de l'IA en France. Réponds à la question de l'utilisateur à partir du résultat de la requête SQL ci-dessous, exécutée sur les données suivantes : {sources}.
Réponds en une ou deux phrases, en français, en citant la source des données. Si ces données ne couvrent pas la période ou le périmètre demandés, dis-le au lieu de répondre.

Requête : {sql}
Résultat :
{result}"""


class SQLTool:
    def __init__(self, llm: LLM, tables: TableStore):
        self.llm = llm
        self.tables = tables

    def answer(self, conversation: list[Message], question: str) -> Answer | None:
        """Répond à ``question`` (déjà réécrite en requête autonome) par une requête SQL.

        Renvoie None si aucune requête valide n'a pu être écrite : le pipeline se rabat
        alors sur la recherche documentaire.

        TP4 :
        1. tables pertinentes : ``self.tables.search(question, k=3)`` (des noms), et leur
           description : ``self.tables.schema(noms)`` ;
        2. le LLM écrit la requête (``self.llm.chat``, avec SQL_PROMPT) ;
        3. exécution : ``self.tables.query(sql)`` renvoie (colonnes, lignes) ou lève SQLError ;
           en cas d'erreur, ou si le résultat est vide ou nul (souvent un filtre erroné),
           redonner le problème au LLM une fois ;
        4. le LLM formule la réponse à partir du résultat (DATA_ANSWER_PROMPT,
           ``format_result(colonnes, lignes)``).
        Mettez la requête dans la trace (``"sql"``) et les documents des tables utilisées
        dans ``"documents"`` (``table.doc_id`` pour ``table`` dans ``self.tables.tables``).
        """
        # TP4 : à compléter
        return None
