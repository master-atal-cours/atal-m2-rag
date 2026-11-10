"""Construit la présentation statique (docs/index.html) à partir des slides de ce dossier.

    python md/build.py

md/deck.json donne l'ordre des slides, md/slides/*.html leur contenu,
md/notes.md les notes de l'orateur (listes à puces) et md/assets/ les images.
Le résultat, dans docs/, est publié par GitHub Pages.

La page vient de md/template.html. Dans la présentation : flèches, espace ou glissement
pour avancer ; N affiche les notes ; P ouvre la vue présentateur (slide courante, suivante,
notes, chronomètre) dans une autre fenêtre, synchronisée ; F passe en plein écran.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "docs"

# Images de la présentation : identifiant dans les slides -> fichier de md/assets/
ASSETS = {
    "/_blob/14521be99e5b10b51db422624c0f7c6c": "assets/logo-bee4win.png",
    "/_blob/8a34cbbf67a84a6721606a6e971aadfc": "assets/logo-universite-de-nantes.png",
}
# Icônes des slides -> icônes Phosphor (https://phosphoricons.com)
ICONS = {
    "Lock": "lock", "Search": "magnifying-glass", "Clock": "clock", "Wrench": "wrench", "Warning": "warning",
    "Users": "users", "Tool": "toolbox", "Key": "key", "Database": "database", "Code": "code", "Chart": "chart-bar",
}

def icon(match: re.Match) -> str:
    name, style = match.group(1), match.group(2)
    size = re.search(r"width:\s*(\d+)px", style)
    font = f"font-size:{size.group(1)}px" if size else "font-size:48px"
    return f'<x-icon style="{style}"><i class="ph ph-{ICONS.get(name, "circle")}" style="{font}"></i></x-icon>'


def read_notes() -> dict[str, list[tuple[int, str]]]:
    """md/notes.md : une section « ## id-de-la-slide » par slide, puis des puces « - » (deux niveaux)."""
    notes: dict[str, list[tuple[int, str]]] = {}
    path = HERE / "notes.md"
    if not path.exists():
        return notes
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = notes.setdefault(line[3:].strip(), [])
        elif current is not None and (m := re.match(r"^(\s*)[-*] (.+)$", line)):
            current.append((1 if len(m.group(1)) >= 2 else 0, m.group(2).strip()))
        elif current is not None and line.strip() and current:  # suite d'une puce sur plusieurs lignes
            level, text = current[-1]
            current[-1] = (level, text + " " + line.strip())
    return notes


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def notes_html(items: list[tuple[int, str]]) -> str:
    """Liste à puces imbriquée (deux niveaux)."""
    out, depth = ["<ul>"], 0
    for level, text in items:
        if level > depth:
            out[-1] = out[-1].removesuffix("</li>")
            out.append("<ul>")
        elif level < depth:
            out.append("</ul></li>")
        out.append(f"<li>{inline(text)}</li>")
        depth = level
    if depth:
        out.append("</ul></li>")
    out.append("</ul>")
    return "".join(out)


def main() -> None:
    deck = json.loads((HERE / "deck.json").read_text(encoding="utf-8"))
    notes = read_notes()
    parts = []
    for i, slide_id in enumerate(deck["order"], start=1):
        source = (HERE / "slides" / f"{slide_id}.html").read_text(encoding="utf-8")
        for blob, path in ASSETS.items():
            source = source.replace(blob, path)
        source = re.sub(r'<x-icon name="(\w+)" style="([^"]*)"></x-icon>', icon, source)
        if slide_id in notes:  # notes structurées de notes.md, à la place des notes en texte brut
            start, end = source.find("<aside>"), source.find("</aside>")
            source = source[:start] + f"<aside>{notes_html(notes[slide_id])}" + source[end:]
        parts.append(f'<div class="slide" data-index="{i}">\n{source.strip()}\n</div>')
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    for path in ASSETS.values():
        shutil.copy(HERE / path, OUT / path)
    title = html.escape("Retrieval-Augmented Generation (RAG) — M2 ATAL 2026")
    page = (HERE / "template.html").read_text(encoding="utf-8")
    page = page.replace("<!--TITLE-->", title).replace("<!--SLIDES-->", "\n".join(parts))
    (OUT / "index.html").write_text(page, encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"{len(parts)} slides -> {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
