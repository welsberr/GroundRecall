from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


class CiteGeistOkfSourceAdapter:
    name = "citegeist_okf"

    def detect(self, root: str | Path) -> bool:
        base = Path(root)
        manifest_path = base / "manifest.json"
        if not manifest_path.exists():
            return False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        return manifest.get("bundle_kind") == "citegeist_okf_bundle"

    def discover(self, root: str | Path) -> list[DiscoveredImportSource]:
        base = Path(root)
        rows: list[DiscoveredImportSource] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(base).as_posix()
            if path.name == "manifest.json":
                kind = "citegeist_okf_manifest"
            elif relative_path.startswith("works/") and path.suffix == ".md":
                kind = "citegeist_okf_work"
            elif relative_path.startswith("topics/") and path.suffix == ".md":
                kind = "citegeist_okf_topic"
            elif path.name in {"index.md", "log.md", "bibliography.bib"}:
                kind = "citegeist_okf_support"
            else:
                continue
            rows.append(
                DiscoveredImportSource(
                    path=path,
                    relative_path=relative_path,
                    source_kind="citegeist_okf",
                    artifact_kind=kind,
                    is_text=True,
                    metadata={},
                )
            )
        return rows

    def import_intent(self) -> str:
        return "grounded_knowledge"

    def build_rows(self, context, sources: list[DiscoveredImportSource], root: Path | None = None) -> StructuredImportRows:
        base = root or sources[0].path.parent
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        work_sources = [item for item in sources if item.artifact_kind == "citegeist_okf_work"]
        topic_sources = [item for item in sources if item.artifact_kind == "citegeist_okf_topic"]

        artifact_rows: list[dict[str, Any]] = []
        fragment_rows: list[dict[str, Any]] = []
        observation_rows: list[dict[str, Any]] = []
        claim_rows: list[dict[str, Any]] = []
        concept_rows: list[dict[str, Any]] = []
        relation_rows: list[dict[str, Any]] = []

        artifact_by_path: dict[str, str] = {}
        for source in sources:
            artifact_id = f"ia_{sha256(source.relative_path.encode('utf-8')).hexdigest()[:12]}"
            artifact_by_path[source.relative_path] = artifact_id
            artifact_rows.append(
                {
                    "artifact_id": artifact_id,
                    "import_id": context.import_id,
                    "artifact_kind": source.artifact_kind,
                    "path": source.relative_path,
                    "title": _title_for_source(source),
                    "sha256": sha256(source.path.read_bytes()).hexdigest(),
                    "created_at": context.imported_at,
                    "metadata": {"source_kind": "citegeist_okf", "okf_manifest": manifest if source.relative_path == "manifest.json" else {}},
                    "current_status": "draft",
                }
            )

        topic_slugs: set[str] = set()
        for topic_source in topic_sources:
            frontmatter, _ = _split_frontmatter(topic_source.path.read_text(encoding="utf-8"))
            slug = str(frontmatter.get("slug") or Path(topic_source.relative_path).stem)
            topic_slugs.add(slug)
            concept_rows.append(
                {
                    "concept_id": _topic_concept_id(slug),
                    "import_id": context.import_id,
                    "title": str(frontmatter.get("name") or slug.replace("-", " ").title()),
                    "aliases": [slug],
                    "description": f"CiteGeist topic imported from OKF bundle {manifest.get('okf_profile', '')}.",
                    "source_artifact_ids": [artifact_by_path[topic_source.relative_path]],
                    "current_status": "triaged",
                }
            )

        work_concepts: dict[str, str] = {}
        work_frontmatter: dict[str, dict[str, Any]] = {}
        for work_source in work_sources:
            frontmatter, body = _split_frontmatter(work_source.path.read_text(encoding="utf-8"))
            citation_key = str(frontmatter.get("citation_key") or Path(work_source.relative_path).stem)
            work_frontmatter[citation_key] = frontmatter
            concept_id = _work_concept_id(citation_key)
            work_concepts[citation_key] = concept_id
            title = str(frontmatter.get("title") or citation_key)
            concept_rows.append(
                {
                    "concept_id": concept_id,
                    "import_id": context.import_id,
                    "title": title,
                    "aliases": [citation_key],
                    "description": _work_description(frontmatter),
                    "source_artifact_ids": [artifact_by_path[work_source.relative_path]],
                    "current_status": "triaged",
                }
            )

            topic_values = [str(value) for value in frontmatter.get("topic_slugs", []) if str(value)]
            topic_slugs.update(topic_values)
            for slug in topic_values:
                relation_rows.append(
                    {
                        "relation_id": f"rel_citegeist_topic_{_safe_id(citation_key)}_{_safe_id(slug)}",
                        "import_id": context.import_id,
                        "source_id": concept_id,
                        "target_id": _topic_concept_id(slug),
                        "relation_type": "member_of_topic",
                        "evidence_ids": [],
                        "current_status": "triaged",
                    }
                )

            metadata_summary = _work_description(frontmatter)
            abstract = _extract_section(body, "Abstract")
            for index, (role, text, claim_kind) in enumerate(
                [
                    ("summary", metadata_summary, "bibliographic_summary"),
                    ("summary", abstract, "abstract_summary"),
                ],
                start=1,
            ):
                if not text:
                    continue
                observation_id = f"obs_citegeist_{_safe_id(citation_key)}_{index}"
                fragment_id = f"frag_citegeist_{_safe_id(citation_key)}_{index}"
                claim_id = f"clm_citegeist_{_safe_id(citation_key)}_{index}"
                fragment_rows.append(
                    {
                        "fragment_id": fragment_id,
                        "import_id": context.import_id,
                        "source_id": artifact_by_path[work_source.relative_path],
                        "text": text,
                        "section": "Metadata" if index == 1 else "Abstract",
                        "line_start": 0,
                        "line_end": 0,
                        "metadata": {"citation_key": citation_key, "okf_type": frontmatter.get("okf_type", "citegeist.work")},
                        "current_status": "draft",
                    }
                )
                observation_rows.append(
                    {
                        "observation_id": observation_id,
                        "import_id": context.import_id,
                        "artifact_id": artifact_by_path[work_source.relative_path],
                        "role": role,
                        "text": text,
                        "origin_path": work_source.relative_path,
                        "origin_section": "Metadata" if index == 1 else "Abstract",
                        "line_start": 0,
                        "line_end": 0,
                        "grounding_status": "grounded",
                        "support_kind": "direct_source",
                        "confidence_hint": 0.86 if index == 1 else 0.78,
                        "current_status": "draft",
                    }
                )
                claim_rows.append(
                    {
                        "claim_id": claim_id,
                        "import_id": context.import_id,
                        "claim_text": text,
                        "claim_kind": claim_kind,
                        "metadata": {
                            "citation_key": citation_key,
                            "doi": frontmatter.get("doi", ""),
                            "review_status": frontmatter.get("review_status", ""),
                            "okf_type": frontmatter.get("okf_type", "citegeist.work"),
                        },
                        "source_observation_ids": [observation_id],
                        "supporting_fragment_ids": [fragment_id],
                        "concept_ids": [concept_id],
                        "contradicts_claim_ids": [],
                        "supersedes_claim_ids": [],
                        "confidence_hint": 0.86 if index == 1 else 0.78,
                        "grounding_status": "grounded",
                        "current_status": "triaged",
                    }
                )

        for slug in topic_slugs:
            topic_id = _topic_concept_id(slug)
            if not any(row["concept_id"] == topic_id for row in concept_rows):
                concept_rows.append(
                    {
                        "concept_id": topic_id,
                        "import_id": context.import_id,
                        "title": slug.replace("-", " ").title(),
                        "aliases": [slug],
                        "description": "CiteGeist topic referenced by an OKF work page.",
                        "source_artifact_ids": [],
                        "current_status": "triaged",
                    }
                )

        for work_source in work_sources:
            frontmatter, body = _split_frontmatter(work_source.path.read_text(encoding="utf-8"))
            citation_key = str(frontmatter.get("citation_key") or Path(work_source.relative_path).stem)
            for relation_type, target_key in _extract_citation_links(body):
                if target_key not in work_concepts:
                    target_frontmatter = work_frontmatter.get(target_key, {})
                    work_concepts[target_key] = _work_concept_id(target_key)
                    concept_rows.append(
                        {
                            "concept_id": work_concepts[target_key],
                            "import_id": context.import_id,
                            "title": str(target_frontmatter.get("title") or target_key),
                            "aliases": [target_key],
                            "description": "CiteGeist citation target referenced by an OKF work page.",
                            "source_artifact_ids": [],
                            "current_status": "draft",
                        }
                    )
                relation_rows.append(
                    {
                        "relation_id": f"rel_citegeist_{relation_type}_{_safe_id(citation_key)}_{_safe_id(target_key)}",
                        "import_id": context.import_id,
                        "source_id": work_concepts[citation_key],
                        "target_id": work_concepts[target_key],
                        "relation_type": relation_type,
                        "evidence_ids": [],
                        "current_status": "triaged",
                    }
                )

        return StructuredImportRows(
            artifact_rows=artifact_rows,
            fragment_rows=fragment_rows,
            observation_rows=observation_rows,
            claim_rows=claim_rows,
            concept_rows=concept_rows,
            relation_rows=relation_rows,
        )


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    frontmatter = yaml.safe_load(text[4:end]) or {}
    return frontmatter if isinstance(frontmatter, dict) else {}, text[end + 4 :].lstrip()


def _extract_section(body: str, heading: str) -> str:
    section = _extract_raw_section(body, heading)
    return re.sub(r"\s+", " ", section).strip()


def _extract_raw_section(body: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return ""
    rest = body[match.end() :].strip()
    next_heading = re.search(r"^##\s+", rest, re.MULTILINE)
    section = rest[: next_heading.start()].strip() if next_heading else rest
    return section.strip()


def _extract_citation_links(body: str) -> list[tuple[str, str]]:
    section = _extract_raw_section(body, "Citation Graph")
    rows: list[tuple[str, str]] = []
    current_relation = "references"
    for line in section.splitlines():
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            current_relation = heading.group(1).strip().lower().replace(" ", "_")
            continue
        link = re.match(r"^-\s+\[([^\]]+)\]\([^)]+\)", line.strip())
        code = re.match(r"^-\s+`([^`]+)`", line.strip())
        if link:
            rows.append((current_relation, link.group(1).strip()))
        elif code:
            rows.append((current_relation, code.group(1).strip()))
    return rows


def _work_description(frontmatter: dict[str, Any]) -> str:
    title = str(frontmatter.get("title") or frontmatter.get("citation_key") or "Untitled work")
    year = str(frontmatter.get("year") or "").strip()
    entry_type = str(frontmatter.get("entry_type") or "work")
    doi = str(frontmatter.get("doi") or "").strip()
    authors = frontmatter.get("authors") or []
    author_text = ", ".join(str(author) for author in authors[:3]) if isinstance(authors, list) else str(authors)
    parts = [f"{title} is a CiteGeist {entry_type}"]
    if author_text:
        parts.append(f"by {author_text}")
    if year:
        parts.append(f"from {year}")
    text = " ".join(parts) + "."
    if doi:
        text += f" DOI: {doi}."
    return text


def _title_for_source(source: DiscoveredImportSource) -> str:
    if source.path.suffix == ".md":
        frontmatter, body = _split_frontmatter(source.path.read_text(encoding="utf-8"))
        if frontmatter.get("title"):
            return str(frontmatter["title"])
        for line in body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return source.path.stem


def _work_concept_id(citation_key: str) -> str:
    return f"concept::citegeist-work-{_safe_id(citation_key)}"


def _topic_concept_id(slug: str) -> str:
    return f"concept::citegeist-topic-{_safe_id(slug)}"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


register_source_adapter(CiteGeistOkfSourceAdapter())
