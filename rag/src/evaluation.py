"""Évaluation sur le questionnaire data/questions.toml.                 [FOURNI]

Onglet « Évaluation » de l'interface, ou en ligne de commande : rag eval [-v] [--only tableau,T3]

Chaque question est notée automatiquement :

- **réponse** : présence des éléments attendus (``expect``) : chaîne, liste
  d'alternatives ou expression régulière préfixée par « re: ». La comparaison
  ignore la casse, les accents et les séparateurs de milliers. Pour
  ``abstain = true``, le système doit dire qu'il n'a pas trouvé l'information.
- **sources** : présence des documents attendus (``sources``) parmi les passages
  fournis au LLM, pour distinguer erreur de recherche et erreur de génération.

Les résultats sont enregistrés dans runs/.
"""

from __future__ import annotations

import json
import re
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .config import ROOT
from .core import Answer, Message
from .text import normalize

QUESTIONS = ROOT / "data" / "questions.toml"
RUNS = ROOT / "runs"

CATEGORIES = {
    "factuel": "Fait énoncé dans un paragraphe",
    "identifiant": "Article, numéro, référence exacte",
    "tableau": "Valeur dans un tableau (CSV, XLSX, HTML, JSON)",
    "structure": "Réponse qui dépend du titre de la section",
    "multi-tours": "Question de suivi dans une conversation",
    "versions": "Plusieurs versions d'un document",
    "synthese": "Réponse qui combine plusieurs documents",
    "abstention": "Réponse absente du corpus",
    "agregation": "Comptage, somme, classement sur des données",
    "catalogue": "Question sur la base documentaire elle-même",
    "conversation": "Échange sans recherche (salutation, reformulation)",
}

ABSTENTION_MARKERS = [
    "pas trouve", "n'ai trouve aucun", "ne contient pas", "ne contiennent pas", "aucune information",
    "pas possible de", "n'est pas possible", "ne peux pas", "ne peut pas etre determine",
    "pas d'information", "pas d'informations", "ne figure pas", "ne figurent pas", "ne mentionne pas",
    "ne mentionnent pas", "ne precise pas", "ne precisent pas", "pas en mesure", "je ne sais pas",
    "impossible de repondre", "ne permet pas de", "ne permettent pas de", "n'est pas indique",
    "n'est pas mentionne", "n'est pas precise", "ne dispose pas", "pas disponible", "aucun element",
    "ne fournissent pas", "ne fournit pas", "pas de donnees", "aucune donnee", "aucune mention",
    "aucun resultat", "pas couverte", "pas couvert", "ne couvre pas", "ne couvrent pas",
]


@dataclass
class Question:
    id: str
    category: str
    turns: list[str]  # alternance utilisateur / assistant, en commençant par l'utilisateur
    expect: list[Any] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    first: list[list[str]] = field(default_factory=list)  # [bonnes valeurs, mauvaises valeurs]
    abstain: bool = False
    sources: list[str] = field(default_factory=list)
    max_chars: int | None = None
    phase: int = 1
    reference: str = ""  # réponse attendue, affichée à côté de celle du système
    note: str = ""

    @property
    def conversation(self) -> list[Message]:
        roles = ["user", "assistant"]
        return [{"role": roles[i % 2], "content": t} for i, t in enumerate(self.turns)]

    @property
    def question(self) -> str:
        return self.turns[-1]


def load_questions(path=QUESTIONS) -> list[Question]:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    questions = []
    for q in data["questions"]:
        turns = q.get("turns") or [q["question"]]
        questions.append(Question(
            id=q["id"], category=q["category"], turns=turns, expect=q.get("expect", []),
            forbid=q.get("forbid", []), first=q.get("first", []), abstain=q.get("abstain", False),
            sources=q.get("sources", []),
            max_chars=q.get("max_chars"), phase=q.get("phase", 1), reference=q.get("reference", ""),
            note=q.get("note", ""),
        ))
    return questions


# ─────────────────────────────────────────────────────────────────────────────
#  Notation
# ─────────────────────────────────────────────────────────────────────────────


def _norm(text: str) -> str:
    text = normalize(text)
    text = re.sub(r"(?<=\d)[ .](?=\d{3}\b)", "", text)  # 35 000 000 / 35.000.000 -> 35000000
    text = re.sub(r"\s*%", " %", text)
    return re.sub(r"\s+", " ", text)


def _match(item: Any, answer: str) -> bool:
    if isinstance(item, list):
        return any(_match(alternative, answer) for alternative in item)
    item = str(item)
    if item.startswith("re:"):
        return re.search(_norm(item[3:]).replace(" %", r"\s*%"), answer) is not None
    return _norm(item) in answer


def is_abstention(text: str) -> bool:
    norm = _norm(text)
    return any(marker in norm for marker in ABSTENTION_MARKERS)


def grade(question: Question, answer: str) -> tuple[bool, str]:
    """(réussite, explication)."""
    norm = _norm(answer)
    if question.abstain:
        return (True, "abstention correcte") if is_abstention(answer) else (False, "devait s'abstenir")
    missing = [item for item in question.expect if not _match(item, norm)]
    forbidden = [item for item in question.forbid if _match(item, norm)]
    if missing:
        what = " / ".join(str(m) if not isinstance(m, list) else "|".join(map(str, m)) for m in missing)
        reason = f"manque : {what}"
        if is_abstention(answer):
            reason = "abstention à tort (" + reason + ")"
        return False, reason
    if forbidden:
        return False, f"contient : {', '.join(map(str, forbidden))}"
    if question.first:
        # La bonne valeur doit apparaître avant la mauvaise (ex. 35 M€ avant 30 M€ :
        # la réponse principale est la bonne, l'autre n'est au mieux qu'une mention)
        good, bad = question.first
        position = lambda items: min((p for i in items if (p := norm.find(_norm(i))) >= 0), default=-1)  # noqa: E731
        p_good, p_bad = position(good), position(bad)
        if p_bad >= 0 and (p_good < 0 or p_bad < p_good):
            return False, f"donne d'abord : {bad[0]}"
    if question.max_chars and len(answer) > question.max_chars:
        return False, f"trop long ({len(answer)} > {question.max_chars} caractères)"
    return True, "ok"


def sources_found(question: Question, answer: Answer) -> bool | None:
    if not question.sources:
        return None
    found = {hit.chunk.doc_id for hit in answer.sources}
    found |= set(answer.trace.get("documents", []))
    return all(any(src in doc for doc in found) for src in question.sources)


# ─────────────────────────────────────────────────────────────────────────────
#  Exécution
# ─────────────────────────────────────────────────────────────────────────────


def evaluate(pipeline: Any, question: Question) -> dict[str, Any]:
    """Pose une question au pipeline et note sa réponse."""
    start = time.time()
    try:
        answer = pipeline.answer(question.conversation)
        text = answer.text
        error = None
    except Exception as e:  # noqa: BLE001 - une question en erreur ne bloque pas l'évaluation
        answer, text, error = Answer(), "", f"{type(e).__name__}: {e}"
    ok, reason = grade(question, text) if error is None else (False, error)
    return {
        "id": question.id,
        "category": question.category,
        "phase": question.phase,
        "question": question.question,
        "reference": question.reference,
        "answer": text,
        "ok": ok,
        "reason": reason,
        "sources_ok": sources_found(question, answer),
        "sources": [hit.chunk.id for hit in answer.sources],
        "trace": {k: v for k, v in answer.trace.items() if isinstance(v, (str, int, float, bool, list))},
        "seconds": round(time.time() - start, 1),
    }


def run(pipeline: Any, questions: list[Question], workers: int = 1) -> list[dict[str, Any]]:
    def one(question: Question) -> dict[str, Any]:
        return evaluate(pipeline, question)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, questions))
    return [one(q) for q in questions]


def regrade(path: str, questions: list[Question]) -> list[dict[str, Any]]:
    """Re-note les réponses d'un fichier de résultats avec le questionnaire actuel."""
    by_id = {q.id: q for q in questions}
    results = json.loads((ROOT / path).read_text(encoding="utf-8"))
    for r in results:
        if r["id"] in by_id and not r["reason"].startswith(("LLMError", "SQLError", "Embedding")):
            r["ok"], r["reason"] = grade(by_id[r["id"]], r["answer"])
    return results


def save(results: list[dict[str, Any]], pipeline_name: str) -> str:
    RUNS.mkdir(exist_ok=True)
    path = RUNS / f"{pipeline_name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path.relative_to(ROOT))


def report(results: list[dict[str, Any]], pipeline_name: str, verbose: bool = False) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title=f"Évaluation — pipeline {pipeline_name}", show_lines=False)
    for column in ("id", "catégorie", "question", "réponse", "sources", "s"):
        table.add_column(column, no_wrap=column != "question")
    for r in results:
        sources = "—" if r["sources_ok"] is None else ("✓" if r["sources_ok"] else "✗")
        mark = "[green]✓[/]" if r["ok"] else f"[red]✗[/] [dim]{r['reason'][:50]}[/]"
        table.add_row(r["id"], r["category"], r["question"][:70], mark, sources, f"{r['seconds']:.0f}")
    console.print(table)

    summary = Table(title="Par catégorie")
    for column in ("catégorie", "réussite", "sources trouvées", "description"):
        summary.add_column(column)
    for category, description in CATEGORIES.items():
        rows = [r for r in results if r["category"] == category]
        if not rows:
            continue
        ok = sum(r["ok"] for r in rows)
        with_sources = [r for r in rows if r["sources_ok"] is not None]
        found = f"{sum(r['sources_ok'] for r in with_sources)}/{len(with_sources)}" if with_sources else "—"
        color = "green" if ok == len(rows) else "yellow" if ok else "red"
        summary.add_row(category, f"[{color}]{ok}/{len(rows)}[/]", found, description)
    console.print(summary)
    total = sum(r["ok"] for r in results)
    console.print(f"[bold]Score : {total}/{len(results)}[/bold]")

    if verbose:
        for r in results:
            status = "[green]✓[/]" if r["ok"] else "[red]✗[/]"
            console.rule(f"{status} {r['id']} · {r['question']}")
            for key in ("query", "route", "sql"):
                if key in r["trace"]:
                    console.print(f"[dim]{key} : {r['trace'][key]}[/]")
            console.print(r["answer"] or "[dim](vide)[/]")
            if not r["ok"]:
                console.print(f"[red]{r['reason']}[/]")
