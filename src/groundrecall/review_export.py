from __future__ import annotations
from pathlib import Path
import hashlib
import json, yaml
import re
import sys
from collections import defaultdict
from typing import Any, Callable
from .citation_support import bibliography_summary_payload, load_bibliography_index, serialize_bib_entry
from .review_schema import CitationReviewEntry, ReviewSession

def export_review_state_json(session: ReviewSession, path: str | Path) -> None:
    Path(path).write_text(session.model_dump_json(indent=2), encoding="utf-8")

def export_promoted_pack(session: ReviewSession, outdir: str | Path) -> None:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    promoted_pack = dict(session.draft_pack.pack)
    promoted_pack["version"] = str(promoted_pack.get("version", "0.1.0-draft")).replace("-draft", "-reviewed")
    promoted_pack["curation"] = {"reviewer": session.reviewer, "ledger_entries": len(session.ledger)}

    concepts = []
    for concept in session.draft_pack.concepts:
        if concept.status == "rejected":
            continue
        concepts.append({
            "id": concept.concept_id,
            "title": concept.title,
            "description": concept.description,
            "prerequisites": concept.prerequisites,
            "mastery_signals": concept.mastery_signals,
            "status": concept.status,
            "notes": concept.notes,
            "mastery_profile": {},
        })

    (outdir / "pack.yaml").write_text(yaml.safe_dump(promoted_pack, sort_keys=False), encoding="utf-8")
    (outdir / "concepts.yaml").write_text(yaml.safe_dump({"concepts": concepts}, sort_keys=False), encoding="utf-8")
    (outdir / "review_ledger.json").write_text(json.dumps(session.model_dump(), indent=2), encoding="utf-8")
    (outdir / "license_attribution.json").write_text(json.dumps(session.draft_pack.attribution, indent=2), encoding="utf-8")


def export_promoted_pack_to_course_repo(session: ReviewSession, course_repo: str | Path, outdir: str | Path | None = None) -> Path:
    from .course_repo import resolve_course_repo

    resolved = resolve_course_repo(course_repo)
    target = Path(outdir) if outdir is not None else Path(resolved.generated_pack_dir or (Path(resolved.repo_root) / "generated" / "pack"))
    export_promoted_pack(session, target)
    return target


LATEX_CITE_RE = re.compile(r"\\cite[a-zA-Z*]*(?:\[[^\]]*\])?(?:\[[^\]]*\])?\{([^}]+)\}")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _status_field_spec() -> dict[str, Any]:
    return {
        "field": "status",
        "label": "Review status",
        "input": "select",
        "required": True,
        "options": [
            {
                "value": "trusted",
                "label": "Trusted",
                "help": "Promote this concept and its supported claims when the evidence and wording are ready.",
            },
            {
                "value": "provisional",
                "label": "Provisional",
                "help": "Keep this concept in reviewed state when it is promising but still needs citation or wording cleanup.",
            },
            {
                "value": "needs_review",
                "label": "Needs Review",
                "help": "Leave undecided when support, scope, or concept boundaries are still unclear.",
            },
            {
                "value": "rejected",
                "label": "Rejected",
                "help": "Exclude this concept when it is noise, unsupported, duplicated, or misleading.",
            },
        ],
    }


def _text_field_spec(field: str, label: str, help_text: str, *, multiline: bool = False) -> dict[str, Any]:
    return {
        "field": field,
        "label": label,
        "input": "textarea" if multiline else "text",
        "required": False,
        "help": help_text,
    }


def _citation_status_field_spec() -> dict[str, Any]:
    return {
        "field": "status",
        "label": "Citation review status",
        "input": "select",
        "required": True,
        "options": [
            {
                "value": "unreviewed",
                "label": "Unreviewed",
                "help": "Keep this citation candidate in triage until fit and existence are checked.",
            },
            {
                "value": "verified",
                "label": "Verified",
                "help": "The cited work exists and materially supports the associated manuscript claim.",
            },
            {
                "value": "needs_source_check",
                "label": "Needs Source Check",
                "help": "The citation may be useful but still needs direct source inspection or metadata cleanup.",
            },
            {
                "value": "misleading",
                "label": "Misleading",
                "help": "The citation exists but overstates, contradicts, or poorly fits the claim.",
            },
            {
                "value": "irrelevant",
                "label": "Irrelevant",
                "help": "The citation does not materially support the concept or claim under review.",
            },
            {
                "value": "fabricated",
                "label": "Fabricated",
                "help": "The citation appears invented, malformed, or otherwise not real.",
            },
        ],
    }


def _load_citegeist_extract() -> tuple[Callable[[str], list[Any]] | None, list[str]]:
    citegeist_src = Path("/home/netuser/bin/CiteGeist/src")
    if citegeist_src.exists():
        sys.path.insert(0, str(citegeist_src))
    try:
        from citegeist import available_extraction_backends, extract_references  # type: ignore
    except Exception:
        return None, []
    return extract_references, list(available_extraction_backends())


def _extract_citation_keys(text: str) -> list[str]:
    keys: list[str] = []
    for raw_group in LATEX_CITE_RE.findall(text):
        keys.extend(part.strip() for part in raw_group.split(",") if part.strip())
    return sorted(set(keys))


def _resolve_source_root(import_dir: Path, source_root: str) -> str:
    if not source_root:
        return ""
    root = Path(source_root)
    if root.is_absolute():
        return str(root)
    return str((import_dir.parent.parent / root).resolve())


def _artifact_citation_payloads(
    artifacts: list[dict[str, Any]],
    *,
    source_root: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    extract_references, backends = _load_citegeist_extract()
    artifact_payloads: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {}
    root = Path(source_root) if source_root else None
    bibliography_index = load_bibliography_index(source_root) if source_root else {}

    for artifact in artifacts:
        path = Path(source_root) / artifact["path"] if root is not None else None
        raw_text = ""
        if path is not None and path.exists():
            try:
                raw_text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw_text = ""
        citation_keys = _extract_citation_keys(raw_text) if raw_text else []
        extracted_refs: list[dict[str, Any]] = []
        if extract_references is not None and raw_text:
            try:
                for entry in extract_references(raw_text):
                    extracted_refs.append(
                        {
                            "citation_key": "",
                            "entry_type": entry.entry_type,
                            "title": entry.fields.get("title", ""),
                            "author": entry.fields.get("author", ""),
                            "year": entry.fields.get("year", ""),
                            "venue": entry.fields.get("journal", "") or entry.fields.get("booktitle", ""),
                        }
                    )
            except Exception:
                extracted_refs = []

        payload = {
            "artifact_id": artifact["artifact_id"],
            "path": artifact["path"],
            "title": artifact.get("title", ""),
            "citation_keys": citation_keys,
            "resolved_entries": [serialize_bib_entry(bibliography_index.get(key)) for key in citation_keys if bibliography_index.get(key)],
            "citation_key_count": len(citation_keys),
            "extracted_references": extracted_refs[:12],
            "extracted_reference_count": len(extracted_refs),
            "citegeist_backends": backends,
        }
        artifact_payloads.append(payload)
        summaries[artifact["artifact_id"]] = {
            "citation_key_count": len(citation_keys),
            "extracted_reference_count": len(extracted_refs),
            "has_citation_support": bool(citation_keys or extracted_refs),
        }
    return artifact_payloads, summaries


def build_citation_review_entries_from_import(import_dir: str | Path) -> list[CitationReviewEntry]:
    base = Path(import_dir)
    manifest = _read_json(base / "manifest.json")
    resolved_source_root = _resolve_source_root(base, manifest.get("source_root", ""))
    artifacts = _read_jsonl(base / "artifacts.jsonl")
    observations = _read_jsonl(base / "observations.jsonl")
    claims = _read_jsonl(base / "claims.jsonl")
    bibliography_index = load_bibliography_index(resolved_source_root)

    artifact_payloads, _ = _artifact_citation_payloads(
        artifacts,
        source_root=resolved_source_root,
    )
    observations_by_id = {item["observation_id"]: item for item in observations}
    artifact_claim_links: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"claim_ids": set(), "concept_ids": set()})

    for claim in claims:
        artifact_ids = {
            observations_by_id[item]["artifact_id"]
            for item in claim.get("source_observation_ids", [])
            if item in observations_by_id and observations_by_id[item].get("artifact_id")
        }
        for artifact_id in artifact_ids:
            artifact_claim_links[artifact_id]["claim_ids"].add(claim["claim_id"])
            artifact_claim_links[artifact_id]["concept_ids"].update(
                concept_id.replace("concept::", "", 1) for concept_id in claim.get("concept_ids", [])
            )

    entries: list[CitationReviewEntry] = []
    for artifact in artifact_payloads:
        link_payload = artifact_claim_links.get(artifact["artifact_id"], {"claim_ids": set(), "concept_ids": set()})
        for citation_key in artifact.get("citation_keys", []):
            digest = hashlib.sha1(f"{artifact['artifact_id']}|key|{citation_key}".encode("utf-8")).hexdigest()[:12]
            bib_entry = bibliography_index.get(citation_key, {})
            fields = bib_entry.get("fields", {})
            entries.append(
                CitationReviewEntry(
                    citation_review_id=f"citrev-{digest}",
                    artifact_id=artifact["artifact_id"],
                    artifact_path=artifact.get("path", ""),
                    artifact_title=artifact.get("title", ""),
                    source_kind="citation_key",
                    locator=artifact.get("path", ""),
                    citation_key=citation_key,
                    title=str(fields.get("title", "")),
                    author=str(fields.get("author", "")),
                    year=str(fields.get("year", "")),
                    venue=str(fields.get("journal", "") or fields.get("booktitle", "") or fields.get("publisher", "")),
                    source_bib_path=str(bib_entry.get("source_bib_path", "")),
                    raw_bibtex=str(bib_entry.get("raw_bibtex", "")),
                    related_concept_ids=sorted(link_payload["concept_ids"]),
                    related_claim_ids=sorted(link_payload["claim_ids"]),
                )
            )
        for index, reference in enumerate(artifact.get("extracted_references", []), start=1):
            digest = hashlib.sha1(
                f"{artifact['artifact_id']}|ref|{reference.get('title', '')}|{reference.get('author', '')}|{index}".encode("utf-8")
            ).hexdigest()[:12]
            entries.append(
                CitationReviewEntry(
                    citation_review_id=f"citrev-{digest}",
                    artifact_id=artifact["artifact_id"],
                    artifact_path=artifact.get("path", ""),
                    artifact_title=artifact.get("title", ""),
                    source_kind="extracted_reference",
                    locator=f"{artifact.get('path', '')}#ref-{index}",
                    citation_key="",
                    title=reference.get("title", ""),
                    author=reference.get("author", ""),
                    year=reference.get("year", ""),
                    venue=reference.get("venue", ""),
                    related_concept_ids=sorted(link_payload["concept_ids"]),
                    related_claim_ids=sorted(link_payload["claim_ids"]),
                )
            )
    return entries


def _build_import_review_payload(session: ReviewSession, import_dir: Path) -> dict[str, Any]:
    manifest = _read_json(import_dir / "manifest.json")
    resolved_source_root = _resolve_source_root(import_dir, manifest.get("source_root", ""))
    lint_payload = _read_json(import_dir / "lint_findings.json")
    queue_payload = _read_json(import_dir / "review_queue.json")
    artifacts = _read_jsonl(import_dir / "artifacts.jsonl")
    observations = _read_jsonl(import_dir / "observations.jsonl")
    claims = _read_jsonl(import_dir / "claims.jsonl")

    observations_by_id = {item["observation_id"]: item for item in observations}
    claims_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    findings_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in lint_payload.get("findings", []):
        findings_by_target[finding["target_id"]].append(finding)
    for claim in claims:
        for concept_id in claim.get("concept_ids", []):
            claims_by_concept[concept_id].append(claim)

    artifact_citations, artifact_citation_summary = _artifact_citation_payloads(
        artifacts,
        source_root=resolved_source_root,
    )
    artifact_by_id = {item["artifact_id"]: item for item in artifacts}

    concept_reviews: list[dict[str, Any]] = []
    for concept in session.draft_pack.concepts:
        full_concept_id = f"concept::{concept.concept_id}" if not concept.concept_id.startswith("concept::") else concept.concept_id
        concept_claims = claims_by_concept.get(full_concept_id, [])
        claim_payloads: list[dict[str, Any]] = []
        has_citation_support = False
        for claim in concept_claims[:25]:
            supporting_observations = [observations_by_id[item] for item in claim.get("source_observation_ids", []) if item in observations_by_id]
            artifact_ids = {item["artifact_id"] for item in supporting_observations}
            citation_support = [artifact_citation_summary.get(artifact_id, {}) for artifact_id in artifact_ids]
            has_citation_support = has_citation_support or any(item.get("has_citation_support") for item in citation_support)
            claim_payloads.append(
                {
                    "claim_id": claim["claim_id"],
                    "claim_text": claim.get("claim_text", ""),
                    "claim_kind": claim.get("claim_kind", ""),
                    "grounding_status": claim.get("grounding_status", "unknown"),
                    "supporting_observations": [
                        {
                            "observation_id": obs["observation_id"],
                            "origin_path": obs.get("origin_path", ""),
                            "origin_section": obs.get("origin_section", ""),
                            "text": obs.get("text", ""),
                            "line_start": obs.get("line_start", 0),
                            "line_end": obs.get("line_end", 0),
                        }
                        for obs in supporting_observations
                    ],
                    "citation_support": citation_support,
                    "artifact_paths": [artifact_by_id[item]["path"] for item in artifact_ids if item in artifact_by_id],
                    "finding_messages": [item["message"] for item in findings_by_target.get(claim["claim_id"], [])],
                }
            )

        concept_reviews.append(
            {
                "concept_id": concept.concept_id,
                "title": concept.title,
                "status": concept.status,
                "description": concept.description,
                "review_help": (
                    "Prefer `trusted` when claims are coherent and citation-bearing support is appropriate; "
                    "prefer `provisional` when the concept is plausible but still needs citation or wording cleanup."
                ),
                "claim_count": len(concept_claims),
                "grounded_claim_count": sum(1 for item in concept_claims if item.get("grounding_status") == "grounded"),
                "warning_count": len(findings_by_target.get(full_concept_id, [])),
                "has_citation_support": has_citation_support,
                "top_claims": claim_payloads,
                "notes": list(concept.notes),
            }
        )

    return {
        "import_context": {
            "manifest": manifest,
            "lint_summary": lint_payload.get("summary", {}),
            "queue_length": queue_payload.get("queue_length", 0),
            "source_adapter": manifest.get("source_adapter", ""),
        },
        "review_guidance": {
            "overview": (
                "Review concepts first, then inspect representative claims and their source observations before promotion."
            ),
            "priorities": [
                "Focus reviewer effort on concepts with strong grounded claims and explicit citations first.",
                "Downgrade or reject concepts whose claims are fragmented, duplicated, or missing meaningful support.",
                "For academic material, citation-bearing claims deserve special scrutiny for fit, contradiction, and fabrication risk.",
            ],
            "citation_guidance": [
                "A citation key or extracted reference is evidence of traceability, not correctness.",
                "Check whether the cited work actually supports the claim and whether the claim overstates it.",
                "Use the citation track to prioritize claims that can move into a separate citation-ingestion workflow.",
            ],
        },
        "field_specs": [
            _status_field_spec(),
            _text_field_spec("description", "Concept description", "Refine the concept summary to match the strongest supported interpretation."),
            _text_field_spec("notes", "Reviewer notes", "Record why this concept is trusted, provisional, rejected, or still unclear.", multiline=True),
            _text_field_spec("prerequisites", "Prerequisites", "List prerequisite concepts only when the manuscript support is explicit or defensible.", multiline=True),
        ],
        "citation_field_specs": [
            _citation_status_field_spec(),
            _text_field_spec("notes", "Citation notes", "Record whether the cited work exists, fits the claim, or should move into a dedicated citation-ingestion lane.", multiline=True),
        ],
        "concept_reviews": concept_reviews,
        "citation_reviews": [entry.model_dump() for entry in session.citation_reviews],
        "bibliography": bibliography_summary_payload(manifest.get("source_root", "")),
        "citations": {
            "enabled": True,
            "provider": "citegeist" if artifact_citations and artifact_citations[0].get("citegeist_backends") else "none",
            "artifacts": artifact_citations,
            "summary": {
                "artifact_count_with_citations": sum(1 for item in artifact_citations if item["citation_key_count"] or item["extracted_reference_count"]),
                "citation_key_total": sum(item["citation_key_count"] for item in artifact_citations),
                "extracted_reference_total": sum(item["extracted_reference_count"] for item in artifact_citations),
            },
            "next_actions": [
                "Promote citation-bearing claims into a dedicated citation review lane.",
                "Use CiteGeist extraction as a first pass, then verify support and metadata before trusting the citation.",
            ],
        },
    }


def export_review_ui_data(session: ReviewSession, outdir: str | Path, import_dir: str | Path | None = None) -> None:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "reviewer": session.reviewer,
        "draft_pack": session.draft_pack.model_dump(),
        "citation_reviews": [entry.model_dump() for entry in session.citation_reviews],
        "ledger": [entry.model_dump() for entry in session.ledger],
    }
    if import_dir is not None:
        payload.update(_build_import_review_payload(session, Path(import_dir)))
    (outdir / "review_data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
