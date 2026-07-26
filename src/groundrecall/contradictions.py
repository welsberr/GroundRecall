from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import ClaimRecord, ContradictionCaseRecord


def contradiction_case_id_for_claims(claim_ids: Iterable[str]) -> str:
    normalized = sorted({str(claim_id).strip() for claim_id in claim_ids if str(claim_id).strip()})
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]
    readable = "__".join(_safe_id_part(claim_id) for claim_id in normalized[:2])
    return f"contradiction_case::{readable}::{digest}"


def generate_contradiction_cases_from_claims(
    claims: Iterable[ClaimRecord],
    *,
    opened_at: str | None = None,
    existing_cases: Iterable[ContradictionCaseRecord] = (),
) -> list[ContradictionCaseRecord]:
    claim_by_id = {claim.claim_id: claim for claim in claims}
    existing_by_pair = {
        tuple(sorted(case.claim_ids)): case
        for case in existing_cases
        if case.case_kind == "contradiction" and len(case.claim_ids) >= 2
    }
    generated: list[ContradictionCaseRecord] = []
    seen_pairs: set[tuple[str, str]] = set()
    timestamp = opened_at or _now_utc()
    for claim in claim_by_id.values():
        for target_id in claim.contradicts_claim_ids:
            if target_id not in claim_by_id:
                continue
            pair = tuple(sorted((claim.claim_id, target_id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if pair in existing_by_pair:
                generated.append(existing_by_pair[pair])
                continue
            generated.append(
                ContradictionCaseRecord(
                    case_id=contradiction_case_id_for_claims(pair),
                    claim_ids=list(pair),
                    case_kind="contradiction",
                    status="open",
                    severity=_severity_for_claim_pair(claim_by_id[pair[0]], claim_by_id[pair[1]]),
                    opened_at=timestamp,
                    metadata={
                        "generation_method": "explicit_contradicts_claim_ids",
                        "explicit_edges": [
                            {
                                "source_claim_id": claim.claim_id,
                                "target_claim_id": target_id,
                            }
                        ],
                    },
                    current_status="triaged",
                )
            )
    return generated


def contradiction_cases_for_claim_ids(
    cases: Iterable[ContradictionCaseRecord],
    claim_ids: Iterable[str],
) -> list[ContradictionCaseRecord]:
    wanted = {claim_id for claim_id in claim_ids if claim_id}
    return [case for case in cases if wanted.intersection(case.claim_ids)]


def sync_contradiction_cases_for_store(store_dir: str | Path) -> list[ContradictionCaseRecord]:
    from .store import GroundRecallStore

    store = GroundRecallStore(store_dir)
    cases = generate_contradiction_cases_from_claims(
        store.list_claims(),
        existing_cases=store.list_contradiction_cases(),
    )
    for case in cases:
        store.save_contradiction_case(case)
    return cases


def _severity_for_claim_pair(left: ClaimRecord, right: ClaimRecord) -> str:
    statuses = {left.current_status, right.current_status}
    if "promoted" in statuses:
        return "high"
    if "reviewed" in statuses:
        return "medium"
    return "low"


def _safe_id_part(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return text[:48] or "claim"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
