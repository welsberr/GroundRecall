from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


def _load_citegeist_symbols() -> dict[str, Any] | None:
    import sys

    citegeist_src = Path("/home/netuser/bin/CiteGeist/src")
    if citegeist_src.exists():
        sys.path.insert(0, str(citegeist_src))
    try:
        from citegeist.app_api import LiteratureExplorerApi  # type: ignore
        from citegeist.bibtex import BibEntry, parse_bibtex, render_bibtex  # type: ignore
        from citegeist.storage import BibliographyStore  # type: ignore
    except Exception:
        return None
    return {
        "LiteratureExplorerApi": LiteratureExplorerApi,
        "BibEntry": BibEntry,
        "parse_bibtex": parse_bibtex,
        "render_bibtex": render_bibtex,
        "BibliographyStore": BibliographyStore,
    }


def discover_bib_files(source_root: str | Path) -> list[Path]:
    root = Path(source_root)
    if not root.exists():
        return []
    candidates = [
        path
        for path in root.rglob("*.bib")
        if path.is_file() and not path.name.endswith("-bak.bib") and not path.name.startswith(".")
    ]

    def rank(path: Path) -> tuple[int, int, str]:
        rel = path.relative_to(root)
        name = path.name
        if rel == Path("refs.bib"):
            return (0, len(rel.parts), str(rel))
        if rel == Path("biblio.bib"):
            return (1, len(rel.parts), str(rel))
        if name == "refs.bib":
            return (2, len(rel.parts), str(rel))
        if name == "biblio.bib":
            return (3, len(rel.parts), str(rel))
        return (4, len(rel.parts), str(rel))

    return sorted(candidates, key=rank)


def load_bibliography_index(source_root: str | Path) -> dict[str, dict[str, Any]]:
    symbols = _load_citegeist_symbols()
    root = Path(source_root)
    index: dict[str, dict[str, Any]] = {}
    for bib_path in discover_bib_files(root):
        try:
            entries = _parse_bib_entries(bib_path.read_text(encoding="utf-8"), symbols=symbols)
        except Exception:
            continue
        for entry in entries:
            raw_bibtex = _render_entry_bibtex(entry, symbols=symbols)
            payload = {
                "citation_key": entry.citation_key,
                "entry_type": entry.entry_type,
                "fields": dict(entry.fields),
                "source_bib_path": str(bib_path.relative_to(root)),
                "raw_bibtex": raw_bibtex,
                "duplicate_source_bib_paths": [],
            }
            existing = index.get(entry.citation_key)
            if existing is None:
                index[entry.citation_key] = payload
            else:
                existing.setdefault("duplicate_source_bib_paths", []).append(str(bib_path.relative_to(root)))
    return index


def materialize_citegeist_store(import_dir: str | Path, source_root: str | Path) -> dict[str, Any]:
    symbols = _load_citegeist_symbols()
    if symbols is None:
        return {"available": False}
    BibliographyStore = symbols["BibliographyStore"]
    LiteratureExplorerApi = symbols["LiteratureExplorerApi"]

    import_root = Path(import_dir)
    db_path = import_root / "citegeist.sqlite3"
    if db_path.exists():
        db_path.unlink()
    store = BibliographyStore(db_path)
    ingested_files: list[str] = []
    for bib_path in discover_bib_files(source_root):
        try:
            text = bib_path.read_text(encoding="utf-8")
            entries = _parse_bib_entries(text, symbols=symbols)
            for entry in entries:
                store.upsert_entry(
                    entry,
                    raw_bibtex=_render_entry_bibtex(entry, symbols=symbols),
                    source_type="bibtex",
                    source_label=str(bib_path.relative_to(Path(source_root))),
                    review_status="draft",
                )
            store.connection.commit()
            ingested_files.append(str(bib_path.relative_to(Path(source_root))))
        except Exception:
            continue
    api = LiteratureExplorerApi(store)
    return {
        "available": True,
        "db_path": str(db_path),
        "ingested_files": ingested_files,
        "api": api,
        "store": store,
    }


def bibliography_summary_payload(source_root: str | Path) -> dict[str, Any]:
    index = load_bibliography_index(source_root)
    source_files = discover_bib_files(source_root)
    return {
        "enabled": bool(index),
        "entry_count": len(index),
        "source_files": [str(path.relative_to(Path(source_root))) for path in source_files],
    }


def serialize_bib_entry(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "citation_key": entry.get("citation_key", ""),
        "entry_type": entry.get("entry_type", ""),
        "fields": dict(entry.get("fields", {})),
        "source_bib_path": entry.get("source_bib_path", ""),
        "raw_bibtex": entry.get("raw_bibtex", ""),
        "duplicate_source_bib_paths": list(entry.get("duplicate_source_bib_paths", [])),
    }


def serialize_citegeist_entry_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    result = dict(payload)
    if "raw_bibtex" in result and isinstance(result["raw_bibtex"], str):
        return result
    return json.loads(json.dumps(result))


def _parse_bib_entries(text: str, *, symbols: dict[str, Any] | None) -> list[Any]:
    if symbols is not None:
        try:
            return symbols["parse_bibtex"](text)
        except Exception:
            pass
    return _fallback_parse_bibtex(text, symbols=symbols)


def _render_entry_bibtex(entry: Any, *, symbols: dict[str, Any] | None) -> str:
    if symbols is not None:
        try:
            return symbols["render_bibtex"]([entry])
        except Exception:
            pass
    fields = []
    for key, value in entry.fields.items():
        fields.append(f"  {key} = {{{value}}}")
    body = ",\n".join(fields)
    return f"@{entry.entry_type}{{{entry.citation_key},\n{body}\n}}"


def _fallback_parse_bibtex(text: str, *, symbols: dict[str, Any] | None) -> list[Any]:
    BibEntry = symbols["BibEntry"] if symbols is not None else None
    entries: list[Any] = []
    pattern = re.compile(r"@(?P<entry_type>[A-Za-z]+)\s*\{\s*(?P<citation_key>[^,\s]+)\s*,", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]
        fields = _fallback_parse_fields(body)
        if BibEntry is not None:
            entries.append(BibEntry(entry_type=match.group("entry_type").lower(), citation_key=match.group("citation_key").strip(), fields=fields))
        else:
            entries.append(type("BibEntryFallback", (), {"entry_type": match.group("entry_type").lower(), "citation_key": match.group("citation_key").strip(), "fields": fields})())
    return entries


def _fallback_parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    length = len(body)
    while index < length:
        while index < length and body[index] in " \t\r\n,":
            index += 1
        if index >= length or body[index] == "}":
            break
        key_start = index
        while index < length and re.match(r"[A-Za-z0-9_:-]", body[index]):
            index += 1
        key = body[key_start:index].strip().lower()
        while index < length and body[index] in " \t\r\n=":
            index += 1
        value = ""
        if index < length and body[index] == "{":
            depth = 1
            index += 1
            value_start = index
            while index < length and depth > 0:
                if body[index] == "{":
                    depth += 1
                elif body[index] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            value = body[value_start:index].strip()
            index += 1
        elif index < length and body[index] == '"':
            index += 1
            value_start = index
            while index < length and body[index] != '"':
                if body[index] == "\\":
                    index += 1
                index += 1
            value = body[value_start:index].strip()
            index += 1
        else:
            value_start = index
            while index < length and body[index] not in ",\n":
                index += 1
            value = body[value_start:index].strip()
        if key:
            fields[key] = value.rstrip(",")
    return fields
