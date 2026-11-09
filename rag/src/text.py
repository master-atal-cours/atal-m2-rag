"""Outils texte : normalisation et découpage en mots pour BM25.         [FOURNI]

    >>> tokenize("Les obligations de transparence de l'article 50")
    ['obliga', 'transp', 'articl', '50']
"""

from __future__ import annotations

import re
import unicodedata

# Mots-outils français (et quelques mots anglais fréquents) ignorés par BM25
STOPWORDS = set("""
a afin ai aie aient ainsi alors au aucun aucune aupres auquel aura aurai auraient aurais aurait
aussi autre autres aux auxquelles auxquels avaient avais avait avant avec avez aviez avions avoir
avons ayant c ca ce ceci cela celle celles celui ces cet cette ceux chaque chez ci comme comment
d dans de des desquelles desquels deux dit doit donc dont du duquel elle elles en encore entre
est et etaient etais etait etant ete etes etre eu eue eues eurent eus eut eux faire fait fois
font hors i il ils j je jusqu l la laquelle le lequel les lesquelles lesquels leur leurs lors
lorsque lui m ma mais me meme memes mes moi mon n ne ni non nos notre nous on ont or ou par parce
pas peu peut peuvent plus pour pourquoi qu quand que quel quelle quelles quels qui quoi s sa sans
se selon ses si son sont sous sur t ta te tes toi ton tous tout toute toutes tres tu un une unes
uns vers voici voila vos votre vous y
the of and or to in is are for on with by an be as at this that it from
""".split())


def normalize(text: str) -> str:
    """Minuscules, sans accents, apostrophes et espaces unifiées."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.replace("’", "'").replace(" ", " ").replace(" ", " ")


def tokenize(text: str) -> list[str]:
    """Découpe un texte en mots normalisés pour la recherche lexicale.

    - minuscules et suppression des accents ;
    - suppression des mots-outils (le, la, de, ...) ;
    - racinisation très simple : les mots de plus de 6 lettres sont tronqués
      (« réglementation », « règlement » → « reglem »), les nombres sont gardés.
    """
    tokens = []
    for token in re.findall(r"[a-z0-9]+", normalize(text)):
        if token in STOPWORDS:
            continue
        if token.isdigit():
            tokens.append(token)
        elif len(token) > 1:
            tokens.append(token[:6])
    return tokens
