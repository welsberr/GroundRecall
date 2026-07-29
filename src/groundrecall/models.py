from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

try:
    from epistemap import ConfidenceAssessment
except ImportError:  # pragma: no cover - optional local integration fallback
    ConfidenceAssessment = dict  # type: ignore[misc,assignment]


LifecycleStatus = Literal["draft", "triaged", "reviewed", "promoted", "superseded", "archived", "rejected"]
GroundingStatus = Literal["grounded", "partially_grounded", "ungrounded"]
SupportKind = Literal["direct_source", "derived_from_page", "derived_from_session", "inferred", "unknown"]
ProvenanceVisibility = Literal["full", "partial", "redacted", "hidden"]
ReleaseLevel = Literal["public", "internal", "confidential", "privileged", "private"]
ScopeKind = Literal["entity", "group", "project", "community"]
WorkKind = Literal["project", "technique", "experiment", "prototype", "incident", "lesson"]
WorkOutcome = Literal["unknown", "successful", "failed", "inconclusive", "superseded", "abandoned"]
ContributionState = Literal["proposed", "triaged", "under_review", "accepted", "partially_accepted", "rejected", "deferred", "withdrawn", "superseded"]
StewardshipStatus = Literal["assigned", "active", "transferred", "declined", "expired", "orphaned"]
CustodyEventKind = Literal["assign", "accept", "transfer", "decline", "orphan", "recover", "retire"]


class ProvenanceRecord(BaseModel):
    origin_artifact_id: str = ""
    origin_path: str = ""
    origin_section: str = ""
    source_url: str = ""
    retrieval_date: str = ""
    machine_id: str = ""
    session_id: str = ""
    support_kind: SupportKind = "unknown"
    grounding_status: GroundingStatus = "ungrounded"


class SourceRecord(BaseModel):
    source_id: str
    title: str = ""
    source_type: str = "document"
    path: str = ""
    url: str = ""
    retrieved_at: str = ""
    metadata: dict = Field(default_factory=dict)
    current_status: LifecycleStatus = "draft"


class FragmentRecord(BaseModel):
    fragment_id: str
    source_id: str
    text: str
    section: str = ""
    line_start: int = 0
    line_end: int = 0
    metadata: dict = Field(default_factory=dict)
    current_status: LifecycleStatus = "draft"


class ArtifactRecord(BaseModel):
    artifact_id: str
    artifact_kind: str
    title: str = ""
    path: str = ""
    sha256: str = ""
    created_at: str = ""
    metadata: dict = Field(default_factory=dict)
    current_status: LifecycleStatus = "draft"


class ScopeRecord(BaseModel):
    scope_id: str
    scope_kind: ScopeKind
    title: str
    description: str = ""
    parent_scope_id: str = ""
    owner_scope_id: str = ""
    owner_principal_ids: list[str] = Field(default_factory=list)
    release_level: ReleaseLevel = "private"
    retention_class: str = ""
    current_status: LifecycleStatus = "draft"
    metadata: dict = Field(default_factory=dict)


class WorkRecord(BaseModel):
    work_id: str
    work_kind: WorkKind
    title: str
    summary: str = ""
    scope_id: str = ""
    work_status: str = "active"
    outcome: WorkOutcome = "unknown"
    started_at: str = ""
    completed_at: str = ""
    review_due_at: str = ""
    related_work_ids: list[str] = Field(default_factory=list)
    related_claim_ids: list[str] = Field(default_factory=list)
    related_artifact_ids: list[str] = Field(default_factory=list)
    release_level: ReleaseLevel = "private"
    current_status: LifecycleStatus = "draft"
    metadata: dict = Field(default_factory=dict)


class DecisionRecord(BaseModel):
    decision_id: str
    scope_id: str = ""
    question: str
    outcome: str
    status: str = "active"
    alternatives_considered: list[str] = Field(default_factory=list)
    rejected_alternatives: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    rationale: str = ""
    supporting_record_ids: list[str] = Field(default_factory=list)
    opposing_record_ids: list[str] = Field(default_factory=list)
    decision_maker_ids: list[str] = Field(default_factory=list)
    reviewer_role_ids: list[str] = Field(default_factory=list)
    effective_at: str = ""
    review_due_at: str = ""
    superseded_at: str = ""
    release_level: ReleaseLevel = "private"
    current_status: LifecycleStatus = "draft"
    metadata: dict = Field(default_factory=dict)


class ContributionRecord(BaseModel):
    contribution_id: str
    origin_instance_id: str = ""
    contributor_id: str
    destination_scope_id: str
    contribution_intent: str
    contributed_record_ids: list[str] = Field(default_factory=list)
    contributed_content_hashes: list[str] = Field(default_factory=list)
    proposed_release_level: ReleaseLevel = "private"
    provenance_visibility: ProvenanceVisibility = "full"
    state: ContributionState = "proposed"
    assigned_steward_role_ids: list[str] = Field(default_factory=list)
    reviewer_role_ids: list[str] = Field(default_factory=list)
    policy_decision_ids: list[str] = Field(default_factory=list)
    review_receipt_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    created_at: str = ""
    updated_at: str = ""
    release_level: ReleaseLevel = "private"
    current_status: LifecycleStatus = "draft"
    metadata: dict = Field(default_factory=dict)


class ContributionReviewReceipt(BaseModel):
    receipt_id: str
    contribution_id: str
    reviewer_id: str
    reviewer_role: str = ""
    decision: str
    rationale: str
    reviewed_content_hashes: list[str] = Field(default_factory=list)
    policy_id: str = ""
    reviewed_at: str = ""
    release_level: ReleaseLevel = "private"
    current_status: LifecycleStatus = "reviewed"
    metadata: dict = Field(default_factory=dict)


class StewardshipRecord(BaseModel):
    stewardship_id: str
    subject_type: Literal["scope", "record", "work", "decision", "contribution"]
    subject_id: str
    scope_id: str = ""
    steward_principal_id: str = ""
    steward_role_id: str = ""
    responsibility_type: str = "maintain"
    effective_at: str = ""
    expires_at: str = ""
    status: StewardshipStatus = "assigned"
    succession_target_id: str = ""
    release_level: ReleaseLevel = "private"
    current_status: LifecycleStatus = "draft"
    metadata: dict = Field(default_factory=dict)


class CustodyEventRecord(BaseModel):
    event_id: str
    event_kind: CustodyEventKind
    subject_type: str
    subject_id: str
    scope_id: str = ""
    previous_custodian_id: str = ""
    new_custodian_id: str = ""
    authority_id: str = ""
    rationale: str = ""
    occurred_at: str = ""
    release_level: ReleaseLevel = "private"
    current_status: LifecycleStatus = "reviewed"
    metadata: dict = Field(default_factory=dict)


class ObservationRecord(BaseModel):
    observation_id: str
    artifact_id: str = ""
    role: str
    text: str
    metadata: dict = Field(default_factory=dict)
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)
    confidence_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    assessments: list[ConfidenceAssessment] = Field(default_factory=list)
    current_status: LifecycleStatus = "draft"


class ClaimRecord(BaseModel):
    claim_id: str
    claim_text: str
    claim_kind: str = "statement"
    metadata: dict = Field(default_factory=dict)
    source_observation_ids: list[str] = Field(default_factory=list)
    supporting_fragment_ids: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    contradicts_claim_ids: list[str] = Field(default_factory=list)
    supersedes_claim_ids: list[str] = Field(default_factory=list)
    confidence_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    review_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    assessments: list[ConfidenceAssessment] = Field(default_factory=list)
    last_confirmed_at: str = ""
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)
    current_status: LifecycleStatus = "draft"


class ContradictionCaseRecord(BaseModel):
    case_id: str
    claim_ids: list[str] = Field(default_factory=list)
    case_kind: Literal["contradiction", "disagreement", "supersession_question", "scope_mismatch", "ambiguity"] = "contradiction"
    status: Literal["open", "under_review", "resolved", "superseded", "rejected"] = "open"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    opened_at: str = ""
    resolved_at: str = ""
    adjudication_id: str = ""
    rationale: str = ""
    metadata: dict = Field(default_factory=dict)
    current_status: LifecycleStatus = "draft"


class ConceptRecord(BaseModel):
    concept_id: str
    title: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    source_artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    current_status: LifecycleStatus = "draft"


class RelationRecord(BaseModel):
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)
    assessments: list[ConfidenceAssessment] = Field(default_factory=list)
    current_status: LifecycleStatus = "draft"


class ReviewCandidateRecord(BaseModel):
    review_candidate_id: str
    candidate_type: Literal["claim", "concept", "relation"]
    candidate_id: str
    triage_lane: str = "knowledge_capture"
    priority: int = 50
    finding_codes: list[str] = Field(default_factory=list)
    rationale: str = ""
    current_status: LifecycleStatus = "draft"


class PromotionRecord(BaseModel):
    promotion_id: str
    candidate_type: Literal["claim", "concept", "relation"]
    candidate_id: str
    promotion_target: str = "groundrecall_store"
    verdict: Literal["approved", "rejected", "superseded"] = "approved"
    reviewer: str = ""
    promoted_object_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    promoted_at: str = ""


class AdjudicationRecord(BaseModel):
    adjudication_id: str
    subject_id: str
    subject_type: Literal["claim", "observation", "relation", "contradiction_case"] = "claim"
    selected_assessment_ids: list[str] = Field(default_factory=list)
    considered_assessment_ids: list[str] = Field(default_factory=list)
    adjudicator: str = ""
    method: str = "explicit_review"
    rationale: str = ""
    decided_at: str = ""
    metadata: dict = Field(default_factory=dict)


class GroundRecallSnapshot(BaseModel):
    snapshot_id: str
    created_at: str
    sources: list[SourceRecord] = Field(default_factory=list)
    fragments: list[FragmentRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    scopes: list[ScopeRecord] = Field(default_factory=list)
    works: list[WorkRecord] = Field(default_factory=list)
    decisions: list[DecisionRecord] = Field(default_factory=list)
    contributions: list[ContributionRecord] = Field(default_factory=list)
    contribution_review_receipts: list[ContributionReviewReceipt] = Field(default_factory=list)
    stewardship: list[StewardshipRecord] = Field(default_factory=list)
    custody_events: list[CustodyEventRecord] = Field(default_factory=list)
    observations: list[ObservationRecord] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
    contradiction_cases: list[ContradictionCaseRecord] = Field(default_factory=list)
    concepts: list[ConceptRecord] = Field(default_factory=list)
    relations: list[RelationRecord] = Field(default_factory=list)
    promotions: list[PromotionRecord] = Field(default_factory=list)
    adjudications: list[AdjudicationRecord] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
