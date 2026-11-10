#!/usr/bin/env python3
"""Télécharge le corpus du TP décrit dans data/corpus.toml.

Usage :
    python scripts/download_corpus.py               # télécharge les fichiers manquants
    python scripts/download_corpus.py --check       # vérifie les fichiers présents, sans réseau
    python scripts/download_corpus.py --force       # re-télécharge tout
    python scripts/download_corpus.py --only cnil   # seulement les chemins contenant "cnil"
    python scripts/download_corpus.py --zip corpus.zip   # depuis une archive
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import shutil
import ssl
import sys
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "corpus.toml"
DEST = ROOT / "data" / "corpus"
USER_AGENT = "atal-m2-rag-course/1.0 (cours M2 ATAL; +https://github.com/master-atal-cours/atal-m2-rag)"
TIMEOUT_S = 90
RETRIES = 3

# Magasin de certificats du système, complété par les certificats intermédiaires que
# certains serveurs n'envoient pas (voir scripts/intermediates.pem).
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.load_verify_locations(cafile=Path(__file__).resolve().parent / "intermediates.pem")

# Signatures attendues par extension : détecte une page d'erreur ou un
# anti-robot renvoyé à la place du vrai fichier.
MAGIC = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK"],
    ".xlsx": [b"PK"],
    ".odt": [b"PK"],
    ".zip": [b"PK"],
}


@dataclass
class Result:
    path: str
    status: str  # "ok", "présent", "modifié", "manquant", "échec"
    size: int = 0
    detail: str = ""


def load_manifest() -> list[dict]:
    with MANIFEST.open("rb") as f:
        return tomllib.load(f)["documents"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_content(path: str, data: bytes) -> str | None:
    """Renvoie un message d'erreur si le contenu ne ressemble pas au format attendu."""
    if not data:
        return "fichier vide"
    suffix = Path(path).suffix.lower()
    expected = MAGIC.get(suffix)
    if expected and not any(data.startswith(m) for m in expected):
        head = data[:200].decode("utf-8", errors="replace").replace("\n", " ")
        return f"contenu inattendu pour un {suffix} (début : {head[:80]!r})"
    if suffix in {".html", ".md", ".csv", ".json"} and len(data) < 200:
        return f"contenu trop court ({len(data)} octets)"
    return None


def fetch(doc: dict) -> bytes:
    headers = {"User-Agent": USER_AGENT, **doc.get("headers", {})}
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            request = urllib.request.Request(doc["url"], headers=headers)
            with urllib.request.urlopen(
                request, timeout=TIMEOUT_S, context=SSL_CONTEXT
            ) as response:
                data = response.read()
            if error := check_content(doc["path"], data):
                raise ValueError(error)
            return data
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            last_error = e
            if isinstance(e, urllib.error.HTTPError) and e.code in {403, 404, 410}:
                break  # inutile d'insister
            time.sleep(2 * attempt)
    raise RuntimeError(str(last_error))


def download(doc: dict, force: bool) -> Result:
    target = DEST / doc["path"]
    expected = doc.get("sha256") or ""
    if target.exists() and not force:
        if not expected or sha256_of(target) == expected:
            return Result(doc["path"], "présent", target.stat().st_size)
    try:
        data = fetch(doc)
    except Exception as e:  # noqa: BLE001 - on veut un rapport, pas une trace
        return Result(doc["path"], "échec", detail=str(e))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    digest = hashlib.sha256(data).hexdigest()
    if expected and digest != expected:
        return Result(
            doc["path"], "modifié", len(data),
            "la source a changé depuis la préparation du TP (fichier conservé)",
        )
    return Result(doc["path"], "ok", len(data))


def check(doc: dict) -> Result:
    target = DEST / doc["path"]
    if not target.exists():
        return Result(doc["path"], "manquant")
    expected = doc.get("sha256") or ""
    if expected and sha256_of(target) != expected:
        return Result(doc["path"], "modifié", target.stat().st_size)
    return Result(doc["path"], "présent", target.stat().st_size)


def update_hashes(documents: list[dict]) -> None:
    """Réécrit les lignes `sha256 = "..."` du manifeste à partir des fichiers locaux."""
    text = MANIFEST.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^(?=\[\[documents\]\])", text)
    digests = {
        d["path"]: sha256_of(DEST / d["path"])
        for d in documents
        if (DEST / d["path"]).exists()
    }
    out = []
    for block in blocks:
        m = re.search(r'(?m)^path\s*=\s*"([^"]+)"', block)
        if m and m.group(1) in digests:
            line = f'sha256 = "{digests[m.group(1)]}"'
            if re.search(r"(?m)^sha256\s*=", block):
                block = re.sub(r'(?m)^sha256\s*=\s*"[^"]*"', line, block)
            else:
                block = block.rstrip("\n") + "\n" + line + "\n\n"
        out.append(block)
    MANIFEST.write_text("".join(out), encoding="utf-8")
    print(f"{len(digests)} empreintes mises à jour dans {MANIFEST.relative_to(ROOT)}")


def install_zip(source: str, documents: list[dict]) -> None:
    """Installe le corpus depuis une archive locale ou distante."""
    if re.match(r"https?://", source):
        request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(
            request, timeout=TIMEOUT_S * 4, context=SSL_CONTEXT
        ) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
    else:
        archive = zipfile.ZipFile(source)
    wanted = {d["path"] for d in documents}
    count = 0
    for member in archive.infolist():
        name = member.filename.removeprefix("corpus/")
        if name not in wanted:  # n'extrait que les fichiers du manifeste
            continue
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        count += 1
    print(f"{count} fichiers extraits dans {DEST.relative_to(ROOT)}")


def make_zip(destination: str, documents: list[dict]) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for d in documents:
            path = DEST / d["path"]
            if path.exists():
                archive.write(path, f"corpus/{d['path']}")
    print(f"Archive créée : {destination}")


def human(size: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} To"


def report(results: list[Result]) -> int:
    symbols = {
        "ok": "✓", "présent": "✓", "modifié": "!", "manquant": "✗", "échec": "✗",
    }
    for r in sorted(results, key=lambda r: r.path):
        size = human(r.size) if r.size else ""
        line = f" {symbols[r.status]} {r.status:<8} {r.path:<60} {size:>8}"
        if r.detail:
            line += f"\n            → {r.detail}"
        print(line)
    failed = [r for r in results if r.status in {"échec", "manquant"}]
    changed = [r for r in results if r.status == "modifié"]
    total = sum(r.size for r in results)
    print(
        f"\n{len(results) - len(failed)}/{len(results)} fichiers disponibles "
        f"({human(total)}) dans {DEST.relative_to(ROOT)}/"
    )
    if changed:
        print(
            f"{len(changed)} fichier(s) différent(s) de la version préparée pour le TP : "
            "certaines réponses attendues du questionnaire peuvent avoir changé."
        )
    if failed:
        print(
            f"{len(failed)} fichier(s) indisponible(s). Réessayez plus tard, ou installez "
            "l'archive miroir : python scripts/download_corpus.py --zip <archive>"
        )
        return 1
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:  # consoles Windows en cp1252
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Télécharge le corpus du TP RAG.")
    parser.add_argument("--check", action="store_true", help="vérifie sans télécharger")
    parser.add_argument("--force", action="store_true", help="re-télécharge tout")
    parser.add_argument("--only", help="ne traite que les chemins contenant ce texte")
    parser.add_argument("--zip", help="installe depuis une archive (chemin ou URL)")
    parser.add_argument("--make-zip", help="crée l'archive miroir")
    parser.add_argument("--update-hashes", action="store_true",
                        help="recalcule les sha256 du manifeste")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    documents = load_manifest()
    if args.only:
        documents = [d for d in documents if args.only in d["path"]]

    if args.zip:
        install_zip(args.zip, documents)
        return report([check(d) for d in documents])
    if args.make_zip:
        make_zip(args.make_zip, documents)
        return 0
    if args.check:
        return report([check(d) for d in documents])

    print(f"Téléchargement de {len(documents)} documents vers {DEST.relative_to(ROOT)}/ …\n")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda d: download(d, args.force), documents))
    if args.update_hashes:
        update_hashes(load_manifest())
    return report(results)


if __name__ == "__main__":
    sys.exit(main())
