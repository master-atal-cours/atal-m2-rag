# M2 ATAL - RAG

Un chatbot de questions-réponses sur la réglementation de l'IA en France, construit en quatre TP.

## Installation

Python 3.11+ et [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/master-atal-cours/atal-m2-rag.git
cd atal-m2-rag
uv sync
uv run python scripts/download_corpus.py
```

Sans uv : `python -m venv .venv`, l'activer, `pip install -e .`, puis `rag …` au lieu de `uv run rag …`.

### Serveur LLM

Ollama sur votre machine (configuration par défaut) :

```bash
uv run python scripts/setup_ollama.py               # sans GPU : --model qwen3.5:4b
```

Voir [OLLAMA.md](OLLAMA.md).

Serveur de l'université : créer `config.local.toml` (ignoré par git) :

```toml
[api]
host = "blabla.univ-nantes.fr"
port = 8000

[embeddings]            # seulement si les embeddings sont servis sur un autre port
port = 8001
```

Serveur sans modèle d'embeddings : les calculer sur votre machine avec `uv sync --extra local` et

```toml
[embeddings]
provider = "local"
```

```bash
uv run rag check                                    # deux coches : LLM et embeddings
```

## Utilisation

```bash
uv run rag                                          # interface sur http://localhost:7860
uv run rag eval -v --only tableau,T3                # évaluation sans interface
```

- **Chat** : réponses, trace, passages retrouvés, prompt complet envoyé au LLM.
- **Évaluation** : les 41 questions, réponses attendues, score par catégorie.
- **Index** : passages d'un document, recherche sans LLM.

Après une modification du code : **Recharger le code**.

## Code

```
rag/
├── pipeline.py      enchaîne les composants
├── chunker.py       TP1, TP2   découpage en passages
├── encoder.py       TP1        textes → vecteurs
├── search.py        TP1, TP2   recherche des passages
├── prompt.py        TP1 à TP4  messages envoyés au LLM
├── rewriter.py      TP3        réécriture des questions de suite
├── context.py       TP3        sélection et ordre des passages
├── abstention.py    TP3        refus de répondre sans passage pertinent
├── router.py        TP4        choix de l'outil
├── sql.py           TP4        text-to-SQL sur les tableaux
├── catalog.py       TP4        questions sur la base documentaire
└── src/             code fourni (documents, clients LLM et embeddings, SQL, évaluation, interface)
data/
├── corpus.toml      manifeste du corpus
├── questions.toml   questionnaire et réponses attendues
└── corpus/          documents téléchargés
```

Les méthodes à écrire sont marquées `TPn : à compléter` ; leur docstring donne le contrat.

## Boîte à outils

Sorties réelles (bge-m3, qwen3.5:9b).

**Documents** (`rag/src/documents.py`), reçus par `Chunker.chunk(doc)` :

```python
doc.id, doc.format            # 'universites/charte-ia-uco.docx', 'docx'
doc.title, doc.meta           # titre ; date, status, source… (data/corpus.toml)
doc.raw_text                  # texte brut : TP1
doc.blocks                    # blocs structurés : TP2
block.kind, block.text        # 'heading', 'text' ou 'table' ; le contenu
block.level, block.page       # niveau d'un titre (1, 2…) ; page d'un PDF
block.rows                    # tableau : rows[0] est l'en-tête
# [['Année', '1981', '1982', …], ['Nombre de plaintes reçues', '136', '151', …]]
```

**Passages et index** (`rag/src/core.py`) :

```python
Chunk(text="…", doc_id=doc.id, meta={"section": "…"})  # chunk.id = 'doc_id#n' une fois indexé
Hit(chunk, 0.0325, details={"dense": 0.677, "bm25": 17.789})  # un passage retrouvé
self.index.chunks             # tous les passages ; self.index.vectors : matrice (n, d)
self.index.position[chunk.id] # indice d'un passage dans self.index.chunks
self.index.documents[doc_id]  # métadonnées d'un document : title, format, date, status…
```

**Embeddings** (`rag/src/embeddings.py`), `self.client` dans `Encoder` :

```python
V = self.client.embed(textes)            # (3, 1024)
q = self.client.embed([question])[0]     # (1024,)
V @ q                                    # [0.801, 0.332, 0.235] une fois normalisés
```

Normalisez dans `Encoder` : tous les serveurs ne renvoient pas des vecteurs de norme 1.

**LLM** (`rag/src/llm.py`), `self.llm` dans `rewriter`, `router`, `sql` et `catalog` :

```python
self.llm.ask("Définis un embedding en une phrase.")   # -> str
messages = [
    {"role": "system", "content": "Tu réponds en une phrase, en français."},
    {"role": "user", "content": "Qu'est-ce que la CNIL ?"},
]
self.llm.chat(messages, max_tokens=80, temperature=0)
# "La CNIL est l'autorité administrative française chargée de veiller au respect
#  des règles relatives à la protection des données personnelles."
self.llm.stream(messages)        # la même réponse, morceau par morceau

class Analyse(BaseModel):        # sortie structurée (pydantic), TP4
    type: Literal["definition", "chiffre", "autre"]
    annee: int | None

question = "Analyse la question : « Combien de plaintes la CNIL a-t-elle reçues en 2024 ? »"
self.llm.json([{"role": "user", "content": question}], Analyse)
# Analyse(type='chiffre', annee=2024)
```

**Recherche lexicale et tableaux** (`rag/src/text.py`, `rank_bm25`, `rag/chunker.py`) :

```python
from rank_bm25 import BM25Okapi
from .src.text import tokenize

tokenize("Que prévoit l'article 50 du règlement sur l'IA ?")  # ['prevoi', 'articl', '50', 'reglem', 'ia']
bm25 = BM25Okapi([tokenize(t) for t in textes])
bm25.get_scores(tokenize("amende 35 000 000"))   # un score par texte : [2.195, 0, 0]
serialize_row(["Pays", "2024", "2025"], ["Danemark", "28", "42"])  # 'Pays: Danemark | 2024: 28 | 2025: 42'
```

**Données tabulaires** (`rag/src/tables.py`), `self.tables` dans `SQLTool` :

```python
question = "Combien de contrôles la CNIL a-t-elle menés dans le secteur de la santé en 2025 ?"
self.tables.search(question, k=3)
# ['cnil_sanctions_prononcees_2020_2025', 'cnil_controles_2025', 'cnil_controles_2024']
print(self.tables.schema(["cnil_controles_2025"]))   # colonnes et valeurs possibles, pour le prompt
# TABLE cnil_controles_2025  -- Liste des contrôles réalisés par la CNIL en 2025 (323 lignes)
#   - secteur_du_controle  valeurs : Commerce, Santé, Collectivités territoriales, …
cols, rows = self.tables.query(
    "SELECT secteur_du_controle, COUNT(*) AS n FROM cnil_controles_2025 GROUP BY 1 ORDER BY n DESC LIMIT 3"
)
print(format_result(cols, rows))   # secteur_du_controle | n, Commerce | 140, Santé | 42…
self.tables.query("DELETE FROM cnil_controles_2025")  # SQLError : SELECT uniquement
```

## Solutions

`solutions/phase-N.zip` : les fichiers de `rag/` à la fin du TP N. Mettre son travail de côté, puis :

```bash
uv run python -m zipfile -e solutions/phase-2.zip rag/
```

`rag/src/` n'est pas touché.
