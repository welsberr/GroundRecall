from __future__ import annotations

from pathlib import Path
import re

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


TEXT_SUFFIXES = {".tex"}
EXCLUDED_NAMES = {
    ".pp-export-tmp.tex",
    "paper.woven.arxiv.tex",
    "paper.woven.test.tex",
    "paper.woven.org",
    "paper.org",
    "paper_b.org",
    "paper_c.org",
    "paper_c.bak.org",
    "paper-demo.org",
    "paper-orig.org",
    "test.output.org",
    "tex-blocks.org",
}
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "setup"}
EXCLUDED_PREFIXES = ("table-", "figure-", "fig-")
INCLUDE_RE = re.compile(r"\\(?:include|input)\{([^}]+)\}")


class PolyPaperSourceAdapter:
    name = "polypaper"

    def detect(self, root: str | Path) -> bool:
        base = Path(root)
        return (
            (base / "main.tex").exists()
            and (base / "pieces").is_dir()
            and ((base / "paper.org").exists() or (base / "README.md").exists())
        )

    def discover(self, root: str | Path) -> list[DiscoveredImportSource]:
        base = Path(root)
        allowed_paths = self._collect_reachable_tex(base)
        rows: list[DiscoveredImportSource] = []
        for path in sorted(allowed_paths):
            rows.append(
                DiscoveredImportSource(
                    path=path,
                    relative_path=path.relative_to(base).as_posix(),
                    source_kind="polypaper",
                    artifact_kind="markdown_note",
                    is_text=True,
                    metadata={},
                )
            )
        return rows

    def import_intent(self) -> str:
        return "grounded_knowledge"

    def build_rows(self, context, sources: list[DiscoveredImportSource]) -> StructuredImportRows | None:
        return None

    def _collect_reachable_tex(self, base: Path) -> set[Path]:
        entrypoint = base / "main.tex"
        reachable: set[Path] = set()
        pending: list[Path] = [entrypoint]

        while pending:
            current = pending.pop()
            if not current.exists():
                continue
            if current in reachable:
                continue
            if any(part in EXCLUDED_DIRS for part in current.relative_to(base).parts):
                continue
            if current.name in EXCLUDED_NAMES or current.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if current.parent.name == "figs":
                continue
            if current.name.startswith(EXCLUDED_PREFIXES) or current.name == "tables.tex":
                continue
            text = current.read_text(encoding="utf-8")
            for raw_ref in INCLUDE_RE.findall(text):
                candidate = self._resolve_include(base, current.parent, raw_ref.strip())
                if candidate is not None and candidate not in reachable:
                    pending.append(candidate)
            if current != entrypoint:
                reachable.add(current)

        return reachable

    def _resolve_include(self, base: Path, current_dir: Path, raw_ref: str) -> Path | None:
        candidates = [current_dir / raw_ref, base / raw_ref]
        resolved: list[Path] = []
        for candidate in candidates:
            if candidate.suffix:
                resolved.append(candidate)
            else:
                resolved.append(candidate.with_suffix(".tex"))
        for candidate in resolved:
            if candidate.exists():
                return candidate
        return None


register_source_adapter(PolyPaperSourceAdapter())
