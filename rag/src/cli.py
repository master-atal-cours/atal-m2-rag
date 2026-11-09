"""Ligne de commande.                                                     [FOURNI]

    rag              lance l'interface web (http://localhost:7860)
    rag check        vérifie la connexion au LLM et au serveur d'embeddings
    rag eval         évalue le système sur le questionnaire, sans interface (-v : réponses)
"""

from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console

console = Console()


def cmd_check(args) -> int:
    from .config import load_settings
    from .embeddings import EmbeddingClient
    from .llm import LLM

    settings = load_settings()
    console.print(f"API LLM          : {settings.api.base_url}  (modèle : {settings.llm_model})")
    if settings.embedding_provider == "local":
        console.print(f"Embeddings       : locaux ({settings.local_embedding_model})")
    else:
        console.print(f"API embeddings   : {settings.embeddings.base_url}  (modèle : {settings.embedding_model})")
    ok = True
    try:
        start = time.time()
        reply = LLM(settings).ask("Réponds simplement « OK ».", max_tokens=10)
        console.print(f"[green]✓[/] LLM : « {reply} » ({time.time() - start:.1f} s)")
    except Exception as e:  # noqa: BLE001
        ok = False
        console.print(f"[red]✗ LLM : {e}[/]")
    try:
        start = time.time()
        vector = EmbeddingClient(settings).embed([f"test de connexion {time.time()}"], progress=False)[0]
        console.print(f"[green]✓[/] Embeddings : dimension {vector.shape[0]} ({time.time() - start:.1f} s)")
    except Exception as e:  # noqa: BLE001
        ok = False
        console.print(f"[red]✗ Embeddings : {e}[/]")
    return 0 if ok else 1


def cmd_eval(args) -> int:
    from ..pipeline import Pipeline
    from .core import Resources
    from .evaluation import load_questions, regrade, report, run, save

    questions = load_questions()
    if args.regrade:  # re-note des réponses déjà enregistrées, sans rappeler le LLM
        report(regrade(args.regrade, questions), args.regrade, verbose=args.verbose)
        return 0
    if args.only:
        wanted = {w.strip().lower() for w in args.only.split(",")}
        questions = [q for q in questions if q.id.lower() in wanted or q.category in wanted]
    pipeline = Pipeline(Resources())
    start = time.time()
    results = run(pipeline, questions, workers=args.workers)
    report(results, "rag", verbose=args.verbose)
    console.print(f"[dim]{time.time() - start:.0f} s · résultats enregistrés dans {save(results, 'eval')}[/]")
    return 0


def cmd_ui(args) -> int:
    from .app import launch

    launch(port=args.port, share=args.share)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="rag", description="TP RAG — M2 ATAL")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true", help="lien public temporaire Gradio")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("check", help="vérifie la connexion à l'API").set_defaults(func=cmd_check)
    p = sub.add_parser("eval", help="évalue sur le questionnaire, sans interface")
    p.add_argument("--only", help="catégories ou identifiants, séparés par des virgules")
    p.add_argument("-w", "--workers", type=int, default=4, help="questions traitées en parallèle")
    p.add_argument("-v", "--verbose", action="store_true", help="affiche les réponses")
    p.add_argument("--regrade", metavar="RUN", help="re-note un fichier de runs/ sans rappeler le LLM")
    p.set_defaults(func=cmd_eval)
    args = parser.parse_args(argv)
    if args.command is None:  # rag, sans sous-commande : l'interface web
        args.func = cmd_ui
    try:
        return args.func(args)
    except Exception as e:  # noqa: BLE001 - message lisible plutôt qu'une trace
        console.print(f"[red]{type(e).__name__} : {e}[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
