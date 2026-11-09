"""Router : choisit l'outil qui traitera le dernier message.

TP4 — toutes les questions ne se traitent pas par recherche de passages :

- "documents"    : recherche dans les documents, puis génération ;
- "donnees"      : calcul sur des tableaux (compter, additionner…) : requête SQL ;
- "catalogue"    : question sur la base elle-même : liste des documents ;
- "conversation" : salutation, traduction de la réponse précédente… : pas de recherche.

Au départ, il n'y a qu'une route : tout va à la recherche documentaire.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .src.core import Message
from .src.llm import LLM

ROUTER_PROMPT = """Tu es le routeur d'un assistant documentaire. Classe la dernière demande de l'utilisateur dans l'une de ces catégories :

- "conversation" : salutation, remerciement, question sur l'assistant lui-même, ou demande de transformer la réponse précédente (la traduire, la résumer, la reformuler) sans nouvelle information à chercher ;
- "catalogue" : question sur la base documentaire elle-même, c'est-à-dire sur les fichiers qu'elle contient (quels documents, combien, de quelles sources, dans quels formats) ;
- "donnees" : calcul sur de nombreuses lignes d'un tableau (compter, additionner, faire une moyenne, trouver un maximum ou un minimum, classer, filtrer une liste) : contrôles, sanctions, amendes, plaintes ou mises en demeure de la CNIL, modèles du catalogue compar:IA ;
- "documents" : toute autre question, dont la réponse se trouve dans le texte des documents, y compris la lecture d'une statistique publiée (un pourcentage, un taux) et ce qu'un texte prévoit (règles, obligations, montants maximaux fixés par un règlement…).

Exemples :
- « Merci, c'est très clair ! » → conversation
- « Peux-tu traduire ta réponse en anglais ? » → conversation
- « Quels documents de la base parlent de pseudonymisation ? » → catalogue
- « Combien de contrôles la CNIL a-t-elle menés à Paris en 2024 ? » → donnees
- « Combien de modèles d'OpenAI le catalogue compar:IA contient-il ? » → donnees
- « Quel modèle de compar:IA consomme le moins d'énergie ? » → donnees
- « Que prévoit l'article 5 du règlement sur l'IA ? » → documents
- « Quelle amende maximale le RGPD prévoit-il ? » → documents
- « Quelle part des entreprises du secteur de la construction utilise l'IA selon l'Insee ? » → documents
- « Et en quelle année ? » (après une question sur une entreprise) → documents

Une question de suite qui demande une information nouvelle relève de « documents » ou de « donnees », jamais de « conversation ». En cas de doute, choisis « documents »."""


class Route(BaseModel):
    """Sortie structurée du routeur. TP4 : ajouter les trois autres routes."""

    route: Literal["documents"]


class Router:
    def __init__(self, llm: LLM):
        self.llm = llm

    def route(self, conversation: list[Message]) -> str:
        """Nom de la route : "documents", "donnees", "catalogue" ou "conversation".

        TP4 : ``self.llm.json(messages, Route)`` renvoie un objet ``Route`` dont le champ
        ``route`` ne peut prendre que les valeurs prévues (sortie structurée). Donnez au
        LLM ROUTER_PROMPT, les derniers messages et la dernière demande.
        """
        # TP4 : à compléter
        return "documents"
