"""Chargement des documents du corpus.                                  [FOURNI]

Chaque fichier est lu sous deux formes :

- ``doc.raw_text`` : le texte « brut », tel que le renverrait un extracteur
  générique (en-têtes de page, menus et tableaux aplatis compris).
  C'est ce qu'utilise le pipeline naïf de la phase 1.

- ``doc.blocks`` : la structure du document, sous forme d'une liste de blocs
  ordonnés : titres (avec leur niveau), paragraphes et tableaux (avec leurs
  lignes et leur en-tête). C'est ce qu'utilisent les phases suivantes.

Formats pris en charge : PDF, HTML/XHTML, Markdown, DOCX, ODT, CSV, XLSX, JSON.
Vous n'avez pas besoin de modifier ce fichier pour le TP.
"""

from __future__ import annotations

import csv
import io
import json
import re
import tomllib
import warnings
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "corpus"
MANIFEST = ROOT / "data" / "corpus.toml"

SUPPORTED = {".pdf", ".html", ".htm", ".xhtml", ".md", ".docx", ".odt", ".csv", ".xlsx", ".json"}


# ─────────────────────────────────────────────────────────────────────────────
#  Modèle de données
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Block:
    """Un élément de structure d'un document."""

    kind: str  # "heading", "text" ou "table"
    text: str = ""  # contenu textuel (pour un tableau : lignes séparées par des retours)
    level: int = 0  # niveau de titre : 1 = titre principal, 2 = section, ...
    page: int | None = None  # numéro de page (PDF uniquement), à partir de 1
    rows: list[list[str]] | None = None  # tableau : rows[0] = en-tête, puis les lignes

    def __repr__(self) -> str:
        extra = f", level={self.level}" if self.kind == "heading" else ""
        extra += f", page={self.page}" if self.page else ""
        extra += f", rows={len(self.rows)}" if self.rows else ""
        preview = self.text[:60].replace("\n", " ")
        return f"Block({self.kind}{extra}, {preview!r})"


@dataclass
class Document:
    """Un document du corpus."""

    id: str  # chemin relatif dans data/corpus, ex. "cnil/guide-securite-donnees-personnelles.pdf"
    title: str
    format: str  # "pdf", "html", "md", "docx", "odt", "csv", "xlsx", "json"
    raw_text: str  # texte brut (phase 1)
    blocks: list[Block] = field(default_factory=list)  # structure (phases 2+)
    meta: dict[str, Any] = field(default_factory=dict)  # métadonnées du manifeste

    def __repr__(self) -> str:
        return (
            f"Document({self.id!r}, format={self.format}, "
            f"{len(self.raw_text):,} caractères, {len(self.blocks)} blocs)"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Point d'entrée
# ─────────────────────────────────────────────────────────────────────────────


def load_manifest(path: Path = MANIFEST) -> dict[str, dict[str, Any]]:
    """Métadonnées du manifeste, indexées par chemin relatif."""
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return {d["path"]: d for d in tomllib.load(f).get("documents", [])}


LOADER_VERSION = 6  # à incrémenter quand les parseurs changent (invalide le cache)
CACHE_FILE = ROOT / "index" / ".cache" / "documents.pkl"


def load_corpus(
    corpus_dir: Path = CORPUS_DIR, verbose: bool = False, use_cache: bool = True
) -> list[Document]:
    """Charge tous les documents de ``corpus_dir`` (récursivement).

    Les fichiers ajoutés à la main dans data/corpus/ sont aussi chargés :
    leur titre est alors déduit du nom de fichier. Le résultat est mis en cache
    (index/.cache/documents.pkl) : seuls les fichiers modifiés sont relus.
    """
    import pickle

    if not corpus_dir.exists() or not any(corpus_dir.iterdir()):
        raise FileNotFoundError(
            f"Corpus introuvable ({corpus_dir}). "
            "Lancez d'abord : python scripts/download_corpus.py"
        )
    manifest = load_manifest()
    cache: dict[str, Any] = {}
    if use_cache and CACHE_FILE.exists():
        try:
            cache = pickle.loads(CACHE_FILE.read_bytes())
        except Exception:  # noqa: BLE001 - cache corrompu ou d'une autre version
            cache = {}
    documents, fresh = [], {}
    for path in sorted(corpus_dir.rglob("*")):
        if path.suffix.lower() not in SUPPORTED or not path.is_file():
            continue
        rel = path.relative_to(corpus_dir).as_posix()
        meta = manifest.get(rel, {})
        stat = path.stat()
        key = (stat.st_size, stat.st_mtime_ns, LOADER_VERSION, repr(sorted(meta.items())))
        if rel in cache and cache[rel][0] == key:
            doc = cache[rel][1]
        else:
            if verbose:
                print(f"  lecture de {rel} …", flush=True)
            try:
                doc = load_document(path, meta, doc_id=rel)
            except Exception as e:  # noqa: BLE001 - un document illisible ne bloque pas le TP
                warnings.warn(f"Impossible de lire {rel} : {e}", stacklevel=2)
                continue
        fresh[rel] = (key, doc)
        documents.append(doc)
    if use_cache and fresh != cache:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_bytes(pickle.dumps(fresh))
    return documents


def load_document(path: Path, meta: dict[str, Any] | None = None, doc_id: str | None = None) -> Document:
    """Charge un fichier en ``Document`` (texte brut + blocs structurés)."""
    meta = dict(meta or {})
    suffix = path.suffix.lower()
    loader = {
        ".pdf": _load_pdf,
        ".html": _load_html,
        ".htm": _load_html,
        ".xhtml": _load_html,
        ".md": _load_markdown,
        ".docx": _load_docx,
        ".odt": _load_odt,
        ".csv": _load_csv,
        ".xlsx": _load_xlsx,
        ".json": _load_json,
    }[suffix]
    raw_text, blocks = loader(path)
    blocks = [b for b in blocks if b.text.strip() or b.rows]
    title = meta.get("title") or path.stem.replace("-", " ").replace("_", " ")
    return Document(
        id=doc_id or path.name,
        title=title,
        format={".htm": "html", ".xhtml": "html"}.get(suffix, suffix.lstrip(".")),
        raw_text=_clean_raw(raw_text),
        blocks=blocks,
        meta={k: v for k, v in meta.items() if k not in {"sha256", "headers", "path"}},
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Utilitaires
# ─────────────────────────────────────────────────────────────────────────────

_SPACES = re.compile(r"\s+")


def clean(text: str) -> str:
    """Normalise les espaces (insécables et retours à la ligne compris)."""
    text = text.replace("­", "").replace("​", "")  # tiret conditionnel, espace nulle
    return _SPACES.sub(" ", text).strip()


def _clean_raw(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("­", "")
    text = re.sub(r"[ \t  ]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _cell(value: Any) -> str:
    """Formate une valeur de cellule (nombres sans « .0 » superflu)."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.6g}"
    return clean(str(value))


def render_rows(rows: list[list[str]]) -> str:
    """Rendu texte simple d'un tableau : une ligne par rangée, cellules séparées par « | »."""
    return "\n".join(" | ".join(c for c in row) for row in rows)


def _table_block(rows: list[list[str]], page: int | None = None) -> Block | None:
    rows = [[clean(c) for c in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return None
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    # Supprime les colonnes entièrement vides
    keep = [j for j in range(width) if any(r[j] for r in rows)]
    rows = [[r[j] for j in keep] for r in rows]
    if len(keep) <= 1:  # tableau de mise en page : ce n'est pas un vrai tableau
        return Block("text", "\n".join(r[0] for r in rows if r and r[0]), page=page)
    return Block("table", render_rows(rows), page=page, rows=rows)


# Titres « déguisés » en paragraphes (DOCX, ODT, PDF) : « Article 3 : ... », « TITRE II ... »
_PSEUDO_HEADING = re.compile(
    r"^(article|titre|chapitre|section|annexe|partie|fiche)\s+([0-9ivxlc]+|premier|unique)\b",
    re.IGNORECASE,
)


def _pseudo_heading_level(text: str) -> int | None:
    if len(text) > 120 or not _PSEUDO_HEADING.match(text):
        return None
    word = text.split()[0].lower()
    return {"titre": 2, "partie": 2, "chapitre": 2, "annexe": 2, "fiche": 2}.get(word, 3)


# ─────────────────────────────────────────────────────────────────────────────
#  PDF
# ─────────────────────────────────────────────────────────────────────────────


def _pdf_tables(page: Any) -> list[tuple[Any, list[list[str]]]]:
    """Tableaux détectés par PyMuPDF sur une page : [(rectangle, lignes)]."""
    import pymupdf

    # La détection est coûteuse : on ne la lance que sur les pages comportant des traits
    segments = sum(1 for d in page.get_drawings() for item in d["items"] if item[0] in ("l", "re"))
    if segments < 4:
        return []
    found = []
    try:
        for table in page.find_tables().tables:
            rows = [[c or "" for c in row] for row in table.extract()]
            filled = [r for r in rows if sum(1 for c in r if c and c.strip()) >= 2]
            # Extraction ratée (mots collés « Déterminerlerégime » ou lettres entrelacées) :
            # les mots du tableau doivent se retrouver dans le texte de la page, sinon on
            # garde le texte ligne à ligne.
            page_words = set(re.findall(r"\w+", page.get_text().lower()))
            table_words = re.findall(r"\w{4,}", " ".join(c for r in rows for c in r).lower())
            found_ratio = sum(w in page_words for w in table_words) / max(1, len(table_words))
            if len(filled) >= 2 and found_ratio >= 0.85:
                found.append((pymupdf.Rect(table.bbox), rows))
    except Exception:  # noqa: BLE001 - la détection de tableaux est une aide, pas une nécessité
        pass
    return found


def _load_pdf(path: Path) -> tuple[str, list[Block]]:
    import pymupdf

    pdf = pymupdf.open(path)
    raw_pages = [page.get_text() for page in pdf]

    # 1) Lignes avec taille de police et graisse ; les lignes situées dans un tableau
    #    sont remplacées par le tableau lui-même (marqueur ("\x00table", index)).
    pages: list[list[tuple[str, float, bool]]] = []
    page_tables: list[list[list[list[str]]]] = []
    sizes: Counter[float] = Counter()
    for page in pdf:
        tables = _pdf_tables(page)
        page_tables.append([rows for _, rows in tables])
        emitted: set[int] = set()
        lines = []
        for block in page.get_text("dict", sort=True)["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                x0, y0, x1, y1 = line["bbox"]
                center = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
                inside = next((i for i, (rect, _) in enumerate(tables) if center in rect), None)
                if inside is not None:
                    if inside not in emitted:
                        emitted.add(inside)
                        lines.append(("", 0.0, False))
                        lines.append((f"\x00table{inside}", 0.0, False))
                    continue
                text = clean("".join(s["text"] for s in line["spans"]))
                size = round(max(s["size"] for s in spans), 1)
                bold = all(s["flags"] & 16 or "Bold" in s["font"] for s in spans)
                lines.append((text, size, bold))
                sizes[size] += len(text)
            lines.append(("", 0.0, False))  # fin de bloc = fin de paragraphe
        lines.extend((f"\x00table{i}", 0.0, False) for i in range(len(tables)) if i not in emitted)
        pages.append(lines)
    body = sizes.most_common(1)[0][0] if sizes else 10.0

    # 2) En-têtes et pieds de page : lignes répétées sur une grande partie des pages
    repeated: set[str] = set()
    if len(pages) >= 4:
        seen: Counter[str] = Counter()
        for lines in pages:
            for t in {t for t, _, _ in lines if t}:
                seen[re.sub(r"\d+", "#", t)] += 1
        repeated = {t for t, n in seen.items() if n >= max(3, 0.4 * len(pages))}

    # 3) Niveaux de titre : tailles nettement supérieures au corps du texte
    heading_sizes = sorted(
        {s for s, n in sizes.items() if s >= body * 1.18 and n >= 3}, reverse=True
    )[:4]
    level_of = {s: i + 1 for i, s in enumerate(heading_sizes)}

    blocks: list[Block] = []
    for pno, lines in enumerate(pages, start=1):
        paragraph: list[str] = []
        heading: list[str] = []
        heading_level = 0

        def flush_paragraph() -> None:
            if paragraph:
                text = _join_lines(paragraph)
                level = _pseudo_heading_level(text)
                blocks.append(Block("heading", text, level=level, page=pno) if level else Block("text", text, page=pno))
                paragraph.clear()

        def flush_heading() -> None:
            nonlocal heading_level
            if heading:
                text = _join_lines(heading)
                previous = blocks[-1] if blocks else None
                if (
                    previous is not None
                    and previous.kind == "heading"
                    and previous.level == heading_level
                    and previous.page == pno
                    and len(previous.text) + len(text) < 120
                    and not previous.text.endswith((".", ":", "?", "!"))
                ):
                    previous.text += " " + text  # titre coupé sur deux blocs
                else:
                    blocks.append(Block("heading", text, level=heading_level, page=pno))
                heading.clear()
                heading_level = 0

        for text, size, bold in lines:
            if not text:
                flush_heading()
                flush_paragraph()
                continue
            if text.startswith("\x00table"):
                flush_heading()
                flush_paragraph()
                if b := _table_block(page_tables[pno - 1][int(text[6:])], page=pno):
                    blocks.append(b)
                continue
            if re.sub(r"\d+", "#", text) in repeated or re.fullmatch(r"[\d\s/|.-]+", text):
                continue  # en-tête, pied de page ou numéro de page
            level = level_of.get(size)
            if level and len(text) < 160:
                flush_paragraph()
                if heading and level != heading_level:
                    flush_heading()
                heading.append(text)
                heading_level = level
            else:
                flush_heading()
                paragraph.append(text)
        flush_heading()
        flush_paragraph()
    return "\n".join(raw_pages), blocks


def _join_lines(lines: list[str]) -> str:
    """Recolle des lignes de PDF en gérant les césures."""
    out = ""
    for line in lines:
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line
        elif out:
            out += " " + line
        else:
            out = line
    return clean(out)


# ─────────────────────────────────────────────────────────────────────────────
#  HTML
# ─────────────────────────────────────────────────────────────────────────────

_INLINE = {
    "a", "abbr", "b", "bdi", "br", "cite", "code", "data", "dfn", "em", "i", "kbd", "mark",
    "q", "s", "samp", "small", "span", "strong", "sub", "sup", "time", "u", "var", "wbr",
    "font", "img", "label",
}
_TEXT_BLOCKS = {"p", "dd", "dt", "blockquote", "pre", "figcaption", "caption", "address", "summary"}
_DROP = {
    "script", "style", "noscript", "template", "svg", "canvas", "iframe", "button", "form",
    "input", "select", "textarea", "nav", "link", "meta", "head",
}


def _load_html(path: Path) -> tuple[str, list[Block]]:
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    html = path.read_bytes().decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    raw_text = soup.get_text("\n")

    if soup.select_one("p.oj-normal, p.oj-ti-art"):
        return raw_text, _eurlex_oj_blocks(soup)
    if soup.select_one("p.Titrearticle, p.ManualHeading1"):
        return raw_text, _eurlex_com_blocks(soup)
    if soup.find("meta", property="mw:pageId") or soup.select_one("[data-mw-section-id]"):
        root = _wikipedia_root(soup)
    else:
        root = _main_content(soup)
    return raw_text, _html_blocks(root)


def _main_content(soup: Any) -> Any:
    """Zone de contenu principal d'une page web (sans menus, en-tête, pied de page)."""
    for selector in ["div#consulter", "main", "article", "div#content", "div#main", "div.content"]:
        if (node := soup.select_one(selector)) and len(node.get_text(strip=True)) > 500:
            root = node
            break
    else:
        root = soup.body or soup
    for tag in root.find_all(["nav", "header", "footer", "aside", "form", "button"]):
        tag.decompose()
    for tag in root.find_all(class_=re.compile(r"breadcrumb|share|social|cookie|skip|menu|pager|visually-hidden|sr-only", re.I)):
        tag.decompose()
    return root


def _wikipedia_root(soup: Any) -> Any:
    root = soup.body or soup
    selectors = [
        "sup.reference", "sup.mw-ref", ".mw-ref", ".reference", ".mw-references-wrap",
        "ol.references", ".navbox", ".navbox-container", ".bandeau-container", ".bandeau-portail",
        ".homonymie", ".metadata", ".noprint", ".mw-editsection", ".printfooter", "figure",
        ".gallery", ".mw-empty-elt", ".ouvrage", ".autres-projets", ".mbox-small",
    ]
    for tag in root.select(", ".join(selectors)):
        tag.decompose()
    # Sections bibliographiques : peu utiles pour répondre à des questions
    for heading in root.find_all(["h2", "h3"]):
        if re.match(r"(notes|références|voir aussi|liens externes|bibliographie|articles connexes)",
                    heading.get_text(strip=True), re.I):
            section = heading.find_parent("section")
            if section is not None:
                section.decompose()
    return root


def _html_blocks(root: Any) -> list[Block]:
    from bs4 import NavigableString, Tag

    blocks: list[Block] = []
    inline: list[str] = []

    def flush() -> None:
        text = clean(" ".join(inline))
        inline.clear()
        if text:
            blocks.append(Block("text", text))

    def walk(node: Any) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in {"Comment", "Doctype", "CData", "ProcessingInstruction"}:
                    continue
                if str(child).strip():
                    inline.append(str(child))
                continue
            if not isinstance(child, Tag) or child.name in _DROP:
                continue
            name = child.name
            if name in _INLINE:
                inline.append(child.get_text(" "))
            elif re.fullmatch(r"h[1-6]", name):
                flush()
                if text := clean(child.get_text(" ")):
                    blocks.append(Block("heading", text, level=int(name[1])))
            elif name == "table":
                flush()
                rows = [
                    [cell.get_text(" ") for cell in tr.find_all(["th", "td"], recursive=False)]
                    for tr in child.find_all("tr")
                    if tr.find_parent("table") is child
                ]
                if block := _table_block(rows):
                    blocks.append(block)
            elif name in {"ul", "ol"}:
                flush()
                for li in child.find_all("li", recursive=False):
                    nested = [n.extract() for n in li.find_all(["ul", "ol"], recursive=False)]
                    if text := clean(li.get_text(" ")):
                        blocks.append(Block("text", "- " + text))
                    for sub in nested:
                        wrapper = Tag(name="div")
                        wrapper.append(sub)
                        walk(wrapper)
            elif name in _TEXT_BLOCKS or name == "li":
                flush()
                if text := clean(child.get_text(" ")):
                    blocks.append(Block("text", text))
            else:
                flush()
                walk(child)
        flush()

    walk(root)
    return blocks


def _eurlex_oj_blocks(soup: Any) -> list[Block]:
    """Règlements publiés au Journal officiel de l'UE (XHTML « oj-* »)."""
    from bs4 import Tag

    blocks: list[Block] = []
    for note in soup.select("p.oj-note, span.oj-note-tag, hr"):
        note.decompose()
    seen_title = False
    seen_recitals = False
    pending: dict[str, str] = {}

    def add_heading(text: str, level: int) -> None:
        if text := clean(text):
            blocks.append(Block("heading", text, level=level))

    def enumeration(table: Any) -> None:
        """Tableaux « a) texte » utilisés pour les énumérations et les considérants."""
        tr = table.find("tr")
        cells = tr.find_all("td", recursive=False) if tr else []
        if len(cells) == 2 and len(cells[0].get_text(strip=True)) <= 8:
            label = clean(cells[0].get_text(" "))
            first = True
            for child in cells[1].children:
                if not isinstance(child, Tag):
                    continue
                if child.name == "table":
                    enumeration(child)
                elif text := clean(child.get_text(" ")):
                    blocks.append(Block("text", f"{label} {text}" if first else text))
                    first = False
            return
        rows = [[c.get_text(" ") for c in row.find_all(["td", "th"], recursive=False)] for row in table.find_all("tr")]
        if block := _table_block(rows):
            blocks.append(block)

    def walk(node: Any) -> None:
        nonlocal seen_title, seen_recitals
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            classes = child.get("class") or []
            if child.name == "div" and str(child.get("id", "")).startswith("rct_") and not seen_recitals:
                seen_recitals = True
                add_heading("Considérants", 2)
            if child.name == "table":
                enumeration(child)
            elif child.name == "p":
                text = child.get_text(" ")
                if "oj-doc-ti" in classes:
                    pending.setdefault("doc", "")
                    pending["doc"] += " " + text
                    continue
                if "doc" in pending:
                    add_heading(pending.pop("doc"), 2 if seen_title else 1)
                    seen_title = True
                if "oj-ti-section-1" in classes:
                    pending["section"] = text
                elif "oj-ti-section-2" in classes:
                    head = pending.pop("section", "")
                    level = 3 if head.strip().upper().startswith("SECTION") else 2
                    add_heading(f"{clean(head)} — {clean(text)}" if head else text, level)
                elif "oj-ti-art" in classes:
                    pending["article"] = text
                elif "oj-sti-art" in classes:
                    add_heading(f"{clean(pending.pop('article', ''))} — {clean(text)}", 4)
                elif "oj-ti-grseq-1" in classes:
                    add_heading(text, 3)
                else:
                    if "article" in pending:  # article sans titre
                        add_heading(pending.pop("article"), 4)
                    if t := clean(text):
                        blocks.append(Block("text", t))
            else:
                walk(child)

    walk(soup.body or soup)
    if "doc" in pending:
        add_heading(pending.pop("doc"), 2 if seen_title else 1)
    return blocks


def _eurlex_com_blocks(soup: Any) -> list[Block]:
    """Documents de la Commission (propositions « COM ») convertis depuis Word."""
    for tag in soup.select("a.footnoteRef, span.FootnoteReference, a.footnote, div.footnote, p.footnote"):
        tag.decompose()
    levels = {
        "Typedudocument": 1, "Titreobjet": 1, "Exposdesmotifstitre": 2,
        "ManualHeading1": 2, "ManualHeading2": 3, "ManualHeading3": 4,
        "SectionTitle": 2, "Titrearticle": 4, "ChapterTitle": 2,
    }
    blocks: list[Block] = []
    title_parts: list[str] = []
    for p in (soup.body or soup).find_all("p"):
        classes = p.get("class") or []
        text = clean(p.get_text(" "))
        if not text:
            continue
        if any(c.endswith("_cp") for c in classes):
            continue  # page de garde
        level = next((levels[c] for c in classes if c in levels), None)
        if level == 1:
            title_parts.append(text)
            continue
        if title_parts:
            blocks.append(Block("heading", " — ".join(title_parts), level=1))
            title_parts.clear()
        if level:
            if "SectionTitle" in classes and text.upper().startswith(("CHAPITRE", "SECTION")):
                level = 3
            blocks.append(Block("heading", text, level=level))
        else:
            blocks.append(Block("text", text))
    return blocks


# ─────────────────────────────────────────────────────────────────────────────
#  Markdown
# ─────────────────────────────────────────────────────────────────────────────


def _load_markdown(path: Path) -> tuple[str, list[Block]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)  # front matter YAML
    blocks: list[Block] = []
    paragraph: list[str] = []
    table: list[list[str]] = []
    in_code = False

    def flush() -> None:
        if paragraph:
            blocks.append(Block("text", _md_inline(" ".join(paragraph))))
            paragraph.clear()
        if table:
            if b := _table_block(table):
                blocks.append(b)
            table.clear()

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            flush()
            continue
        if in_code:
            paragraph.append(line)
            continue
        if m := re.match(r"^(#{1,6})\s+(.*)", stripped):
            flush()
            blocks.append(Block("heading", _md_inline(m.group(2)), level=len(m.group(1))))
        elif stripped.startswith("|"):
            if paragraph:
                blocks.append(Block("text", _md_inline(" ".join(paragraph))))
                paragraph.clear()
            if not re.fullmatch(r"\|?[\s:|-]+\|?", stripped):  # ligne de séparation
                table.append([c.strip() for c in stripped.strip("|").split("|")])
        elif re.match(r"^([-*+]|\d+[.)])\s+", stripped):
            flush()
            blocks.append(Block("text", "- " + _md_inline(re.sub(r"^([-*+]|\d+[.)])\s+", "", stripped))))
        elif not stripped or stripped.startswith(":::") or stripped.startswith("<"):
            flush()
        else:
            if blocks and not paragraph and blocks[-1].text.startswith("- ") and line.startswith("  "):
                blocks[-1].text += " " + _md_inline(stripped)  # suite d'un élément de liste
            else:
                paragraph.append(stripped)
    flush()
    return text, blocks


def _md_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)  # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # liens
    text = re.sub(r"(\*\*|__|\*|_|`)(.+?)\1", r"\2", text)  # emphase, code
    return clean(text)


# ─────────────────────────────────────────────────────────────────────────────
#  DOCX et ODT
# ─────────────────────────────────────────────────────────────────────────────


def _load_docx(path: Path) -> tuple[str, list[Block]]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(path))
    raw_text = "\n".join(p.text for p in document.paragraphs)  # ignore les tableaux
    blocks: list[Block] = []
    for element in document.element.body.iterchildren():
        tag = element.tag.split("}")[-1]
        if tag == "tbl":
            table = Table(element, document)
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            if b := _table_block(rows):
                blocks.append(b)
            continue
        if tag != "p":
            continue
        paragraph = Paragraph(element, document)
        text = clean(paragraph.text)
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        if m := re.match(r"(heading|titre)\s*(\d)", style, re.I):
            blocks.append(Block("heading", text, level=int(m.group(2)) + 1))
        elif style.lower() in {"title", "titre"}:
            blocks.append(Block("heading", text, level=1))
        elif level := _pseudo_heading_level(text):
            blocks.append(Block("heading", text, level=level))
        elif "list" in style.lower() or "liste" in style.lower():
            blocks.append(Block("text", "- " + text))
        elif blocks and blocks[-1].kind == "text" and text[:1].islower():
            blocks[-1].text += " " + text  # paragraphe coupé (document issu d'un PDF)
        else:
            blocks.append(Block("text", text))
    return raw_text, blocks


_ODF = {
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}


def _load_odt(path: Path) -> tuple[str, list[Block]]:
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("content.xml"))
    body = root.find(".//office:text", _ODF)
    blocks: list[Block] = []
    t = "{%s}" % _ODF["text"]
    tb = "{%s}" % _ODF["table"]

    def text_of(el: Any) -> str:
        parts = []
        for node in el.iter():
            if node.tag == t + "s":
                parts.append(" ")
            elif node.tag in {t + "tab", t + "line-break"}:
                parts.append(" ")
            if node.text and node.tag != t + "note-citation":
                parts.append(node.text)
            if node.tail and node is not el:
                parts.append(node.tail)
        return clean("".join(parts))

    def walk(el: Any) -> None:
        for child in el:
            if child.tag == t + "h":
                level = int(child.get(t + "outline-level", "1"))
                if text := text_of(child):
                    blocks.append(Block("heading", text, level=min(level, 6)))
            elif child.tag == t + "p":
                if text := text_of(child):
                    level = _pseudo_heading_level(text)
                    blocks.append(Block("heading", text, level=level) if level else Block("text", text))
            elif child.tag == t + "list":
                for item in child.iter(t + "list-item"):
                    for p in item.findall(t + "p"):
                        if text := text_of(p):
                            blocks.append(Block("text", "- " + text))
            elif child.tag == tb + "table":
                rows = [
                    [text_of(cell) for cell in row.findall(tb + "table-cell")]
                    for row in child.iter(tb + "table-row")
                ]
                if b := _table_block(rows):
                    blocks.append(b)
            elif child.tag in {t + "section", t + "soft-page-break"} or len(child):
                walk(child)

    if body is not None:
        walk(body)
    raw_text = "\n".join(b.text for b in blocks)
    return raw_text, blocks


# ─────────────────────────────────────────────────────────────────────────────
#  Données tabulaires : CSV, XLSX, JSON
# ─────────────────────────────────────────────────────────────────────────────


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _load_csv(path: Path) -> tuple[str, list[Block]]:
    text = _decode(path.read_bytes())
    try:
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if text.count(";") > text.count(",") else ","
    # newline="" : laisse le module csv gérer les retours à la ligne (\r, \n, \r\n),
    # y compris ceux qui apparaissent à l'intérieur de cellules entre guillemets.
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows = [row for row in reader if any(c.strip() for c in row)]
    blocks = []
    if b := _table_block(rows):
        blocks.append(b)
    return text, blocks


def load_table_rows(path: Path) -> list[tuple[str, list[list[str]]]]:
    """Tableaux d'un fichier de données (CSV, XLSX, JSON), sous forme [(nom, lignes)].

    Utilisé par la phase 4 pour charger les données dans une base SQL.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        blocks = _load_csv(path)[1]
        return [(path.stem, b.rows) for b in blocks if b.rows]
    if suffix == ".xlsx":
        return [(name, rows) for name, rows in _xlsx_tables(path)]
    if suffix == ".json":
        blocks = _load_json(path)[1]
        return [(path.stem, b.rows) for b in blocks if b.rows]
    return []


def _xlsx_tables(path: Path) -> list[tuple[str, list[list[str]]]]:
    """Un tableau par feuille, avec en-têtes multi-lignes fusionnés (« France 2025 »)."""
    out = []
    for name, rows, _title, _notes in _xlsx_sheets(path):
        if rows:
            out.append((name, rows))
    return out


def _xlsx_sheets(path: Path) -> list[tuple[str, list[list[str]], list[str], list[str]]]:
    import openpyxl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for sheet in workbook.worksheets:
        raw = [[_cell(v) for v in row] for row in sheet.iter_rows(values_only=True)]
        raw = [row for row in raw if any(row)]
        width = max((len(r) for r in raw), default=0)
        raw = [r + [""] * (width - len(r)) for r in raw]
        filled = [sum(1 for c in r if c) for r in raw]
        # Titres au début, notes (« Lecture : », « Source : »...) à la fin : une seule cellule
        start = 0
        while start < len(raw) and filled[start] <= 1:
            start += 1
        end = len(raw)
        while end > start and filled[end - 1] <= 1:
            end -= 1
        titles = [next(c for c in r if c) for r in raw[:start]]
        notes = [next(c for c in r if c) for r in raw[end:]]
        region = raw[start:end]
        if not region:
            sheets.append((sheet.title, [], titles, notes))
            continue
        # Largeur utile : dernière colonne contenant une valeur (les feuilles mises en
        # forme déclarent souvent des centaines de colonnes vides)
        width = max((max((j for j, c in enumerate(r) if c), default=0) for r in region), default=0) + 1
        region = [r[:width] for r in region]

        def is_number(c: str) -> bool:
            return bool(re.fullmatch(r"-?[\d\s]+([.,]\d+)?|s|nd|ns|n\.s\.|-", c.strip()))

        # En-tête : lignes jusqu'à la première ligne « libellé + valeurs numériques »,
        # ou jusqu'à une ligne de regroupement (seule la première cellule est remplie)
        n_header = 0
        for row in region:
            values = [c for c in row[1:] if c]
            if row[0] and values and sum(is_number(c) for c in values) >= max(1, len(values) // 2):
                break
            if n_header and row[0] and not values:
                break
            n_header += 1
        n_header = max(1, min(n_header, 4))
        header_rows = region[:n_header]
        header = []
        for j in range(width):
            parts = []
            for hr in header_rows:
                # Cellules fusionnées : on propage la dernière valeur vers la droite
                value = hr[j]
                if not value and j > 0 and hr is not header_rows[-1]:
                    k = j
                    while k > 0 and not hr[k]:
                        k -= 1
                    value = hr[k] if k > 0 else ""
                if value and value not in parts:
                    parts.append(value)
            header.append(" ".join(parts))
        rows = [header]
        group = ""
        for row in region[n_header:]:
            if row[0] and not any(row[1:]):
                group = row[0]  # ligne de regroupement (« Taille de l'entreprise »)
                continue
            label = f"{group} — {row[0]}" if group and row[0] else row[0]
            rows.append([label, *row[1:]])
        sheets.append((sheet.title, rows, titles, notes))
    return sheets


def _load_xlsx(path: Path) -> tuple[str, list[Block]]:
    import openpyxl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    raw_lines = []
    for sheet in workbook.worksheets:
        raw_lines.append(sheet.title)
        for row in sheet.iter_rows(values_only=True):
            if any(v is not None for v in row):
                raw_lines.append("\t".join(_cell(v) for v in row))
    blocks: list[Block] = []
    for name, rows, titles, notes in _xlsx_sheets(path):
        if not titles:
            heading = name
        elif name.lower() in titles[0].lower():
            heading = titles[0]  # « Figure 1 – Part des entreprises… »
        else:
            heading = f"{name} — {titles[0]}"
        blocks.append(Block("heading", heading, level=2))
        blocks.extend(Block("text", t) for t in titles[1:])
        if rows and (b := _table_block(rows)):
            blocks.append(b)
        blocks.extend(Block("text", n) for n in notes)
    return "\n".join(raw_lines), blocks


def _flatten(value: Any, prefix: str = "") -> dict[str, str]:
    """Aplatit un objet JSON imbriqué : {"a": {"b": 1}} -> {"a.b": "1"}."""
    if isinstance(value, dict):
        out: dict[str, str] = {}
        for k, v in value.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(value, list):
        if all(not isinstance(v, (dict, list)) for v in value):
            return {prefix: ", ".join(_cell(v) for v in value)}
        return {prefix: json.dumps(value, ensure_ascii=False)}
    return {prefix: _cell(value) if not isinstance(value, bool) else ("oui" if value else "non")}


def _records(data: Any) -> list[dict[str, Any]] | None:
    """Trouve la principale collection d'enregistrements d'un document JSON."""
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        return data
    if isinstance(data, dict):
        values = list(data.values())
        if len(values) >= 3 and all(isinstance(v, dict) for v in values):
            return [{"id": k, **v} for k, v in data.items()]
        candidates = [v for v in values if isinstance(v, (list, dict))]
        for candidate in sorted(candidates, key=len, reverse=True):
            if (records := _records(candidate)) and len(records) >= 3:
                return records
    return None


def _load_json(path: Path) -> tuple[str, list[Block]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    data = json.loads(text)
    records = _records(data)
    if not records:
        flat = _flatten(data)
        return text, [Block("text", f"{k} : {v}") for k, v in flat.items()]
    flat_records = [_flatten(r) for r in records]
    columns: list[str] = []
    for r in flat_records:
        columns.extend(k for k in r if k not in columns)
    rows = [columns] + [[r.get(c, "") for c in columns] for r in flat_records]
    block = _table_block(rows)
    return text, [block] if block else []


# ─────────────────────────────────────────────────────────────────────────────
#  Aperçu en ligne de commande : python -m rag.documents <fichier>
# ─────────────────────────────────────────────────────────────────────────────


def _preview(paths: Iterable[str]) -> None:
    manifest = load_manifest()
    for p in paths:
        path = Path(p)
        rel = path.resolve().relative_to(CORPUS_DIR).as_posix() if path.resolve().is_relative_to(CORPUS_DIR) else path.name
        doc = load_document(path, manifest.get(rel), doc_id=rel)
        print(doc)
        for block in doc.blocks[:60]:
            indent = "  " * (block.level if block.kind == "heading" else 4)
            print(f"{indent}{block!r}")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    _preview(sys.argv[1:])
