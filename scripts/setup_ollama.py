"""Prépare Ollama pour le TP : serveur, téléchargement et essai des modèles.

    python scripts/setup_ollama.py                       # qwen3.5:9b et bge-m3
    python scripts/setup_ollama.py --model qwen3.5:4b    # sans GPU
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_EMBEDDING = "bge-m3"
SMALL_MODEL = "qwen3.5:4b"

INSTALL = {
    "Windows": "winget install Ollama.Ollama   (ou l'installeur de https://ollama.com/download)",
    "Darwin": "brew install ollama   (ou l'application de https://ollama.com/download)",
    "Linux": "curl -fsSL https://ollama.com/install.sh | sh",
}


def ok(text: str) -> None:
    print(f"  ✓ {text}")


def warn(text: str) -> None:
    print(f"  ! {text}")


def fail(text: str) -> None:
    print(f"  ✗ {text}")
    sys.exit(1)


def request(url: str, payload: dict | None = None, timeout: float = 10) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def server_up(base: str) -> bool:
    try:
        request(f"{base}/api/version", timeout=3)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def start_server(base: str) -> None:
    """Lance « ollama serve » en arrière-plan et attend qu'il réponde."""
    log = Path(tempfile.gettempdir()) / "ollama-serve.log"
    kwargs: dict = {"stdout": log.open("ab"), "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(["ollama", "serve"], **kwargs)
    for _ in range(30):
        time.sleep(1)
        if server_up(base):
            ok(f"serveur lancé (journal : {log})")
            return
    fail(f"le serveur ne répond pas après 30 s ; voir {log}")


def gpu() -> str | None:
    """Description du GPU, ou None si aucun n'est détecté."""
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                check=False, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if out:
                return out.splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            pass
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "Apple Silicon (Metal)"
    return None


def installed_models(base: str) -> set[str]:
    names = set()
    for model in request(f"{base}/api/tags").get("models", []):
        names.add(model["name"])
        if model["name"].endswith(":latest"):
            names.add(model["name"].removesuffix(":latest"))
    return names


def pull(model: str, present: set[str]) -> None:
    if model in present:
        ok(f"{model} déjà téléchargé")
        return
    print(f"  téléchargement de {model}…")
    if subprocess.run(["ollama", "pull", model], check=False).returncode != 0:
        fail(f"échec du téléchargement de {model} : vérifiez le nom")
    ok(f"{model} téléchargé")


def try_models(base: str, model: str, embedding: str) -> None:
    start = time.time()
    reply = request(f"{base}/v1/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "Réponds simplement « OK »."}],
        "max_tokens": 10,
        "reasoning_effort": "none",
    }, timeout=300)
    text = reply["choices"][0]["message"]["content"].strip()
    ok(f"{model} répond « {text} » ({time.time() - start:.1f} s, chargement compris)")
    # À lire tout de suite : charger le modèle d'embeddings peut décharger le modèle de chat
    for loaded in request(f"{base}/api/ps").get("models", []):
        if loaded["name"] in (model, f"{model}:latest") and loaded.get("context_length"):
            context = loaded["context_length"]
            if context < 4096:
                warn(f"contexte de {context} tokens : trop court, définir OLLAMA_CONTEXT_LENGTH=8192 et relancer Ollama")
            else:
                ok(f"contexte de {context} tokens")
    start = time.time()
    vectors = request(f"{base}/v1/embeddings", {"model": embedding, "input": ["test"]}, timeout=120)
    ok(f"{embedding} : vecteurs de dimension {len(vectors['data'][0]['embedding'])} ({time.time() - start:.1f} s)")


def write_config(model: str) -> None:
    """Indique un modèle de chat différent du modèle par défaut dans config.local.toml."""
    path = ROOT / "config.local.toml"
    line = f'model = "{model}"'
    if not path.exists():
        path.write_text(f"[llm]\n{line}\n", encoding="utf-8")
        ok(f"config.local.toml créé : [llm] {line}")
    elif line in path.read_text(encoding="utf-8"):
        ok(f"config.local.toml indique déjà {line}")
    else:
        warn(f"ajoutez dans config.local.toml, section [llm] : {line}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Prépare Ollama pour le TP RAG")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"modèle de chat (défaut : {DEFAULT_MODEL})")
    parser.add_argument("--embedding", default=DEFAULT_EMBEDDING, help=f"modèle d'embeddings (défaut : {DEFAULT_EMBEDDING})")
    parser.add_argument("--url", default="http://localhost:11434", help="adresse du serveur Ollama")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    print("1. Installation")
    if not shutil.which("ollama"):
        fail("Ollama n'est pas installé. Installez-le, puis relancez ce script :\n"
             f"      {INSTALL.get(platform.system(), 'https://ollama.com/download')}")
    version = subprocess.run(["ollama", "--version"], check=False, capture_output=True, text=True)
    lines = (version.stdout + version.stderr).splitlines()
    ok(next((line.strip() for line in lines if "version is" in line), "Ollama installé"))

    print("2. Serveur")
    if server_up(base):
        ok(f"le serveur répond sur {base}")
    elif base in ("http://localhost:11434", "http://127.0.0.1:11434"):
        print("  le serveur ne tourne pas : lancement de « ollama serve »…")
        start_server(base)
    else:
        fail(f"aucun serveur ne répond sur {base}")

    print("3. Matériel")
    card = gpu()
    if card:
        ok(f"GPU : {card}")
    else:
        warn("aucun GPU détecté : les réponses seront lentes.")
        if args.model == DEFAULT_MODEL:
            warn(f"conseil : relancez avec --model {SMALL_MODEL} (plus petit, plus rapide)")

    print("4. Modèles")
    present = installed_models(base)
    pull(args.model, present)
    pull(args.embedding, present)

    print("5. Essai")
    try:
        try_models(base, args.model, args.embedding)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        fail(f"l'essai a échoué : {e}")

    if args.model != DEFAULT_MODEL:
        print("6. Configuration")
        write_config(args.model)
    if args.embedding != DEFAULT_EMBEDDING:
        warn(f'ajoutez dans config.local.toml, section [embeddings] : model = "{args.embedding}"')
    print("\nOllama est prêt. Ensuite : uv run rag check, puis uv run rag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
