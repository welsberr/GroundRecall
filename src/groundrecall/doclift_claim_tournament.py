from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .groundrecall_source_adapters.doclift_bundle import DocliftBundleSourceAdapter


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_META_PATTERNS = (
    "is a web_article in the imported doclift bundle",
    "is a bibliography_topic in the imported doclift bundle",
    "this essay has been transferred here",
)


@dataclass
class ClaimTrackScore:
    strategy: str
    predicted_claims: list[str]
    gold_claims: list[str]
    matches: int
    precision: float
    recall: float
    f1: float
    meta_noise: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "predicted_claims": list(self.predicted_claims),
            "gold_claims": list(self.gold_claims),
            "matches": self.matches,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "meta_noise": self.meta_noise,
        }


def _normalize_tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _claim_overlap(a: str, b: str) -> float:
    left = _normalize_tokens(a)
    right = _normalize_tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _is_meta_noise(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _META_PATTERNS)


def _score_track(predicted_claims: list[str], gold_claims: list[str], strategy: str) -> ClaimTrackScore:
    matched_gold: set[int] = set()
    matches = 0
    for predicted in predicted_claims:
        best_index = None
        best_score = 0.0
        for index, gold in enumerate(gold_claims):
            if index in matched_gold:
                continue
            overlap = _claim_overlap(predicted, gold)
            if overlap > best_score:
                best_score = overlap
                best_index = index
        if best_index is not None and best_score >= 0.34:
            matched_gold.add(best_index)
            matches += 1

    precision = matches / len(predicted_claims) if predicted_claims else 0.0
    recall = matches / len(gold_claims) if gold_claims else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0
    meta_noise = sum(1 for claim in predicted_claims if _is_meta_noise(claim))
    return ClaimTrackScore(
        strategy=strategy,
        predicted_claims=predicted_claims,
        gold_claims=gold_claims,
        matches=matches,
        precision=precision,
        recall=recall,
        f1=f1,
        meta_noise=meta_noise,
    )


def _winner_key(score: ClaimTrackScore) -> tuple[float, float, float, float]:
    return (
        score.f1,
        score.recall,
        -float(score.meta_noise),
        -abs(len(score.predicted_claims) - len(score.gold_claims)),
    )


def evaluate_doclift_claim_tracks(bundle_root: str | Path, benchmark_path: str | Path) -> dict[str, Any]:
    base = Path(bundle_root)
    benchmark = json.loads(Path(benchmark_path).read_text(encoding="utf-8"))
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    adapter = DocliftBundleSourceAdapter()
    documents = {str(item.get("document_id")): item for item in manifest.get("documents", []) if isinstance(item, dict)}

    per_document: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, float]] = {
        "conservative": {"matches": 0.0, "predicted": 0.0, "gold": 0.0, "meta_noise": 0.0},
        "broad": {"matches": 0.0, "predicted": 0.0, "gold": 0.0, "meta_noise": 0.0},
    }

    for entry in benchmark.get("documents", []):
        document_id = str(entry["document_id"])
        document = documents[document_id]
        gold_claims = [str(item).strip() for item in entry.get("gold_claims", []) if str(item).strip()]
        track_scores = []
        for strategy in ("conservative", "broad"):
            predicted_claims = adapter.extract_document_claims(base, document, strategy=strategy, limit=6)
            score = _score_track(predicted_claims, gold_claims, strategy)
            track_scores.append(score)
            aggregate[strategy]["matches"] += score.matches
            aggregate[strategy]["predicted"] += len(score.predicted_claims)
            aggregate[strategy]["gold"] += len(score.gold_claims)
            aggregate[strategy]["meta_noise"] += score.meta_noise
        winner = max(track_scores, key=_winner_key)
        per_document.append(
            {
                "document_id": document_id,
                "title": str(document.get("title") or ""),
                "winner": winner.strategy,
                "tracks": [score.as_dict() for score in track_scores],
            }
        )

    judge_summary: dict[str, Any] = {"tracks": {}}
    for strategy, totals in aggregate.items():
        precision = totals["matches"] / totals["predicted"] if totals["predicted"] else 0.0
        recall = totals["matches"] / totals["gold"] if totals["gold"] else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0
        judge_summary["tracks"][strategy] = {
            "matches": int(totals["matches"]),
            "predicted_claims": int(totals["predicted"]),
            "gold_claims": int(totals["gold"]),
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "meta_noise": int(totals["meta_noise"]),
        }

    judge_summary["winner"] = max(
        judge_summary["tracks"].items(),
        key=lambda item: (
            item[1]["f1"],
            item[1]["recall"],
            -float(item[1]["meta_noise"]),
            -abs(item[1]["predicted_claims"] - item[1]["gold_claims"]),
        ),
    )[0]
    judge_summary["criteria"] = [
        "maximize f1 against gold claims",
        "prefer higher recall when f1 ties",
        "penalize meta/identity claim noise",
        "prefer predicted claim counts close to gold-set size",
    ]

    return {
        "bundle_root": str(base),
        "benchmark_path": str(benchmark_path),
        "per_document": per_document,
        "judge_summary": judge_summary,
    }
