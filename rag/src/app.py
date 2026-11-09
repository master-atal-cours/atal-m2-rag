"""Interface web (Gradio) : chat, évaluation et exploration de l'index.  [FOURNI]

    uv run rag        puis ouvrir http://localhost:7860

Après une modification de votre code, cliquez sur « Recharger le code » : les
composants sont rechargés et l'index reconstruit (les embeddings déjà calculés
sont en cache).
"""

from __future__ import annotations

import html
import importlib
import queue
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import gradio as gr

from .core import Answer, Resources
from .evaluation import CATEGORIES, evaluate, load_questions, save
from .llm import record_calls

# Modules de votre code, dans l'ordre où les recharger (dépendances d'abord)
COMPONENTS = [
    "rag.abstention", "rag.chunker", "rag.encoder", "rag.search", "rag.prompt", "rag.rewriter",
    "rag.context", "rag.router", "rag.sql", "rag.catalog", "rag.pipeline",
]

EXAMPLES = [
    "Que prévoit l'article 50 du règlement européen sur l'IA ?",
    "Combien de plaintes la CNIL a-t-elle reçues en 2024 ?",
    "Quelle part des entreprises françaises utilise l'IA ?",
    "Combien de contrôles la CNIL a-t-elle réalisés en 2025 ?",
    "Quels documents de la base proviennent de l'Insee ?",
]

EVAL_COLUMNS = ["", "id", "catégorie", "question", "réponse attendue", "réponse du système", "remarque"]
EVAL_WORKERS = 4  # questions envoyées en parallèle


class System:
    """Le pipeline courant, reconstruit à chaque rechargement du code."""

    def __init__(self) -> None:
        self.resources = Resources()
        self.pipeline: Any = None
        self.status = ""
        self.lock = threading.Lock()
        self.reload()

    def reload(self) -> str:
        with self.lock:
            try:
                for name in COMPONENTS:
                    if name in sys.modules:
                        importlib.reload(sys.modules[name])
                    else:
                        importlib.import_module(name)
                self.pipeline = sys.modules["rag.pipeline"].Pipeline(self.resources)
                index = self.pipeline.index
                dim = index.vectors.shape[1] if index.vectors.ndim == 2 else 0
                self.status = (
                    f"Code chargé · {len(index.chunks)} passages, vecteurs de dimension {dim}, "
                    f"{len(index.documents)} documents"
                )
            except Exception:  # noqa: BLE001 - une erreur dans le code des étudiants ne doit pas tout arrêter
                error = traceback.format_exc(limit=-3)
                print(error, file=sys.stderr)
                kept = " (la version précédente reste active)" if self.pipeline else ""
                self.status = f"⚠ Erreur au chargement du code{kept} :\n```\n{error}\n```"
            return self.status


# ─────────────────────────────────────────────────────────────────────────────
#  Chat
# ─────────────────────────────────────────────────────────────────────────────


def _trace_markdown(answer: Answer) -> str:
    lines = []
    trace = {k: v for k, v in answer.trace.items() if k != "documents" and v not in (None, "", [])}
    if trace:
        lines.append("#### Trace")
        # Dans un bloc de code Markdown, le texte s'affiche tel quel : pas d'échappement HTML
        lines += [f"- **{k}** : `{' '.join(str(v).replace('`', chr(39)).split())[:400]}`" for k, v in trace.items()]
    if answer.sources:
        lines.append(f"#### {len(answer.sources)} passages fournis au LLM")
        for i, hit in enumerate(answer.sources, start=1):
            text = html.escape(hit.chunk.text[:700]).replace("\n", "<br>")
            lines.append(
                f"<details><summary><b>[{i}]</b> {html.escape(hit.chunk.id)} "
                f"<small>(score {hit.score:.3f})</small></summary><small>{text}…</small></details>"
            )
    return "\n".join(lines) or "_Aucun passage utilisé pour cette réponse._"


def _prompt_markdown(calls: list[dict]) -> str:
    """Chaque appel au LLM, avec tous ses messages, tels que le modèle les reçoit."""
    if not calls:
        return "_Aucun appel au LLM pour cette réponse._"
    lines = [f"{len(calls)} appel(s) au LLM pour cette réponse, dans l'ordre."]
    for i, call in enumerate(calls, start=1):
        lines.append(f"#### Appel {i} · {call['kind']}")
        for message in call["messages"]:
            content = message.get("content") or ""
            if not isinstance(content, str):
                content = str(content)
            lines.append(f"**{message.get('role', '?')}** · {len(content)} caractères")
            # Bloc de code : le texte s'affiche tel quel (pas de Markdown ni d'HTML interprétés)
            lines.append("````text\n" + content.replace("````", "'''") + "\n````")
    return "\n\n".join(lines)


def _run_in_thread(system: System, conversation: list[dict]) -> queue.Queue:
    """Calcule la réponse dans un fil dédié, qui enregistre les appels au LLM.

    Le fil envoie dans la file : ("token", texte)…, puis ("done", answer, appels)
    ou ("error", message, trace).
    """
    events: queue.Queue = queue.Queue()

    def work() -> None:
        calls = record_calls()
        try:
            answer = system.pipeline.answer(conversation)
            for token in answer:
                events.put(("token", token))
            events.put(("done", answer, calls))
        except Exception as e:  # noqa: BLE001
            events.put(("error", f"⚠ {type(e).__name__} : {e}", traceback.format_exc(limit=-3), calls))

    threading.Thread(target=work, daemon=True).start()
    return events


def _chat_tab(system: System) -> None:
    def respond(message: str, history: list[dict]):
        conversation = [
            {"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else str(m["content"])}
            for m in history
            if m.get("role") in {"user", "assistant"}
        ]
        conversation.append({"role": "user", "content": message})
        events = _run_in_thread(system, conversation)
        text = ""
        while True:
            event = events.get()
            if event[0] == "token":
                text += event[1]
                yield text, "_Génération en cours…_", "_Génération en cours…_"
            elif event[0] == "done":
                yield text, _trace_markdown(event[1]), _prompt_markdown(event[2])
                return
            else:
                yield event[1], f"```\n{event[2]}\n```", _prompt_markdown(event[3])
                return

    with gr.Row():
        with gr.Column(scale=3):
            details = gr.Markdown("_Les passages utilisés s'afficheront ici._", render=False)
            prompt = gr.Markdown("_Les messages envoyés au LLM s'afficheront ici._", render=False)
            gr.ChatInterface(
                respond, additional_outputs=[details, prompt], examples=EXAMPLES, run_examples_on_click=False
            )
        with gr.Column(scale=2):
            with gr.Tab("Trace et sources"):
                details.render()
            with gr.Tab("Prompt"):
                prompt.render()


# ─────────────────────────────────────────────────────────────────────────────
#  Évaluation
# ─────────────────────────────────────────────────────────────────────────────


def _question_text(question: Any) -> str:
    if len(question.turns) == 1:
        return question.question
    return f"{question.turns[0]} … → {question.question}"


def _row(question: Any, result: dict | None) -> list[str]:
    base = [question.id, question.category, _question_text(question), question.reference]
    if result is None:
        return ["…", *base, "", ""]
    mark = "✅" if result["ok"] else "❌"
    remark = "" if result["ok"] else result["reason"]
    if result.get("sources_ok") is False:
        remark = (remark + " · " if remark else "") + "documents attendus non retrouvés"
    return [mark, *base, result["answer"], remark]


def _summary(questions: list, results: dict[str, dict]) -> str:
    done = [results[q.id] for q in questions if q.id in results]
    score = sum(r["ok"] for r in done)
    lines = [f"### Score : {score}/{len(questions)}" + ("" if len(done) == len(questions) else f" ({len(done)} réponses reçues)")]
    parts = []
    for category in CATEGORIES:
        rows = [results[q.id] for q in questions if q.category == category and q.id in results]
        total = sum(1 for q in questions if q.category == category)
        if total:
            parts.append(f"{category} {sum(r['ok'] for r in rows)}/{total}")
    lines.append(" · ".join(parts))
    return "\n\n".join(lines)


def _eval_tab(system: System) -> None:
    def run(categories: list[str]):
        questions = [q for q in load_questions() if q.category in categories]
        if not questions:
            yield "_Aucune question sélectionnée._", []
            return
        pipeline = system.pipeline
        results: dict[str, dict] = {}
        yield _summary(questions, results), [_row(q, None) for q in questions]
        with ThreadPoolExecutor(max_workers=EVAL_WORKERS) as pool:
            futures = {pool.submit(evaluate, pipeline, q): q for q in questions}
            for future in as_completed(futures):
                question = futures[future]
                results[question.id] = future.result()
                yield _summary(questions, results), [_row(q, results.get(q.id)) for q in questions]
        path = save([results[q.id] for q in questions], "eval")
        yield _summary(questions, results) + f"\n\n_Résultats enregistrés dans {path}_", [
            _row(q, results[q.id]) for q in questions
        ]

    with gr.Row():
        categories = gr.CheckboxGroup(
            choices=list(CATEGORIES), value=list(CATEGORIES), label="Catégories", scale=4
        )
        start = gr.Button("Lancer l'évaluation", variant="primary", scale=1)
    summary = gr.Markdown("Le questionnaire compte 41 questions. Chaque réponse du système est notée "
                          "automatiquement et affichée à côté de la réponse attendue.")
    table = gr.Dataframe(headers=EVAL_COLUMNS, wrap=True, interactive=False,
                         column_widths=["4%", "5%", "9%", "20%", "20%", "28%", "14%"])
    start.click(run, inputs=categories, outputs=[summary, table])


# ─────────────────────────────────────────────────────────────────────────────
#  Index : passages d'un document, test de la recherche
# ─────────────────────────────────────────────────────────────────────────────


def _index_tab(system: System) -> None:
    def show_document(doc_id: str):
        chunks = [c for c in system.pipeline.index.chunks if c.doc_id == doc_id]
        rows = [[i, c.meta.get("section") or "", len(c.text), c.text] for i, c in enumerate(chunks)]
        return f"{len(chunks)} passages", rows

    def search(query: str):
        if not query.strip():
            return []
        hits = system.pipeline.search.find(query, 10)
        return [
            [i, f"{h.score:.4f}", " ".join(f"{k}={v:.3f}" for k, v in h.details.items()), h.chunk.id, h.chunk.text]
            for i, h in enumerate(hits, start=1)
        ]

    documents = [d.id for d in system.resources.documents]
    with gr.Row():
        with gr.Column():
            gr.Markdown("### Passages d'un document")
            doc = gr.Dropdown(documents, label="Document", value=None)
            count = gr.Markdown()
            chunks = gr.Dataframe(headers=["#", "section", "caractères", "texte"], wrap=True, interactive=False,
                                  column_widths=["6%", "24%", "10%", "60%"])
        with gr.Column():
            gr.Markdown("### Recherche (sans LLM)")
            query = gr.Textbox(label="Requête", placeholder="article 50 du règlement sur l'IA")
            hits = gr.Dataframe(headers=["#", "score", "détails", "passage", "texte"], wrap=True, interactive=False,
                                column_widths=["5%", "10%", "17%", "18%", "50%"])
    doc.change(show_document, inputs=doc, outputs=[count, chunks])
    query.submit(search, inputs=query, outputs=hits)


# ─────────────────────────────────────────────────────────────────────────────


def launch(port: int = 7860, share: bool = False) -> None:
    system = System()
    with gr.Blocks(title="Chatbot RAG") as demo:
        gr.Markdown("## Chatbot RAG — réglementation de l'IA en France")
        with gr.Row():
            status = gr.Markdown(system.status)
            reload = gr.Button("Recharger le code", scale=0)
        reload.click(system.reload, outputs=status)
        with gr.Tab("Chat"):
            _chat_tab(system)
        with gr.Tab("Évaluation"):
            _eval_tab(system)
        with gr.Tab("Index"):
            _index_tab(system)
    demo.launch(server_port=port, share=share)
