"""Le pipeline : enchaîne les composants pour répondre à une conversation.

    conversation ─► router ─┬─ "documents"    ─► rewriter ─► search ─► abstention ─► context ─► prompt ─► LLM
                            ├─ "donnees"      ─► rewriter ─► sql
                            ├─ "catalogue"    ─► catalog
                            └─ "conversation" ─► prompt.build_direct ─► LLM

À l'indexation, chaque document passe par le chunker, puis chaque passage par l'encoder.

Au départ, les composants ne font rien : le routeur n'a qu'une route, la recherche
ne renvoie aucun passage et le prompt est la conversation telle quelle. Le système
se contente donc d'envoyer la question au LLM. Chaque TP remplit quelques
composants ; ce fichier n'a pas besoin d'être modifié.
"""

from __future__ import annotations

from .abstention import NOT_FOUND, Abstention
from .catalog import Catalog
from .chunker import Chunker
from .context import ContextBuilder
from .encoder import Encoder
from .prompt import PromptBuilder
from .rewriter import QueryRewriter
from .router import Router
from .search import Search
from .sql import SQLTool
from .src.core import Answer, Message, Resources, build_index


class Pipeline:
    def __init__(self, resources: Resources):
        self.llm = resources.llm
        self.top_k = resources.top_k
        self.chunker = Chunker()
        self.encoder = Encoder(resources.embeddings)
        self.index = build_index(resources.documents, self.chunker, self.encoder)
        self.search = Search(self.index, self.encoder)
        self.rewriter = QueryRewriter(self.llm)
        self.abstention = Abstention()
        self.context = ContextBuilder(self.index)
        self.prompt = PromptBuilder(self.index)
        self.router = Router(self.llm)
        self.sql = SQLTool(self.llm, resources.tables)
        self.catalog = Catalog(self.llm, self.index)

    def answer(self, conversation: list[Message]) -> Answer:
        """Répond au dernier message de la conversation."""
        route = self.router.route(conversation)
        answer = None
        if route == "donnees":
            answer = self.sql.answer(conversation, self.rewriter.rewrite(conversation))
        elif route == "catalogue":
            answer = self.catalog.answer(conversation)
        elif route == "conversation":
            answer = Answer(stream=self.llm.stream(self.prompt.build_direct(conversation)))
        if answer is None:  # route "documents", ou outil qui n'a pas pu répondre
            answer = self.answer_from_documents(conversation)
        answer.trace["route"] = route
        return answer

    def answer_from_documents(self, conversation: list[Message]) -> Answer:
        """Recherche dans les documents, puis génération à partir des passages retrouvés."""
        query = self.rewriter.rewrite(conversation)
        hits = self.search.find(query, self.top_k)
        if self.abstention.should_abstain(hits):
            return Answer.from_text(NOT_FOUND, sources=hits, trace={"query": query, "abstention": True})
        hits = self.context.build(hits)
        messages = self.prompt.build(conversation, hits)
        return Answer(stream=self.llm.stream(messages), sources=hits, trace={"query": query})
