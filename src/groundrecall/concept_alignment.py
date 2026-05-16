from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

from .store import GroundRecallStore


STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "before",
    "from",
    "has",
    "have",
    "into",
    "not",
    "the",
    "this",
    "that",
    "their",
    "there",
    "they",
    "with",
    "without",
}


@dataclass(frozen=True)
class SeedConcept:
    concept_id: str
    title: str
    aliases: tuple[str, ...]
    description: str
    tokens: tuple[str, ...]


def align_claim_rows_to_seed_concepts(
    claim_rows: list[dict[str, Any]],
    seed_store_dir: str | Path,
    *,
    threshold: float = 0.55,
    max_matches_per_claim: int = 3,
) -> dict[str, Any]:
    seeds = load_seed_concepts(seed_store_dir)
    aligned_claim_count = 0
    external_concept_ids: set[str] = set()

    for claim in claim_rows:
        matches = best_seed_matches(str(claim.get("claim_text", "")), seeds, threshold=threshold, limit=max_matches_per_claim)
        if not matches:
            continue
        existing = list(claim.get("concept_ids", []))
        metadata = dict(claim.get("metadata", {}))
        alignment_rows = list(metadata.get("concept_seed_alignments", []))
        changed = False
        for match in matches:
            concept_id = match["concept_id"]
            if concept_id not in existing:
                existing.append(concept_id)
                external_concept_ids.add(concept_id)
                changed = True
            alignment_rows.append(match)
        if changed:
            aligned_claim_count += 1
            claim["concept_ids"] = existing
        metadata["concept_seed_alignments"] = alignment_rows
        metadata["concept_alignment_source"] = str(seed_store_dir)
        claim["metadata"] = metadata

    return {
        "seed_store_dir": str(seed_store_dir),
        "seed_concept_count": len(seeds),
        "aligned_claim_count": aligned_claim_count,
        "external_concept_ids": sorted(external_concept_ids),
        "threshold": threshold,
    }


def load_seed_concepts(seed_store_dir: str | Path) -> list[SeedConcept]:
    store = GroundRecallStore(seed_store_dir)
    seeds: list[SeedConcept] = []
    for concept in store.list_concepts():
        if concept.current_status not in {"reviewed", "promoted"}:
            continue
        tokens = tuple(_tokens(" ".join([concept.title, *concept.aliases, concept.description])))
        if not tokens:
            continue
        seeds.append(
            SeedConcept(
                concept_id=concept.concept_id,
                title=concept.title,
                aliases=tuple(concept.aliases),
                description=concept.description,
                tokens=tokens,
            )
        )
    return seeds


def best_seed_matches(text: str, seeds: list[SeedConcept], *, threshold: float, limit: int) -> list[dict[str, Any]]:
    normalized_text = _normalize_text(text)
    text_tokens = set(_tokens(text))
    scored: list[dict[str, Any]] = []
    for seed in seeds:
        score, matched_terms = _score_seed(normalized_text, text_tokens, seed)
        if score < threshold:
            continue
        scored.append(
            {
                "concept_id": seed.concept_id,
                "title": seed.title,
                "score": round(score, 3),
                "matched_terms": matched_terms,
            }
        )
    scored.sort(key=lambda item: (-float(item["score"]), item["concept_id"]))
    return scored[:limit]


def _score_seed(normalized_text: str, text_tokens: set[str], seed: SeedConcept) -> tuple[float, list[str]]:
    phrases = [seed.title, *seed.aliases]
    phrase_matches: list[str] = []
    for phrase in phrases:
        normalized_phrase = _normalize_text(phrase)
        if len(normalized_phrase) >= 8 and normalized_phrase in normalized_text:
            phrase_matches.append(phrase)
    if phrase_matches:
        return 1.0, phrase_matches

    seed_tokens = set(seed.tokens)
    if not seed_tokens:
        return 0.0, []
    matched = sorted(seed_tokens & text_tokens)
    if len(matched) < 2:
        return 0.0, matched
    token_ratio = len(matched) / len(seed_tokens)
    # Favor compact operational concepts with repeated terms such as "Notebook scaffold".
    score = min(0.9, token_ratio + min(len(matched) * 0.05, 0.2))
    return score, matched


def _normalize_text(text: str) -> str:
    return " ".join(_tokens(text))


def _tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9-]*", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOPWORDS]
