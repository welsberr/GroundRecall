from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

from .base import DiscoveredImportSource, StructuredImportRows, register_source_adapter


class DocliftBundleSourceAdapter:
    name = "doclift_bundle"
    _TRACK_STRATEGIES = ("conservative", "balanced", "broad")

    _PROSE_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
    _METADATA_PREFIXES = (
        "posted by",
        "share to ",
        "email this",
        "blogthis",
        "labels:",
        "post a comment",
        "older post",
        "newer post",
        "subscribe to",
        "copyright",
        "[last update",
        "this essay has been transferred here",
    )
    _TERMINAL_METADATA_PREFIXES = (
        "posted by",
        "comments",
        "post a comment",
        "newer post",
        "older post",
        "subscribe to",
        "email this",
        "blogthis",
        "share to ",
        "labels:",
    )
    _CLAIM_CUES = (
        " is ",
        " are ",
        " can ",
        " do ",
        " does ",
        " means ",
        " requires ",
        " due to ",
        " part of evolution",
        " fixed in a population",
        " by natural selection",
        " by random genetic drift",
        " over time",
    )
    _LEADIN_PREFIXES = (
        "some popular accounts give the impression",
        "perhaps they think",
        "perhaps they don't think",
        "i'm not sure how",
        "this is the important point",
        "it means that",
    )

    def _resolve_bundle_path(self, base: Path, value: str | Path | None) -> Path:
        if value is None:
            return Path()
        if isinstance(value, str) and not value.strip():
            return Path()
        path = Path(value)
        if not str(path):
            return Path()
        if path.is_absolute():
            return path
        return base / path

    def detect(self, root: str | Path) -> bool:
        base = Path(root)
        return (base / "manifest.json").exists() and (base / "documents").exists()

    def _load_chunks(self, base: Path, document: dict) -> list[dict]:
        explicit_path = document.get("chunks_path")
        if explicit_path:
            chunk_path = self._resolve_bundle_path(base, explicit_path)
        else:
            output_dir = self._resolve_bundle_path(base, document.get("output_dir"))
            chunk_path = output_dir / "document.chunks.json"
        if not chunk_path.exists():
            return []
        payload = json.loads(chunk_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            chunks = payload.get("chunks", [])
            return [chunk for chunk in chunks if isinstance(chunk, dict)]
        if isinstance(payload, list):
            return [chunk for chunk in payload if isinstance(chunk, dict)]
        return []

    def _load_markdown_text(self, base: Path, document: dict) -> str:
        markdown_path = self._resolve_bundle_path(base, document.get("markdown_path", ""))
        if not markdown_path.exists():
            return ""
        return markdown_path.read_text(encoding="utf-8")

    def _normalize_inline_text(self, value: str) -> str:
        text = value.replace("\xa0", " ")
        text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
        text = re.sub(r"\[[^\]]+\]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _looks_like_metadata_line(self, value: str) -> bool:
        lowered = value.strip().lower()
        if not lowered:
            return True
        if any(lowered.startswith(prefix) for prefix in self._METADATA_PREFIXES):
            return True
        if lowered in {"home", "sandwalk", "comments", "recent comments", "loading..."}:
            return True
        if "property='og:" in lowered or lowered.startswith("http"):
            return True
        return False

    def _is_terminal_metadata_line(self, value: str) -> bool:
        lowered = value.strip().lower()
        if not lowered:
            return False
        if any(lowered.startswith(prefix) for prefix in self._TERMINAL_METADATA_PREFIXES):
            return True
        if re.match(r"^\d+\s+comments\b", lowered):
            return True
        return False

    def _is_claim_candidate(self, cleaned: str, *, title: str = "", strategy: str = "conservative") -> bool:
        lowered = cleaned.lower()
        normalized_title = self._normalize_inline_text(title).lower()
        if strategy == "conservative":
            min_length = 70
        elif strategy == "balanced":
            min_length = 50
        else:
            min_length = 40
        if len(cleaned) < min_length:
            return False
        if strategy == "conservative" and len(cleaned) > 360:
            return False
        if strategy == "balanced" and len(cleaned) > 320:
            return False
        if strategy == "broad" and len(cleaned) > 520:
            return False
        if any(lowered.startswith(prefix) for prefix in self._METADATA_PREFIXES):
            return False
        if "?" in cleaned:
            return False
        if any(lowered.startswith(prefix) for prefix in self._LEADIN_PREFIXES):
            return False
        if normalized_title and lowered == normalized_title:
            return False
        if cleaned.count(" ") < 8:
            return False
        if strategy in {"balanced", "conservative"} and cleaned[:1].islower():
            return False
        if not cleaned.endswith((".", "!", "?", '"')):
            return False
        return True

    def _claim_priority(self, cleaned: str, *, strategy: str = "conservative") -> tuple[int, int]:
        lowered = cleaned.lower()
        cue_hits = sum(1 for cue in self._CLAIM_CUES if cue in lowered)
        penalties = 0
        if lowered.startswith(("the latest issue", "this is a brief introduction", "mistakes permeate")):
            penalties += 1
        if '"' in cleaned:
            penalties += 1
        if strategy == "balanced":
            return (cue_hits - penalties, -abs(len(cleaned) - 140))
        return (cue_hits - penalties, -len(cleaned))

    def _meta_noise_count(self, claims: list[str]) -> int:
        count = 0
        for claim in claims:
            lowered = claim.lower()
            if any(lowered.startswith(prefix) for prefix in self._METADATA_PREFIXES):
                count += 1
            if lowered.startswith(("the latest issue", "this is a brief introduction", "mistakes permeate")):
                count += 1
        return count

    def _truncated_claim_count(self, claims: list[str]) -> int:
        truncated = 0
        bad_endings = (" and", " of", " to", " in", " by", " with", " that", " this")
        for claim in claims:
            stripped = claim.strip()
            lowered = stripped.lower()
            if not stripped.endswith((".", "!", "?", '"')):
                truncated += 1
                continue
            if any(lowered.endswith(ending) for ending in bad_endings):
                truncated += 1
        return truncated

    def _redundancy_penalty(self, claims: list[str]) -> float:
        penalty = 0.0
        normalized = [set(re.findall(r"[a-z0-9]+", claim.lower())) for claim in claims]
        for i, left in enumerate(normalized):
            for right in normalized[i + 1 :]:
                if not left or not right:
                    continue
                overlap = len(left & right) / len(left | right)
                if overlap >= 0.6:
                    penalty += overlap
        return penalty

    def _score_claim_batch(self, claims: list[str], *, strategy: str) -> tuple[float, float, float, float, float]:
        if not claims:
            return (-999.0, -999.0, -999.0, -999.0, -999.0)
        cue_score = 0.0
        for claim in claims:
            cue_score += self._claim_priority(claim, strategy=strategy)[0]
        avg_cue_score = cue_score / len(claims)
        meta_penalty = float(self._meta_noise_count(claims))
        truncated_penalty = float(self._truncated_claim_count(claims))
        redundancy_penalty = self._redundancy_penalty(claims)
        avg_length = sum(len(claim) for claim in claims) / len(claims)
        target_count = {
            "conservative": 3,
            "balanced": 5,
            "broad": 6,
        }.get(strategy, 4)
        target_length = {
            "conservative": 150,
            "balanced": 100,
            "broad": 180,
        }.get(strategy, 140)
        count_penalty = abs(len(claims) - target_count)
        length_penalty = abs(avg_length - target_length) / 100.0
        strategy_bias = {
            "balanced": 0.35,
            "conservative": 0.0,
            "broad": -0.15,
        }.get(strategy, 0.0)
        return (
            avg_cue_score + strategy_bias - meta_penalty - truncated_penalty - redundancy_penalty,
            -count_penalty,
            -(length_penalty + truncated_penalty + redundancy_penalty),
            -meta_penalty,
            -abs(avg_length - target_length),
        )

    def _strategy_total_score(self, score: tuple[float, float, float, float, float]) -> float:
        primary, count_fit, quality_fit, meta_fit, length_fit = score
        return (0.5 * primary) + (0.8 * count_fit) + (1.2 * quality_fit) + (0.5 * meta_fit) + (0.03 * length_fit)

    def _extract_claim_sentences_from_paragraphs(
        self,
        paragraphs: list[str],
        *,
        title: str = "",
        limit: int = 4,
        strategy: str = "conservative",
    ) -> list[str]:
        claims: list[str] = []
        seen: set[str] = set()
        candidates: list[tuple[str, tuple[int, int]]] = []
        for paragraph in paragraphs:
            normalized_paragraph = self._normalize_inline_text(paragraph)
            if len(normalized_paragraph) < 80:
                continue
            if strategy == "broad":
                paragraph_key = normalized_paragraph.lower()
                if self._is_claim_candidate(normalized_paragraph, title=title, strategy=strategy) and paragraph_key not in seen:
                    seen.add(paragraph_key)
                    claims.append(normalized_paragraph)
                    if len(claims) >= limit:
                        return claims
            for sentence in self._PROSE_SENTENCE_SPLIT.split(normalized_paragraph):
                cleaned = self._normalize_inline_text(sentence)
                lowered = cleaned.lower()
                if not self._is_claim_candidate(cleaned, title=title, strategy=strategy):
                    continue
                if lowered in seen:
                    continue
                seen.add(lowered)
                if strategy == "balanced":
                    candidates.append((cleaned, self._claim_priority(cleaned, strategy=strategy)))
                else:
                    claims.append(cleaned)
                    if len(claims) >= limit:
                        return claims
        if strategy == "balanced":
            ranked = sorted(candidates, key=lambda item: item[1], reverse=True)
            return [item[0] for item in ranked[:limit]]
        return claims

    def _extract_claim_sentences(self, markdown_text: str, *, title: str = "", limit: int = 4, strategy: str = "conservative") -> list[str]:
        paragraphs: list[str] = []
        current: list[str] = []
        for raw_line in markdown_text.splitlines():
            line = raw_line.strip()
            if not line:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            if self._is_terminal_metadata_line(line):
                if current:
                    paragraphs.append(" ".join(current))
                break
            if line.startswith("#") or line.startswith("![") or line.startswith("|"):
                continue
            if self._looks_like_metadata_line(line):
                continue
            if len(line) < 40:
                continue
            current.append(line)
        if current:
            paragraphs.append(" ".join(current))
        if strategy == "broad":
            broad_claims = self._extract_claim_sentences_from_paragraphs(
                paragraphs,
                title=title,
                limit=max(limit * 2, limit),
                strategy="broad",
            )
            if len(broad_claims) >= limit:
                return broad_claims[:limit]
            return broad_claims
        return self._extract_claim_sentences_from_paragraphs(
            paragraphs,
            title=title,
            limit=limit,
            strategy=strategy,
        )

    def extract_document_claims(
        self,
        base: Path,
        document: dict,
        *,
        strategy: str = "conservative",
        limit: int = 4,
    ) -> list[str]:
        if strategy == "auto":
            selected = self.select_document_claim_strategy(base, document, limit=limit)
            return self.extract_document_claims(base, document, strategy=selected, limit=limit)
        markdown_text = self._load_markdown_text(base, document)
        title = str(document.get("title") or "")
        return self._extract_claim_sentences(markdown_text, title=title, limit=limit, strategy=strategy)

    def select_document_claim_strategy(self, base: Path, document: dict, *, limit: int = 4) -> str:
        candidates: list[tuple[str, tuple[float, float, float, float, float]]] = []
        for strategy in self._TRACK_STRATEGIES:
            claims = self.extract_document_claims(base, document, strategy=strategy, limit=limit)
            candidates.append((strategy, self._score_claim_batch(claims, strategy=strategy)))
        return max(candidates, key=lambda item: self._strategy_total_score(item[1]))[0]

    def select_bundle_claim_strategy(self, base: Path, documents: list[dict], *, limit: int = 4) -> str:
        candidate_docs = [
            document
            for document in documents
            if str(document.get("document_kind") or "").strip() in {"web_article", "document"}
        ]
        if not candidate_docs:
            return "conservative"
        scored: list[tuple[str, tuple[float, float, float, float, float]]] = []
        for strategy in self._TRACK_STRATEGIES:
            total = [0.0, 0.0, 0.0, 0.0, 0.0]
            used = 0
            for document in candidate_docs[:6]:
                claims = self.extract_document_claims(base, document, strategy=strategy, limit=limit)
                score = self._score_claim_batch(claims, strategy=strategy)
                if score[0] <= -999.0:
                    continue
                total = [left + right for left, right in zip(total, score)]
                used += 1
            if used:
                averaged = tuple(value / used for value in total)
            else:
                averaged = (-999.0, -999.0, -999.0, -999.0, -999.0)
            scored.append((strategy, averaged))
        return max(scored, key=lambda item: self._strategy_total_score(item[1]))[0]

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

    def build_rows(self, context, sources: list[DiscoveredImportSource], root: Path | None = None) -> StructuredImportRows | None:
        base = Path(root) if root is not None else Path(context.source_root)
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
        fragment_rows: list[dict] = []
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
        bundle_claim_strategy = self.select_bundle_claim_strategy(base, documents)
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
            if figures_path.is_file():
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
            document_claim_ids: list[str] = []
            for chunk_index, chunk in enumerate(self._load_chunks(base, document), start=1):
                chunk_text = str(chunk.get("text") or "").strip()
                if not chunk_text:
                    continue
                chunk_role = str(chunk.get("role") or "summary")
                chunk_section = str(chunk.get("section") or title)
                line_start = int(chunk.get("line_start") or 0)
                line_end = int(chunk.get("line_end") or line_start)
                fragment_id = f"frag_doclift_{index}_{chunk_index}"
                observation_id = f"obs_doclift_{index}_{chunk_index}"
                fragment_rows.append(
                    {
                        "fragment_id": fragment_id,
                        "import_id": context.import_id,
                        "source_id": artifact_id,
                        "text": chunk_text,
                        "section": chunk_section,
                        "line_start": line_start,
                        "line_end": line_end,
                        "metadata": {
                            "chunk_id": chunk.get("chunk_id", f"{document.get('document_id', index)}-{chunk_index}"),
                            "source_kind": "doclift_chunk",
                        },
                        "current_status": "draft",
                    }
                )
                observation_rows.append(
                    {
                        "observation_id": observation_id,
                        "import_id": context.import_id,
                        "artifact_id": artifact_id,
                        "role": chunk_role,
                        "text": chunk_text,
                        "origin_path": relative_markdown,
                        "origin_section": chunk_section,
                        "line_start": line_start,
                        "line_end": line_end,
                        "source_url": source_path,
                        "metadata": {
                            "source_path_kind": source_path_kind,
                            "chunk_id": chunk.get("chunk_id", f"{document.get('document_id', index)}-{chunk_index}"),
                        },
                        "grounding_status": "grounded",
                        "support_kind": "direct_source",
                        "confidence_hint": float(chunk.get("confidence_hint") or 0.75),
                        "current_status": "draft",
                    }
                )
                if chunk_role in {"claim", "summary"}:
                    claim_id = f"clm_doclift_{index}_{chunk_index}"
                    claim_rows.append(
                        {
                            "claim_id": claim_id,
                            "import_id": context.import_id,
                            "claim_text": chunk_text,
                            "claim_kind": "statement" if chunk_role == "claim" else "summary",
                            "source_observation_ids": [observation_id],
                            "supporting_fragment_ids": [fragment_id],
                            "concept_ids": [concept_id],
                            "contradicts_claim_ids": [],
                            "supersedes_claim_ids": [],
                            "confidence_hint": float(chunk.get("confidence_hint") or 0.75),
                            "grounding_status": "grounded",
                            "current_status": "triaged",
                        }
                    )
                    document_claim_ids.append(claim_id)
            if not document_claim_ids and str(document.get("document_kind") or "").strip() in {"web_article", "document"}:
                selected_strategy = bundle_claim_strategy
                for derived_index, claim_text in enumerate(self.extract_document_claims(base, document, strategy=selected_strategy), start=1):
                    derived_observation_id = f"obs_doclift_{index}_derived_{derived_index}"
                    claim_id = f"clm_doclift_{index}_derived_{derived_index}"
                    observation_rows.append(
                        {
                            "observation_id": derived_observation_id,
                            "import_id": context.import_id,
                            "artifact_id": artifact_id,
                            "role": "claim",
                            "text": claim_text,
                            "origin_path": relative_markdown,
                            "origin_section": title,
                            "line_start": 0,
                            "line_end": 0,
                            "source_url": source_path,
                            "metadata": {
                                "source_path_kind": source_path_kind,
                                "derived_from": "markdown_sentence",
                                "claim_strategy": selected_strategy,
                            },
                            "grounding_status": "grounded",
                            "support_kind": "direct_source",
                            "confidence_hint": 0.65,
                            "current_status": "draft",
                        }
                    )
                    claim_rows.append(
                        {
                            "claim_id": claim_id,
                            "import_id": context.import_id,
                            "claim_text": claim_text,
                            "claim_kind": "statement",
                            "source_observation_ids": [derived_observation_id],
                            "supporting_fragment_ids": [],
                            "concept_ids": [concept_id],
                            "contradicts_claim_ids": [],
                            "supersedes_claim_ids": [],
                            "confidence_hint": 0.65,
                            "grounding_status": "grounded",
                            "current_status": "triaged",
                        }
                    )
                    document_claim_ids.append(claim_id)
            if not document_claim_ids:
                fallback_claim_id = f"clm_doclift_{index}"
                claim_rows.append(
                    {
                        "claim_id": fallback_claim_id,
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
                document_claim_ids.append(fallback_claim_id)
            if previous_concept_id is not None:
                relation_rows.append(
                    {
                        "relation_id": f"rel_doclift_seq_{index}",
                        "import_id": context.import_id,
                        "source_id": previous_concept_id,
                        "target_id": concept_id,
                        "relation_type": "references",
                        "evidence_ids": document_claim_ids[:1],
                        "current_status": "draft",
                    }
                )
            previous_concept_id = concept_id

        return StructuredImportRows(
            artifact_rows=artifact_rows,
            fragment_rows=fragment_rows,
            observation_rows=observation_rows,
            claim_rows=claim_rows,
            concept_rows=concept_rows,
            relation_rows=relation_rows,
        )


register_source_adapter(DocliftBundleSourceAdapter())
