from __future__ import annotations

from pathlib import Path

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


class TranscriptSourceAdapter:
    name = "transcript"

    def detect(self, root: str | Path) -> bool:
        base = Path(root)
        if base.is_file():
            return "transcript" in base.name.lower()
        return any("transcript" in path.name.lower() for path in base.rglob("*") if path.is_file())

    def discover(self, root: str | Path) -> list[DiscoveredImportSource]:
        base = Path(root)
        rows: list[DiscoveredImportSource] = []
        if base.is_file():
            paths = [base] if "transcript" in base.name.lower() else []
            relative_base = base.parent
        else:
            paths = sorted(p for p in base.rglob("*") if p.is_file() and "transcript" in p.name.lower())
            relative_base = base
        for path in paths:
            rows.append(
                DiscoveredImportSource(
                    path=path,
                    relative_path=path.relative_to(relative_base).as_posix(),
                    source_kind="transcript",
                    artifact_kind="session_log",
                    is_text=True,
                    metadata={},
                )
            )
        return rows

    def import_intent(self) -> str:
        return "grounded_knowledge"

    def build_rows(self, context, sources: list[DiscoveredImportSource]) -> StructuredImportRows | None:
        return None


register_source_adapter(TranscriptSourceAdapter())
