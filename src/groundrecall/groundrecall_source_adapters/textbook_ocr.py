from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


MANIFEST_NAME = ".groundrecall-textbook.json"
PAGE_BREAK = "\f"
CHAPTER_RE = re.compile(r"^Chapter\s+(\d+)\.\s+(.+?)(?:\s+\d+)?$", re.IGNORECASE)
PAGE_HEADER_RE = re.compile(r"^\s*(\d+|[ivxlcdm]+)\s+([A-Z][A-Za-z][A-Za-z' -]{2,80})\s*$")
REFERENCE_SECTION_RE = re.compile(r"^(selected references|references|bibliography|index)\b", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass
class Paragraph:
    text: str
    section: str
    page_start: int
    page_end: int
    line_start: int
    line_end: int


class TextbookOcrSourceAdapter:
    name = "textbook_ocr"

    def detect(self, root: str | Path) -> bool:
        return (Path(root) / MANIFEST_NAME).exists()

    def discover(self, root: str | Path) -> list[DiscoveredImportSource]:
        base = Path(root)
        manifest = _load_manifest(base)
        configured_files = manifest.get("files") or []
        if configured_files:
            paths = [base / str(item) for item in configured_files]
        else:
            paths = sorted(path for path in base.rglob("*.txt") if path.is_file())
        rows: list[DiscoveredImportSource] = []
        for path in paths:
            if path.exists() and path.suffix.lower() == ".txt":
                rows.append(
                    DiscoveredImportSource(
                        path=path,
                        relative_path=path.relative_to(base).as_posix(),
                        source_kind="textbook_ocr",
                        artifact_kind="textbook_ocr_text",
                        is_text=True,
                        metadata={"manifest": MANIFEST_NAME},
                    )
                )
        return rows

    def import_intent(self) -> str:
        return "both"

    def build_rows(
        self,
        context,
        sources: list[DiscoveredImportSource],
        root: Path | None = None,
    ) -> StructuredImportRows | None:
        if root is None:
            return None
        manifest = _load_manifest(root)
        book_title = str(manifest.get("title") or root.name.replace("-", " ").title())
        book_slug = _slug(str(manifest.get("id") or book_title))
        promote_sections = bool(manifest.get("promote_sections", False))
        imported_concepts: dict[str, dict[str, Any]] = {}
        artifact_rows: list[dict[str, Any]] = []
        fragment_rows: list[dict[str, Any]] = []
        observation_rows: list[dict[str, Any]] = []
        claim_rows: list[dict[str, Any]] = []
        relation_rows: list[dict[str, Any]] = []

        book_concept_id = f"concept::{book_slug}"
        imported_concepts[book_concept_id] = {
            "concept_id": book_concept_id,
            "import_id": context.import_id,
            "title": book_title,
            "aliases": list(manifest.get("aliases", [])),
            "description": str(manifest.get("description") or "Imported OCR textbook source."),
            "source_artifact_ids": [],
            "current_status": "triaged",
        }

        for artifact_index, source in enumerate(sources, start=1):
            artifact_id = f"ia_{sha256(source.relative_path.encode('utf-8')).hexdigest()[:12]}"
            source_bytes = source.path.read_bytes()
            paragraphs = _extract_paragraphs(source.path.read_text(encoding="utf-8", errors="replace"), book_title)
            sections = sorted({item.section for item in paragraphs if item.section})
            artifact_rows.append(
                {
                    "artifact_id": artifact_id,
                    "import_id": context.import_id,
                    "artifact_kind": "textbook_ocr_text",
                    "path": source.relative_path,
                    "title": f"{book_title} part {artifact_index}",
                    "sha256": sha256(source_bytes).hexdigest(),
                    "created_at": context.imported_at,
                    "metadata": {
                        "source_kind": "textbook_ocr",
                        "book_title": book_title,
                        "authors": manifest.get("authors", []),
                        "year": manifest.get("year", ""),
                        "sections": sections,
                    },
                    "current_status": "draft",
                }
            )
            imported_concepts[book_concept_id]["source_artifact_ids"].append(artifact_id)

            if promote_sections:
                for section in sections:
                    section_id = f"concept::{_slug(section)}"
                    row = imported_concepts.setdefault(
                        section_id,
                        {
                            "concept_id": section_id,
                            "import_id": context.import_id,
                            "title": section,
                            "aliases": [],
                            "description": f"Section or topic imported from {book_title}.",
                            "source_artifact_ids": [],
                            "current_status": "triaged",
                        },
                    )
                    row["source_artifact_ids"].append(artifact_id)

            for paragraph_index, paragraph in enumerate(paragraphs, start=1):
                fragment_id = f"frag_{artifact_id}_{paragraph_index}"
                observation_id = f"obs_{artifact_id}_{paragraph_index}"
                claim_id = f"clm_{observation_id}_{paragraph_index}"
                section_concept_id = f"concept::{_slug(paragraph.section)}"
                concept_ids = [book_concept_id]
                if promote_sections and section_concept_id in imported_concepts and section_concept_id != book_concept_id:
                    concept_ids.append(section_concept_id)
                metadata = {
                    "analysis_lane": "source_ingestion",
                    "argument_role": "source_candidate",
                    "risk_flags": ["ocr_text_needs_review"],
                    "source_kind": "textbook_ocr",
                    "page_start": paragraph.page_start,
                    "page_end": paragraph.page_end,
                }
                fragment_rows.append(
                    {
                        "fragment_id": fragment_id,
                        "import_id": context.import_id,
                        "source_id": artifact_id,
                        "text": paragraph.text,
                        "section": paragraph.section,
                        "line_start": paragraph.line_start,
                        "line_end": paragraph.line_end,
                        "metadata": metadata,
                        "current_status": "draft",
                    }
                )
                observation_rows.append(
                    {
                        "observation_id": observation_id,
                        "import_id": context.import_id,
                        "artifact_id": artifact_id,
                        "role": "summary",
                        "text": paragraph.text,
                        "origin_path": source.relative_path,
                        "origin_section": paragraph.section,
                        "line_start": paragraph.line_start,
                        "line_end": paragraph.line_end,
                        "grounding_status": "grounded",
                        "support_kind": "direct_source",
                        "confidence_hint": 0.55,
                        "current_status": "draft",
                    }
                )
                claim_rows.append(
                    {
                        "claim_id": claim_id,
                        "import_id": context.import_id,
                        "claim_text": paragraph.text,
                        "claim_kind": "source_excerpt",
                        "metadata": metadata,
                        "source_observation_ids": [observation_id],
                        "supporting_fragment_ids": [fragment_id],
                        "concept_ids": concept_ids,
                        "contradicts_claim_ids": [],
                        "supersedes_claim_ids": [],
                        "confidence_hint": 0.55,
                        "grounding_status": "grounded",
                        "current_status": "triaged",
                    }
                )

        concept_rows = list(imported_concepts.values())
        for row in concept_rows:
            row["source_artifact_ids"] = sorted(set(row.get("source_artifact_ids", [])))
        return StructuredImportRows(
            artifact_rows=artifact_rows,
            fragment_rows=fragment_rows,
            observation_rows=observation_rows,
            claim_rows=claim_rows,
            concept_rows=concept_rows,
            relation_rows=relation_rows,
        )


def _load_manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))


def _extract_paragraphs(text: str, book_title: str) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    current_section = book_title
    in_reference_region = False
    line_number = 0
    for page_number, page in enumerate(text.split(PAGE_BREAK), start=1):
        pending: list[tuple[int, str]] = []
        for raw_line in page.splitlines():
            line_number += 1
            line = _clean_line(raw_line)
            if _is_noise_line(line, book_title):
                if pending:
                    _append_paragraph(paragraphs, pending, current_section, page_number)
                    pending = []
                continue
            heading = _heading_from_line(line)
            if heading:
                if pending:
                    _append_paragraph(paragraphs, pending, current_section, page_number)
                    pending = []
                current_section = heading
                in_reference_region = bool(REFERENCE_SECTION_RE.match(heading))
                continue
            if in_reference_region:
                continue
            if not line:
                if pending:
                    _append_paragraph(paragraphs, pending, current_section, page_number)
                    pending = []
                continue
            pending.append((line_number, line))
        if pending:
            _append_paragraph(paragraphs, pending, current_section, page_number)
    return paragraphs


def _append_paragraph(paragraphs: list[Paragraph], lines: list[tuple[int, str]], section: str, page_number: int) -> None:
    text = _join_wrapped_lines([line for _, line in lines])
    if not _is_candidate_paragraph(text):
        return
    paragraphs.append(
        Paragraph(
            text=text,
            section=section,
            page_start=page_number,
            page_end=page_number,
            line_start=lines[0][0],
            line_end=lines[-1][0],
        )
    )


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _heading_from_line(line: str) -> str:
    chapter_match = CHAPTER_RE.match(line)
    if chapter_match:
        return f"Chapter {chapter_match.group(1)}. {chapter_match.group(2).strip()}"
    candidate = re.sub(r"\s+\d{1,4}$", "", line).strip()
    if _looks_like_heading(candidate):
        return candidate
    return ""


def _looks_like_heading(line: str) -> bool:
    if not line or len(line) > 90 or len(line) < 4:
        return False
    if line.endswith((".", ",", ";", ":")):
        return False
    if any(char.isdigit() for char in line):
        return False
    if re.search(r"[^A-Za-z '&-]", line):
        return False
    words = WORD_RE.findall(line)
    if not 1 <= len(words) <= 8:
        return False
    titleish = sum(1 for word in words if word[:1].isupper())
    return titleish >= max(1, len(words) - 1)


def _is_noise_line(line: str, book_title: str) -> bool:
    if not line:
        return False
    if line.isdigit():
        return True
    if re.fullmatch(r"[ivxlcdm]+", line.lower()):
        return True
    if PAGE_HEADER_RE.match(line):
        return True
    normalized = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
    title_norm = re.sub(r"[^a-z0-9]+", " ", book_title.lower()).strip()
    return normalized == title_norm


def _join_wrapped_lines(lines: list[str]) -> str:
    text = " ".join(lines)
    text = re.sub(r"([A-Za-z])- ([a-z])", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_candidate_paragraph(text: str) -> bool:
    if len(text) < 120:
        return False
    if len(WORD_RE.findall(text)) < 18:
        return False
    if _digit_ratio(text) > 0.32:
        return False
    return True


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for char in text if char.isdigit()) / len(text)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


register_source_adapter(TextbookOcrSourceAdapter())
