"""Abstention : ne pas répondre quand rien de pertinent n'a été retrouvé.

TP3 — si le meilleur score dense est trop bas, le système répond NOT_FOUND sans
appeler le LLM.
"""

from __future__ import annotations

from .src.core import Hit

NOT_FOUND = "Je n'ai pas trouvé cette information dans les documents."

# En dessous de ce meilleur score dense, on s'abstient. Valeur calibrée pour bge-m3
# (hors sujet < 0,46 ; vraies questions > 0,60) : à recalibrer si le modèle change
# (l'onglet « Index » affiche les scores).
MIN_DENSE_SCORE = 0.50


class Abstention:
    def should_abstain(self, hits: list[Hit]) -> bool:
        """True s'il faut s'abstenir.

        TP3 : s'abstenir quand le meilleur score dense des passages
        (``hit.details["dense"]``) est inférieur à MIN_DENSE_SCORE.
        """
        # TP3 : à compléter
        return False
