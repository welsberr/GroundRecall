from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


class DocliftBundleSourceAdapter:
    name = "doclift_bundle"

    def _resolve_bundle_path(self, base: Path, value: str | Path | None) -> Path:
        if value is None:
            return Path()
        path = Path(value)
        if path.is_absolute():
            return path
        return base / path

    def detect(self, root: str | Path) -> bool:
        base = Path(root)
        return (base / "manifest.json").exists() and (base / "documents").exists()

    def discover(self, root: str | Path) -> list[DiscoveredImportSource]:
        base = Path(root)
        rows: list[DiscoveredImportSource] = []
        for path in sorted(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".md"}):
            rows.append(
                DiscoveredImportSource(
                    path=path,
                    relative_path=path.relative_to(base).as_posix(),
                    source_kind="doclift_bundle",
                    artifact_kind="doclift_bundle_artifact",
                    is_text=True,
                    metadata={},
                )
            )
        return rows

    def import_intent(self) -> str:
        return "both"

    def build_rows(self, context, sources: list[DiscoveredImportSource]) -> StructuredImportRows | None:
        base = Path(context.source_root)
        if not self.detect(base) and sources:
            for candidate in [sources[0].path.parent, *sources[0].path.parents]:
                if self.detect(candidate):
                    base = candidate
                    break
        manifest_path = base / "manifest.json"
        if not manifest_path.exists():
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        artifact_rows: list[dict] = []
        observation_rows: list[dict] = []
        claim_rows: list[dict] = []
        concept_rows: list[dict] = []
        relation_rows: list[dict] = []

        artifact_by_path: dict[str, str] = {}
        for source in sources:
            artifact_id = f"ia_{sha256(source.relative_path.encode('utf-8')).hexdigest()[:12]}"
            artifact_rows.append(
                {
                    "artifact_id": artifact_id,
                    "import_id": context.import_id,
                    "artifact_kind": source.artifact_kind,
                    "path": source.relative_path,
                    "title": source.path.stem,
                    "sha256": sha256(source.path.read_bytes()).hexdigest(),
                    "created_at": context.imported_at,
                    "metadata": {"source_kind": source.source_kind},
                    "current_status": "draft",
                }
            )
            artifact_by_path[source.relative_path] = artifact_id

        documents = [item for item in manifest.get("documents", []) if isinstance(item, dict)]
        previous_concept_id: str | None = None
        for index, document in enumerate(documents, start=1):
            title = str(document.get("title") or f"Document {index}")
            concept_id = f"concept::{document.get('document_id') or title.lower().replace(' ', '-')}"
            markdown_path = self._resolve_bundle_path(base, document.get("markdown_path", ""))
            if markdown_path.exists():
                relative_markdown = markdown_path.relative_to(base).as_posix()
            else:
                relative_markdown = str(document.get("markdown_path", ""))
            artifact_id = artifact_by_path.get(str(relative_markdown), "")
            figures_path = self._resolve_bundle_path(base, document.get("figures_path", ""))
            figure_payload = {}
            if figures_path.exists():
                figure_payload = json.loads(figures_path.read_text(encoding="utf-8"))
            source_path = str(figure_payload.get("source_path") or document.get("source_path") or relative_markdown)
            source_path_kind = str(figure_payload.get("source_path_kind") or document.get("source_path_kind") or "source_root_relative")

            concept_rows.append(
                {
                    "concept_id": concept_id,
                    "import_id": context.import_id,
                    "title": title,
                    "aliases": [],
                    "description": f"Imported from doclift bundle document kind '{document.get('document_kind', 'document')}'.",
                    "source_artifact_ids": [artifact_id] if artifact_id else [],
                    "current_status": "triaged",
                }
            )
            observation_id = f"obs_doclift_{index}"
            observation_rows.append(
                {
                    "observation_id": observation_id,
                    "import_id": context.import_id,
                    "artifact_id": artifact_id,
                    "role": "summary",
                    "text": title,
                    "origin_path": relative_markdown,
                    "origin_section": title,
                    "line_start": 0,
                    "line_end": 0,
                    "source_url": source_path,
                    "metadata": {"source_path_kind": source_path_kind},
                    "grounding_status": "grounded",
                    "support_kind": "direct_source",
                    "confidence_hint": 0.85,
                    "current_status": "draft",
                }
            )
            claim_rows.append(
                {
                    "claim_id": f"clm_doclift_{index}",
                    "import_id": context.import_id,
                    "claim_text": f"{title} is a {document.get('document_kind', 'document')} in the imported doclift bundle.",
                    "claim_kind": "summary",
                    "source_observation_ids": [observation_id],
                    "supporting_fragment_ids": [],
                    "concept_ids": [concept_id],
                    "contradicts_claim_ids": [],
                    "supersedes_claim_ids": [],
                    "confidence_hint": 0.85,
                    "grounding_status": "grounded",
                    "current_status": "triaged",
                }
            )
            if previous_concept_id is not None:
                relation_rows.append(
                    {
                        "relation_id": f"rel_doclift_seq_{index}",
                        "import_id": context.import_id,
                        "source_id": previous_concept_id,
                        "target_id": concept_id,
                        "relation_type": "references",
                        "evidence_ids": [f"clm_doclift_{index}"],
                        "current_status": "draft",
                    }
                )
            previous_concept_id = concept_id

        return StructuredImportRows(
            artifact_rows=artifact_rows,
            observation_rows=observation_rows,
            claim_rows=claim_rows,
            concept_rows=concept_rows,
            relation_rows=relation_rows,
        )


register_source_adapter(DocliftBundleSourceAdapter())
