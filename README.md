# M2 ATAL - RAG

Construire un **assistant documentaire** fondé sur la génération augmentée par récupération
(RAG), en partant d'un pipeline naïf et en l'améliorant étape par étape. À chaque étape, on
mesure, on analyse ce qui échoue, et on corrige.

Le fil rouge : un chatbot de questions-réponses sur la réglementation de l'IA en France,
qui répond à partir d'une base documentaire hétérogène : règlement européen sur l'IA, RGPD, guides et données
ouvertes de la CNIL, statistiques de l'Insee, chartes universitaires, catalogue de modèles
de langage... en PDF, HTML, Markdown, DOCX, ODT, CSV, XLSX et JSON.

Les slides du cours : https://master-atal-cours.github.io/atal-m2-rag/ (flèches pour avancer, P pour la vue présentateur dans une autre fenêtre).

## Déroulé de la séance (4 h)

| | Présentation | Composants à compléter | Ce qui change |
|---|---|---|---|
| **1** | Le RAG naïf | `chunker`, `encoder`, `search`, `prompt` | découpage fixe, embeddings, recherche dense, prompt |
| **2** | Mieux découper, mieux chercher | `chunker`, `search`, `prompt` | découpage structurel, tableaux, BM25 + fusion, citations |
| | *Pause* | | |
| **3** | Conversation, contexte et versions | `rewriter`, `context`, `abstention`, `prompt` | réécriture de requête, voisins, dates et statuts, abstention |
| **4** | Router vers le bon outil | `router`, `sql`, `catalog`, `prompt` | routeur, text-to-SQL, catalogue, conversation |

## Le système

Chaque composant a son fichier dans `rag/`, et `rag/pipeline.py` les enchaîne :

```
conversation ─► router ─┬─ "documents"    ─► rewriter ─► search ─► abstention ─► context ─► prompt ─► LLM
                        ├─ "donnees"      ─► rewriter ─► sql
                        ├─ "catalogue"    ─► catalog
                        └─ "conversation" ─► prompt ─► LLM
```

Au départ, tous les composants existent mais ne font presque rien : le routeur n'a qu'une
route, `search` ne renvoie aucun passage, `prompt` renvoie la conversation telle quelle. Le
système envoie donc simplement la question au LLM. Chaque TP remplit quelques méthodes,
marquées `TPn : à compléter` ; leur docstring dit ce qu'elles doivent renvoyer.

## Installation

Prérequis : Python 3.11 ou plus récent et git. [uv](https://docs.astral.sh/uv/) est
recommandé (il installe aussi la bonne version de Python).

```bash
git clone https://github.com/master-atal-cours/atal-m2-rag.git
cd atal-m2-rag
uv sync
```

Sans uv :

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -e .
```

Les commandes ci-dessous s'écrivent `uv run rag …` avec uv, ou `rag …` dans un
environnement virtuel activé (`python -m rag …` fonctionne aussi).

### 1. Télécharger le corpus

```bash
uv run python scripts/download_corpus.py
```

Le script télécharge les 48 documents (environ 10 Mo) dans `data/corpus/`. Si une source
est indisponible, l'enseignant fournira une archive : `--zip <archive ou URL>`.

### 2. Un serveur pour le LLM

Le LLM et le modèle d'embeddings sont servis par une API compatible OpenAI.

**Sans serveur fourni par votre université**, faites tourner les modèles sur votre machine
avec [Ollama](https://ollama.com) :

```bash
uv run python scripts/setup_ollama.py
```

Le script vérifie l'installation d'Ollama, lance le serveur, télécharge `qwen3.5:9b` et
`bge-m3`, puis les essaie. La configuration par défaut vise déjà Ollama : rien d'autre à
faire. Sans GPU, ajoutez `--model qwen3.5:4b`. Détails et problèmes courants :
[OLLAMA.md](OLLAMA.md).

**Si votre université fournit un serveur**, créez un fichier `config.local.toml` (ignoré par
git) avec son adresse :

```toml
[api]
host = "blabla.univ-nantes.fr"
port = 8000
```

Si les embeddings ont un port à part : `[embeddings]` puis `port = …`.

### 3. Vérifier

```bash
uv run rag check
```

doit afficher deux coches : le LLM répond, les embeddings sont calculés.

> Sans accès à l'API d'embeddings, vous pouvez les calculer sur votre machine (plus lent) :
> `uv sync --extra local`, puis `provider = "local"` dans la section `[embeddings]`.

## Utiliser le système

```bash
uv run rag
```

puis ouvrir http://localhost:7860. L'interface a trois onglets :

- **Chat** : poser des questions ; à droite, la trace (requête, route…) et les passages
  retrouvés, et dans l'onglet **Prompt**, chaque appel au LLM avec tous ses messages : ce
  que le modèle voit vraiment ;
- **Évaluation** : le bouton envoie les 41 questions du questionnaire et affiche chaque
  réponse à côté de la réponse attendue, avec le score par catégorie ;
- **Index** : les passages d'un document (votre découpage) et une recherche sans LLM.

Après avoir modifié votre code, cliquez sur **Recharger le code** : les composants sont
rechargés et l'index reconstruit (les embeddings déjà calculés sont en cache). Une erreur
dans votre code s'affiche en haut de la page.

`uv run rag eval` lance l'évaluation sans interface (`-v` : affiche les réponses,
`--only tableau,T3` : une partie du questionnaire).

## Le corpus

48 documents publics, décrits dans `data/corpus.toml` (source, date, statut, licence) :

| Collection | Documents | Formats |
|---|---|---|
| Réglementation | règlement (UE) 2024/1689 sur l'IA, proposition de la Commission de 2021, RGPD | XHTML |
| CNIL | guide de la sécurité des données, recommandation et fiches IA, liste de vérification, webinaire, page des sanctions | PDF, HTML |
| Données ouvertes CNIL | amendes, sanctions, plaintes, mises en demeure, contrôles 2024 et 2025 | CSV, XLSX |
| Insee | TIC dans les entreprises en 2024 et en 2025, tableaux de données | PDF, HTML, XLSX |
| Guides Etalab | pseudonymisation, annotation, algorithmes publics | Markdown |
| Chartes | chartes IA de l'UCO et de l'Université Clermont Auvergne | DOCX, PDF |
| Modèles | catalogue compar:IA (154 modèles de langage) | JSON |
| CNNum | synthèse « Données, traces et algorithmes » | ODT |
| Wikipédia | 8 articles (règlement IA, RGPD, CNIL, LLM, RAG, Mistral AI…) | HTML |

Il contient volontairement des pièges : deux versions d'un même texte (proposition et
règlement adopté), deux éditions d'une même statistique (2024 et 2025), des numéros
d'article qui existent dans plusieurs textes, des tableaux de centaines de lignes…

Les fichiers ne sont pas redistribués par ce dépôt : chacun reste soumis à la licence de
sa source (Licence Ouverte, CC BY-SA, Apache-2.0…), indiquée dans le manifeste.

## Le questionnaire

`data/questions.toml` contient 41 questions de 11 types, dont des conversations
multi-tours. Chacune indique la phase à partir de laquelle on s'attend à la réussir :

| Type | Exemple | Phase |
|---|---|---|
| factuel | À partir de quelle date le RGPD est-il applicable ? | 1 |
| identifiant | Que prévoit l'article 50 du règlement européen sur l'IA ? | 2 |
| tableau | Combien de plaintes la CNIL a-t-elle reçues en 2024 ? | 2 |
| structure | Que ne faut-il pas faire en matière de sauvegarde, selon le guide de la CNIL ? | 2 |
| multi-tours | … « Et en 2020 ? » | 3 |
| versions | Quel est le montant maximal des amendes pour une pratique d'IA interdite ? | 3 |
| synthèse | Que recommandent la CNIL et Etalab au sujet de l'annotation ? | 3 |
| abstention | Combien de contrôles la CNIL a-t-elle réalisés en 2012 ? (absent du corpus) | 3 |
| agrégation | Combien de contrôles la CNIL a-t-elle menés dans le secteur de la santé en 2025 ? | 4 |
| catalogue | Quels documents de la base proviennent de l'Insee ? | 4 |
| conversation | « Traduis ta réponse en anglais. » | 4 |

La notation est automatique (éléments attendus dans la réponse, abstention détectée) et
distingue deux causes d'échec : la recherche n'a pas trouvé le bon document, ou le LLM
n'a pas su l'exploiter. Chaque question a aussi une réponse de référence (`reference`),
affichée dans l'onglet Évaluation. Ajoutez vos propres questions !

## Organisation du code

```
rag/
├── pipeline.py      enchaîne les composants (rien à modifier)
├── chunker.py       TP1, TP2   découpe un document en passages
├── encoder.py       TP1        transforme des textes en vecteurs
├── search.py        TP1, TP2   retrouve les passages les plus proches d'une requête
├── prompt.py        TP1 à TP4  construit les messages envoyés au LLM
├── rewriter.py      TP3        réécrit une question de suite en requête autonome
├── context.py       TP3        choisit et ordonne les passages montrés au LLM
├── abstention.py    TP3        ne pas répondre quand rien de pertinent n'est retrouvé
├── router.py        TP4        choisit l'outil : documents, données, catalogue, conversation
├── sql.py           TP4        text-to-SQL sur les tableaux du corpus
├── catalog.py       TP4        questions sur la base documentaire elle-même
└── src/             code fourni, à lire si besoin : lecture des documents, clients du
                     LLM et des embeddings, base SQL, évaluation, interface
data/
├── corpus.toml      manifeste du corpus
├── questions.toml   questionnaire, avec les réponses attendues
└── corpus/          documents téléchargés (non versionnés)
```

## Boîte à outils

Ce que le code fourni met à votre disposition. Les sorties en commentaire sont réelles
(bge-m3, qwen3.5:9b).

**Documents** (`rag/src/documents.py`) : ce que reçoit `Chunker.chunk(doc)`

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

**Passages et index** (`rag/src/core.py`)

```python
Chunk(text="…", doc_id=doc.id, meta={"section": "…"})  # chunk.id = 'doc_id#n' une fois indexé
Hit(chunk, 0.0325, details={"dense": 0.677, "bm25": 17.789})  # un passage retrouvé
self.index.chunks             # tous les passages ; self.index.vectors : matrice (n, d)
self.index.position[chunk.id] # indice d'un passage dans self.index.chunks
self.index.documents[doc_id]  # métadonnées d'un document : title, format, date, status…
```

**Embeddings** (`rag/src/embeddings.py`) : dans `Encoder`, `self.client`

```python
V = self.client.embed(textes)            # (3, 1024) : un vecteur par texte
q = self.client.embed([question])[0]     # (1024,)
V @ q                                    # [0.801, 0.332, 0.235] une fois normalisés
```

Avec bge-m3 servi par Ollama, les vecteurs arrivent déjà de norme 1, mais ce n'est pas le
cas de tous les modèles ni de tous les serveurs : normalisez-les dans `Encoder`.

**LLM** (`rag/src/llm.py`) : `self.llm` dans le rewriter, le routeur, `sql` et `catalog`

```python
self.llm.ask("Définis un embedding en une phrase.")   # -> str
messages = [
    {"role": "system", "content": "Tu réponds en une phrase, en français."},
    {"role": "user", "content": "Qu'est-ce que la CNIL ?"},
]
self.llm.chat(messages, max_tokens=80)
# "La CNIL est l'autorité administrative française chargée de veiller au respect
#  des règles relatives à la protection des données personnelles."
self.llm.stream(messages)        # la même réponse, morceau par morceau
```

`chat` et `stream` acceptent `temperature=` et `max_tokens=`. Pour le TP4, la sortie
structurée :

```python
class Analyse(BaseModel):                        # pydantic : JSON validé
    type: Literal["definition", "chiffre", "autre"]
    annee: int | None

question = "Analyse la question : « Combien de plaintes la CNIL a-t-elle reçues en 2024 ? »"
self.llm.json([{"role": "user", "content": question}], Analyse)
# Analyse(type='chiffre', annee=2024)
```

**Recherche lexicale et tableaux** (`rag/src/text.py`, `rank_bm25`, `rag/chunker.py`)

```python
from rank_bm25 import BM25Okapi
from .src.text import tokenize

tokenize("Que prévoit l'article 50 du règlement sur l'IA ?")  # ['prevoi', 'articl', '50', 'reglem', 'ia']
bm25 = BM25Okapi([tokenize(t) for t in textes])
bm25.get_scores(tokenize("amende 35 000 000"))   # un score par texte : [2.195, 0, 0]
serialize_row(["Pays", "2024", "2025"], ["Danemark", "28", "42"])  # 'Pays: Danemark | 2024: 28 | 2025: 42'
```

**Données tabulaires** (`rag/src/tables.py`) : dans `SQLTool`, `self.tables`

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
self.tables.query("DELETE FROM cnil_controles_2025")  # SQLError : seules les requêtes SELECT…
```

Dans les exemples, `textes` contient trois phrases : une sur les amendes du règlement sur
l'IA, une sur les plaintes reçues par la CNIL, et une recette de tarte tatin ; `question`
porte sur l'amende d'une pratique d'IA interdite.

## Solutions

Le dossier `solutions/` contient une archive par phase, avec les fichiers de `rag/` à la fin
de cette phase, pour repartir d'une base qui fonctionne si vous n'avez pas terminé un TP :

| Archive | Contenu |
|---|---|
| `solutions/phase-1.zip` | TP 1 résolu (point de départ du TP 2) |
| `solutions/phase-2.zip` | TP 1 et 2 résolus (point de départ du TP 3) |
| `solutions/phase-3.zip` | TP 1 à 3 résolus (point de départ du TP 4) |
| `solutions/phase-4.zip` | tout résolu |

Pour repartir de la solution du TP 2, par exemple : mettez votre travail de côté (commit ou
copie), décompressez l'archive dans `rag/`, puis cliquez sur **Recharger le code**.

```bash
uv run python -m zipfile -e solutions/phase-2.zip rag/
```

Les fichiers de `rag/` sont remplacés ; `rag/src/` n'est pas touché.
