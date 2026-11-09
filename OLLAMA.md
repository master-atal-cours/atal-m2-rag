## Installation

| Système | Commande |
|---|---|
| Windows | `winget install Ollama.Ollama`, ou https://ollama.com/download |
| macOS | `brew install ollama`, ou https://ollama.com/download |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

## Préparation

```bash
uv run python scripts/setup_ollama.py
```

Le script lance le serveur, télécharge les modèles et les essaie :

```
1. Installation
  ✓ ollama version is 0.40.8
2. Serveur
  ✓ le serveur répond sur http://localhost:11434
3. Matériel
  ✓ GPU : NVIDIA GeForce RTX 5070 Ti, 16303 MiB
4. Modèles
  ✓ qwen3.5:9b déjà téléchargé
  ✓ bge-m3 déjà téléchargé
5. Essai
  ✓ qwen3.5:9b répond « OK » (3.3 s, chargement compris)
  ✓ contexte de 4096 tokens
  ✓ bge-m3 : vecteurs de dimension 1024 (2.1 s)
```

## Modèles

| Machine | Modèle | Taille |
|---|---|---|
| GPU 8 Go+ ou Mac Apple Silicon | `qwen3.5:9b` (défaut) | 6,6 Go |
| petit GPU ou pas de GPU | `qwen3.5:4b` | 4 Go |

```bash
uv run python scripts/setup_ollama.py --model qwen3.5:4b
```

Le script écrit alors le modèle dans `config.local.toml`. Embeddings : `bge-m3` (1,2 Go) dans tous les cas.
