from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


SECTION_RE = re.compile(r"^##\s+(.*)$", re.M)


def _site_root(root: Path) -> Path:
    candidate = root / "site2_src" / "content" / "indexcc"
    if candidate.is_dir():
        return candidate
    if (root / "content" / "indexcc").is_dir():
        return root / "content" / "indexcc"
    if root.name == "indexcc" and root.is_dir():
        return root
    return root


def _discover_md_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    if base.is_file():
        return [base] if base.suffix.lower() == ".md" else []
    return sorted(path for path in base.rglob("*.md") if path.is_file())


def _read_meta(md_path: Path) -> dict[str, Any]:
    meta_path = md_path.with_suffix(".meta.json")
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _split_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    current = "Body"
    sections: dict[str, list[str]] = {current: []}
    for line in lines:
        match = SECTION_RE.match(line)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items() if "\n".join(value).strip()}


class IndexCcSourceAdapter:
    name = "indexcc"

    def detect(self, root: str | Path) -> bool:
        base = _site_root(Path(root))
        if not base.is_dir():
            return False
        md_files = _discover_md_files(base)
        if not md_files:
            return False
        return any(str(_read_meta(path).get("page_kind", "")) == "claim_entry" for path in md_files)

    def discover(self, root: str | Path) -> list[DiscoveredImportSource]:
        base = _site_root(Path(root))
        rows: list[DiscoveredImportSource] = []
        for path in _discover_md_files(base):
            rows.append(
                DiscoveredImportSource(
                    path=path,
                    relative_path=path.relative_to(base).as_posix(),
                    source_kind="indexcc",
                    artifact_kind="indexcc_entry",
                    is_text=True,
                    metadata={"corpus": "indexcc"},
                )
            )
        return rows

    def import_intent(self) -> str:
        return "grounded_knowledge"

    def build_rows(self, context, sources: list[DiscoveredImportSource]) -> StructuredImportRows | None:
        artifact_rows: list[dict[str, Any]] = []
        observation_rows: list[dict[str, Any]] = []
        claim_rows: list[dict[str, Any]] = []
        concept_rows: list[dict[str, Any]] = []
        relation_rows: list[dict[str, Any]] = []

        for index, source in enumerate(sources, start=1):
            meta = _read_meta(source.path)
            text = source.path.read_text(encoding="utf-8")
            sections = _split_sections(text)
            title = str(meta.get("title") or source.path.stem)
            claim_text = sections.get("Claim", "")
            response_text = sections.get("Response", "")
            references_text = sections.get("References", "")
            further_text = sections.get("Further Reading", "")
            artifact_id = f"ia_{sha256(source.relative_path.encode('utf-8')).hexdigest()[:12]}"
            artifact_rows.append(
                {
                    "artifact_id": artifact_id,
                    "import_id": context.import_id,
                    "artifact_kind": source.artifact_kind,
                    "path": source.relative_path,
                    "title": title,
                    "sha256": sha256(source.path.read_bytes()).hexdigest(),
                    "created_at": context.imported_at,
                    "metadata": {
                        "corpus": "indexcc",
                        "document_kind": meta.get("page_kind", "claim_entry"),
                        "author": meta.get("author", ""),
                        "legacy_source": meta.get("legacy_source", ""),
                        "section_label": meta.get("section_label", ""),
                        "page_kind": meta.get("page_kind", ""),
                    },
                    "current_status": "draft",
                }
            )

            body_sections = [
                ("Claim", claim_text),
                ("Response", response_text),
                ("References", references_text),
                ("Further Reading", further_text),
            ]
            for sec_index, (section_name, section_text) in enumerate(body_sections, start=1):
                if not section_text:
                    continue
                observation_rows.append(
                    {
                        "observation_id": f"obs_{artifact_id}_{sec_index}",
                        "import_id": context.import_id,
                        "artifact_id": artifact_id,
                        "role": "summary" if section_name != "Claim" else "claim",
                        "text": section_text,
                        "origin_path": source.relative_path,
                        "origin_section": section_name,
                        "line_start": 0,
                        "line_end": 0,
                        "source_url": str(meta.get("legacy_source") or ""),
                        "metadata": {
                            "corpus": "indexcc",
                            "document_kind": meta.get("page_kind", "claim_entry"),
                            "section_name": section_name,
                            "author": meta.get("author", ""),
                        },
                        "grounding_status": "grounded",
                        "support_kind": "direct_source",
                        "confidence_hint": 0.88 if section_name == "Claim" else 0.8,
                        "current_status": "draft",
                    }
                )

            claim_obs_id = f"obs_{artifact_id}_1" if claim_text else ""
            if claim_text:
                claim_rows.append(
                    {
                        "claim_id": f"clm_{artifact_id}",
                        "import_id": context.import_id,
                        "claim_text": claim_text,
                        "claim_kind": "claim_entry",
                        "source_observation_ids": [claim_obs_id],
                        "supporting_fragment_ids": [],
                        "concept_ids": [f"concept::{source.path.stem.lower()}"],
                        "contradicts_claim_ids": [],
                        "supersedes_claim_ids": [],
                        "confidence_hint": 0.88,
                        "grounding_status": "grounded",
                        "current_status": "triaged",
                    }
                )

            concept_rows.append(
                {
                    "concept_id": f"concept::{source.path.stem.lower()}",
                    "import_id": context.import_id,
                    "title": title,
                    "aliases": [source.path.stem.upper()],
                    "description": meta.get("description", "Imported Index to Creationist Claims entry."),
                    "source_artifact_ids": [artifact_id],
                    "current_status": "triaged",
                }
            )

        return StructuredImportRows(
            artifact_rows=artifact_rows,
            fragment_rows=[],
            observation_rows=observation_rows,
            claim_rows=claim_rows,
            concept_rows=concept_rows,
            relation_rows=relation_rows,
        )


register_source_adapter(IndexCcSourceAdapter())
