from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .groundrecall_review_bridge import export_review_bundle_from_import
from .review_export import build_citation_review_entries_from_import, export_review_state_json, export_review_ui_data
from .review_schema import ReviewAction, ReviewLedgerEntry, ReviewSession


def _normalize_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


class GroundRecallReviewWorkspace:
    def __init__(self, import_dir: str | Path, reviewer: str = "GroundRecall Import") -> None:
        self.import_dir = Path(import_dir)
        self.reviewer = reviewer

    @property
    def review_session_path(self) -> Path:
        return self.import_dir / "review_session.json"

    @property
    def review_data_path(self) -> Path:
        return self.import_dir / "review_data.json"

    def ensure_review_bundle(self) -> None:
        if not self.review_session_path.exists():
            export_review_bundle_from_import(self.import_dir, reviewer=self.reviewer)
            return
        session = ReviewSession.model_validate_json(self.review_session_path.read_text(encoding="utf-8"))
        updated = False
        if (
            not session.citation_reviews
            or any(entry.source_kind == "citation_key" and not entry.title for entry in session.citation_reviews)
            or any(entry.source_kind == "citation_key" and not entry.source_bib_path for entry in session.citation_reviews)
        ):
            session.citation_reviews = build_citation_review_entries_from_import(self.import_dir)
            updated = True
        if updated or not self.review_data_path.exists():
            self.save_session(session)

    def load_session(self) -> ReviewSession:
        self.ensure_review_bundle()
        return ReviewSession.model_validate_json(self.review_session_path.read_text(encoding="utf-8"))

    def save_session(self, session: ReviewSession) -> None:
        export_review_state_json(session, self.review_session_path)
        export_review_ui_data(session, self.import_dir, import_dir=self.import_dir)

    def load_review_data(self) -> dict[str, Any]:
        self.ensure_review_bundle()
        return json.loads(self.review_data_path.read_text(encoding="utf-8"))

    def apply_updates(
        self,
        *,
        concept_updates: list[dict[str, Any]] | None = None,
        citation_updates: list[dict[str, Any]] | None = None,
        reviewer: str | None = None,
    ) -> ReviewSession:
        session = self.load_session()
        if reviewer:
            session.reviewer = reviewer
        concept_by_id = {concept.concept_id: concept for concept in session.draft_pack.concepts}
        citation_by_id = {entry.citation_review_id: entry for entry in session.citation_reviews}

        for payload in concept_updates or []:
            concept_id = str(payload.get("concept_id", "")).strip()
            if not concept_id or concept_id not in concept_by_id:
                continue
            concept = concept_by_id[concept_id]
            if "status" in payload:
                concept.status = payload["status"]
            if "description" in payload:
                concept.description = str(payload.get("description", "")).strip()
            if "notes" in payload:
                concept.notes = _normalize_lines(payload.get("notes"))
            if "prerequisites" in payload:
                concept.prerequisites = _normalize_lines(payload.get("prerequisites"))
            session.ledger.append(
                ReviewLedgerEntry(
                    reviewer=session.reviewer,
                    action=ReviewAction(
                        action_type="edit_concept",
                        target=concept_id,
                        payload={
                            "status": concept.status,
                            "description": concept.description,
                            "notes": concept.notes,
                            "prerequisites": concept.prerequisites,
                        },
                        rationale=str(payload.get("rationale", "")).strip(),
                    ),
                )
            )

        for payload in citation_updates or []:
            citation_review_id = str(payload.get("citation_review_id", "")).strip()
            if not citation_review_id or citation_review_id not in citation_by_id:
                continue
            entry = citation_by_id[citation_review_id]
            if "status" in payload:
                entry.status = payload["status"]
            if "notes" in payload:
                entry.notes = _normalize_lines(payload.get("notes"))
            session.ledger.append(
                ReviewLedgerEntry(
                    reviewer=session.reviewer,
                    action=ReviewAction(
                        action_type="edit_citation",
                        target=citation_review_id,
                        payload={"status": entry.status, "notes": entry.notes},
                        rationale=str(payload.get("rationale", "")).strip(),
                    ),
                )
            )

        self.save_session(session)
        return session
