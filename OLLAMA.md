# Ollama sur votre machine

Si votre université ne vous fournit pas de serveur LLM, faites tourner les modèles du TP
sur votre machine avec [Ollama](https://ollama.com).

## En une commande

```bash
uv run python scripts/setup_ollama.py
```

Le script vérifie qu'Ollama est installé (sinon, il affiche la commande d'installation),
lance le serveur s'il ne tourne pas, télécharge les deux modèles, puis les essaie :

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

Ollama est prêt. Ensuite : uv run rag check, puis uv run rag
```

La configuration par défaut du TP vise déjà Ollama sur `localhost:11434` : rien d'autre à
régler.

## Installer Ollama

| Système | Commande |
|---|---|
| Windows | `winget install Ollama.Ollama`, ou l'installeur de https://ollama.com/download |
| macOS | `brew install ollama`, ou l'application de https://ollama.com/download |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

Sous Windows et macOS, l'application lance le serveur toute seule ; sous Linux, le script
d'installation en fait un service.

## Quel modèle de chat ?

| Votre machine | Modèle | Téléchargement |
|---|---|---|
| GPU avec 8 Go de mémoire ou plus, ou Mac Apple Silicon | `qwen3.5:9b` (défaut) | 6,6 Go |
| petit GPU, ou pas de GPU | `qwen3.5:4b` | environ 4 Go |

Pour le modèle plus petit :

```bash
uv run python scripts/setup_ollama.py --model qwen3.5:4b
```

Le script l'indique alors dans `config.local.toml` (`[llm] model`). Les scores de référence
du cours ont été mesurés avec `qwen3.5:9b` : attendez-vous à quelques points de moins.
Le modèle d'embeddings, `bge-m3` (1,2 Go), est le même pour tous.

## Problèmes courants

- **Ollama n'est pas reconnu après l'installation** : ouvrez un nouveau terminal.
- **Les réponses sont très lentes** : sans GPU, le modèle tourne sur le processeur. Passez à
  `qwen3.5:4b`.
- **Erreur de mémoire au chargement du modèle** : même remède, un modèle plus petit.
- **Le port 11434 est déjà utilisé** : un serveur Ollama tourne déjà, c'est bon signe.
- **Les réponses ignorent une partie des sources** : le contexte du modèle est peut-être trop
  court (le script l'affiche ; 4 096 tokens suffisent pour le TP). Pour l'agrandir, définissez
  `OLLAMA_CONTEXT_LENGTH=8192` avant de lancer le serveur, puis redémarrez Ollama :
  - Windows : `setx OLLAMA_CONTEXT_LENGTH 8192`, puis quitter et relancer l'application ;
  - macOS : `launchctl setenv OLLAMA_CONTEXT_LENGTH 8192`, puis relancer l'application ;
  - Linux : `sudo systemctl edit ollama`, ajouter `Environment="OLLAMA_CONTEXT_LENGTH=8192"`
    dans la section `[Service]`, puis `sudo systemctl restart ollama`.
