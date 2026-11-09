"""Base SQL construite à partir des données tabulaires du corpus.        [FOURNI]

Utilisée en phase 4 : les questions d'agrégation (« combien de... », « quel
total... », « quel est le plus grand... ») ne se traitent pas par recherche de
passages, mais par une requête SQL sur les données.

    store = TableStore(load_corpus())
    print(store.schema())                       # description des tables pour le LLM
    columns, rows = store.query('SELECT COUNT(*) FROM cnil_controles_2025')

Tables chargées :
- chaque fichier CSV et JSON, chaque feuille XLSX ;
- les tableaux des pages HTML marquées ``sql = true`` dans data/corpus.toml ;
  ceux qui partagent le même en-tête (ex. un tableau par année) sont fusionnés,
  avec une colonne « section » indiquant le titre sous lequel ils apparaissaient.
Un document marqué ``sql = false`` dans le manifeste est ignoré.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .documents import Block, Document
from .text import normalize


@dataclass
class Table:
    name: str  # nom SQL
    doc_id: str
    title: str  # description lisible (titre du document, feuille...)
    columns: list[str]  # noms SQL
    labels: list[str]  # en-têtes d'origine
    rows: int = 0
    examples: list[tuple[Any, ...]] = field(default_factory=list)  # les lignes (pour décrire les valeurs)


class SQLError(RuntimeError):
    """Requête refusée ou invalide."""


def slug(text: str, max_length: int = 40) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", normalize(text)).strip("_")
    return value[:max_length].rstrip("_") or "col"


def _column_name(label: str, used: set[str]) -> str:
    base = slug(label)
    if re.fullmatch(r"(19|20)\d\d", base):
        base = f"annee_{base}"
    elif base[0].isdigit():
        base = f"c_{base}"
    name, i = base, 2
    while name in used:
        name, i = f"{base}_{i}", i + 1
    used.add(name)
    return name


def _value(text: str) -> Any:
    """Convertit « 1 234,5 », « 58 », « 12 % » en nombres ; garde le texte sinon."""
    raw = text.strip()
    compact = re.sub(r"[\s  ]", "", raw).rstrip("%")
    if re.fullmatch(r"-?\d+", compact):
        return int(compact)
    if re.fullmatch(r"-?\d+[.,]\d+", compact):
        return float(compact.replace(",", "."))
    return raw or None


class TableStore:
    def __init__(self, documents: list[Document]):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.tables: list[Table] = []
        for doc in documents:
            try:
                self._add_document(doc)
            except Exception as e:  # noqa: BLE001 - un tableau illisible ne bloque pas le reste
                print(f"⚠ tableau ignoré ({doc.id}) : {e}")

    # ── Construction ─────────────────────────────────────────────────────────

    def _add_document(self, doc: Document) -> None:
        wanted = doc.meta.get("sql", doc.format in {"csv", "json", "xlsx"})
        if not wanted:
            return
        base = slug(re.sub(r"\.\w+$", "", doc.id.replace("donnees/", "")), 60)
        if doc.format in {"csv", "json"}:
            for block in doc.blocks:
                if block.kind == "table" and block.rows:
                    self._create(base, doc, doc.title, block.rows[0], block.rows[1:])
        elif doc.format == "xlsx":
            heading = ""
            for block in doc.blocks:
                if block.kind == "heading":
                    heading = block.text
                elif block.kind == "table" and block.rows:
                    name = f"{base}_{slug(heading.split('–')[0], 30)}"
                    self._create(name, doc, f"{doc.title} — {heading}", block.rows[0], block.rows[1:])
        elif doc.format == "html":
            self._add_html_tables(doc, base)

    def _add_html_tables(self, doc: Document, base: str) -> None:
        groups: dict[tuple[str, ...], list[tuple[str, Block]]] = {}
        heading = ""
        for block in doc.blocks:
            if block.kind == "heading":
                heading = block.text
            elif block.kind == "table" and block.rows and len(block.rows) >= 3:
                key = tuple(slug(h) for h in block.rows[0])
                groups.setdefault(key, []).append((heading, block))
        for i, items in enumerate(groups.values(), start=1):
            header = items[0][1].rows[0]
            rows = [[h, *row] for h, block in items for row in block.rows[1:]]
            years = sorted({int(y) for h, _ in items for y in re.findall(r"\b(?:19|20)\d\d\b", h)})
            suffix = f"{years[0]}_{years[-1]}" if len(years) > 1 else str(years[0]) if years else str(i)
            name = base if len(groups) == 1 else f"{base}_{suffix}"
            self._create(name, doc, f"{doc.title} — {len(items)} tableau(x)", ["section", *header], rows)

    def _create(self, name: str, doc: Document, title: str, header: list[str], rows: list[list[str]]) -> None:
        if not rows or len(header) < 2:
            return
        # Tableau « large » (une colonne par année, ex. Année | 2012 | 2013 | … ) :
        # on le transpose en une ligne par année, plus naturel à interroger en SQL
        # (WHERE annee = 2023) qu'une colonne par année.
        years = [h for h in header[1:] if re.fullmatch(r"\s*(19|20)\d\d\s*", h)]
        if len(years) >= 4 and len(years) >= len(header) - 2:
            labels = [row[0] or f"ligne {i}" for i, row in enumerate(rows, start=1)]
            header, rows = ["annee", *labels], [
                [header[j].strip(), *(row[j] if j < len(row) else "" for row in rows)]
                for j in range(1, len(header))
                if re.fullmatch(r"\s*(19|20)\d\d\s*", header[j])
            ]
            title += " (une ligne par année)"
        used: set[str] = set()
        columns = [_column_name(label, used) for label in header]
        name = slug(name, 60)
        while any(t.name == name for t in self.tables):
            name += "_bis"
        values = [tuple(_value(c) for c in (row + [""] * len(columns))[: len(columns)]) for row in rows]
        # Colonnes typées : « WHERE annee = '2023' » trouve alors bien l'entier 2023
        types = []
        for j in range(len(columns)):
            cells = [row[j] for row in values if row[j] is not None]
            if cells and all(isinstance(v, int) for v in cells):
                types.append("INTEGER")
            elif cells and all(isinstance(v, (int, float)) for v in cells):
                types.append("REAL")
            else:
                types.append("TEXT")
        definition = ", ".join(f'"{c}" {t}' for c, t in zip(columns, types))
        self.db.execute(f'CREATE TABLE "{name}" ({definition})')
        self.db.executemany(f'INSERT INTO "{name}" VALUES ({", ".join("?" * len(columns))})', values)
        self.tables.append(Table(name, doc.id, title, columns, list(header), len(values), values))

    # ── Utilisation ──────────────────────────────────────────────────────────

    def search(self, question: str, k: int = 3) -> list[str]:
        """Noms des k tables dont le titre et les colonnes partagent le plus de mots avec la question."""
        from .text import tokenize

        words = set(tokenize(question))
        scored = []
        for table in self.tables:
            vocabulary = set(tokenize(" ".join([table.title, table.name, *table.labels])))
            for row in table.examples:
                vocabulary |= set(tokenize(" ".join(str(v) for v in row if isinstance(v, str))))
            scored.append((len(words & vocabulary), -len(table.columns), table.name))
        return [name for score, _, name in sorted(scored, reverse=True)[:k] if score > 0]

    def schema(self, tables: list[str] | None = None, max_value: int = 40) -> str:
        """Description compacte des tables, à fournir au LLM."""
        from collections import Counter

        out = []
        for table in self.tables:
            if tables and table.name not in tables:
                continue
            out.append(f"TABLE {table.name}  -- {table.title} ({table.rows} lignes)")
            for j, (column, label) in enumerate(zip(table.columns, table.labels)):
                note = f" « {label[:60]} »" if slug(label) != column else ""
                cells = [row[j] for row in table.examples if row[j] not in (None, "")]
                counts = Counter(cells)
                if cells and all(isinstance(v, str) for v in cells) and 1 < len(counts) <= 60:
                    # Peu de valeurs distinctes : on donne les plus fréquentes, pour écrire
                    # des filtres justes (« Santé » et non « sante »)
                    shown = ", ".join(str(v)[:max_value] for v, _ in counts.most_common(15))
                    more = ", …" if len(counts) > 15 else ""
                    out.append(f"  - {column}{note}  valeurs : {shown}{more}")
                else:
                    example = str(cells[0])[:max_value] if cells else ""
                    out.append(f"  - {column}{note}" + (f"  ex. : {example}" if example else ""))
        return "\n".join(out)

    def query(self, sql: str, max_rows: int = 50) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Exécute une requête en lecture seule ; renvoie (colonnes, lignes)."""
        statement = sql.strip().rstrip(";").strip()
        statement = re.sub(r"^```(?:sql)?\s*|\s*```$", "", statement, flags=re.I).strip()
        if ";" in statement:
            raise SQLError("Une seule requête à la fois.")
        if not re.match(r"(?is)^\s*(select|with)\b", statement):
            raise SQLError("Seules les requêtes SELECT sont autorisées.")
        self.db.execute("PRAGMA query_only = ON")
        deadline = [0]

        def guard() -> int:  # interrompt les requêtes trop longues
            deadline[0] += 1
            return 1 if deadline[0] > 2000 else 0

        self.db.set_progress_handler(guard, 10_000)
        try:
            cursor = self.db.execute(statement)
            rows = cursor.fetchmany(max_rows)
            columns = [d[0] for d in cursor.description or []]
        except sqlite3.Error as e:
            raise SQLError(str(e)) from e
        finally:
            self.db.set_progress_handler(None, 0)
        return columns, rows


def format_result(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Résultat SQL sous forme de tableau texte."""
    if not rows:
        return "(aucune ligne)"
    lines = [" | ".join(columns)]
    lines += [" | ".join("" if v is None else str(v) for v in row) for row in rows]
    return "\n".join(lines)
