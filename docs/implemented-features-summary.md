# GroundRecall Implemented Features Summary

Date: 2026-08-11

This summary records the implemented GroundRecall capabilities that are in
scope for preprint revision after IF-14 and PRR-02. It separates tested
prototype behavior from limitations and future work.

## Assistant Interoperability And Remote MCP

GroundRecall has a tested local MCP server and a bounded HTTP MCP adapter for
private-network deployment. The HTTP adapter supports MCP `initialize`,
`ping`, tool discovery, and bounded read/query calls while keeping policy and
identity controls server-owned.

- Default HTTP exposure is read-only and advertises `readOnlyHint`.
- Fixed bearer-token and server-owned identity-file pilot modes are supported;
  OAuth/OIDC and tunnel-issued identity remain future deployment work.
- Principals can be capped by subject, realm, release level, and tool set.
- Request and response sizes are bounded; oversized responses return a fixed
  error without including result content.
- Responses carry correlation IDs; optional JSONL audit records exclude request
  content and bearer tokens.
- Audit records support hash chaining, verification, rotation, and metadata-only
  manifests with an operator CLI and logrotate hook.
- A proposal-only handoff inbox supports versioned assistant handoff records
  with stable IDs, idempotency keys, provenance, context references, and the
  `handoff_propose`, `handoff_get`, and `handoff_list` MCP methods.

The HTTP adapter, systemd unit, logrotate template, and audit utilities are
deployment templates and pilots. No service or tunnel is installed by the
repository, ChatGPT compatibility has not been certified, and handoff status,
progress/result records, Codex claim automation, OAuth, and centralized audit
export remain future work.

## Current Evidence Snapshot

Current machine-readable reports show:

- institutional federation capability summary: `2 implemented`, `9 partial`,
  `2 future`;
- policy coverage summary: `44` routes total, `27 covered`, `14 partial`,
  `2 intentionally ungated`, `1 future`;
- durable mutation coverage: `15` routes total, `14 covered`, `0 partial`,
  `1 future`;
- institutional conformance scenarios: `6`, all intentionally marked
  `partial`;
- preprint demonstrations: `15` JSON demos plus manifest under
  `examples/preprint/out/`.

The generated local revision snapshot is
`examples/preprint/out/revision_evidence_snapshot.json`.

The evidence counts above describe the institutional/preprint evidence
snapshot and do not include the later ChatGPT/MCP integration commits listed
below; regenerate the snapshot before using those counts as a current release
claim.

## Core Knowledge Substrate

GroundRecall provides a local, file-backed knowledge substrate for grounded
assistant workflows.

- Structured records for sources, fragments, artifacts, observations, claims,
  concepts, relations, contradiction cases, promotions, adjudications, scopes,
  work, decisions, contributions, review receipts, feedback, stewardship,
  custody events, and snapshots.
- Local `GroundRecallStore` persistence with deterministic JSON records.
- Snapshot construction for export, review, federation, inspection, and
  reproducible demonstrations.
- Query/export surfaces for provenance, graph context, confidence context,
  contradictions, and supersessions.
- Source adapter framework for importing material from multiple upstream
  formats.

## Provenance-Preserving Memory Model

GroundRecall keeps provenance attached to claims and observations rather than
flattening memory into ungrounded summaries.

- Observations carry support kind, grounding status, source URL, artifact, path,
  retrieval, and machine/session metadata where available.
- Claims can reference observations, fragments, concepts, contradicted claims,
  superseded claims, license and attribution metadata, release metadata, and
  provenance visibility.
- Export, federation, release-pack, and promotion workflows preserve stable
  record identities and content hashes.
- Candidate/imported material remains distinct from canonical memory until
  review/promotion steps occur.

## Confidence And Temporal Validity Infrastructure

GroundRecall supports confidence as structured, reviewable assessment rather
than a single scalar.

- Confidence profiles can represent basis visibility, ambiguity, applicability,
  expiry, supersession, retraction, and confidence effects.
- Epistemap-compatible exports exist for confidence and knowledge-graph
  surfaces.
- Temporal validity and ordinary “forgetting” are modeled through expiry,
  supersession, retraction, applicability, and confidence reduction rather than
  hard deletion.
- The implementation does not claim full Bayesian calibration or broad
  empirical confidence validation.

## Contradiction Tracking And Adjudication

GroundRecall supports explicit contradiction cases and review-gated
contradiction candidate workflows.

- `contradicts_claim_ids` links can be materialized into deterministic
  contradiction case records.
- Query bundles surface contradiction cases alongside raw contradiction links.
- Diagnostics flag missing contradiction cases, cases with missing claims, and
  open cases involving promoted claims.
- Heuristic contradiction candidates can be reviewed before becoming cases.
- Adjudications can resolve contradiction cases while preserving the underlying
  conflicting claims.
- Robust automatic semantic contradiction detection remains future work.

Demonstrations:

- `contradiction_adjudication.json`
- `contradiction_candidate_review.json`

## Release-Level Classification And Export Guardrails

GroundRecall implements a release lattice:

- `public`
- `internal`
- `confidential`
- `privileged`
- `private`

Implemented behavior:

- `private` records are local-only and are not federated.
- Export and federation filtering prevent access broadening.
- Public export blocks confidential, privileged, and private records unless
  explicit redaction/declassification metadata supports a derivative.
- Hidden or partial provenance is represented as reduced basis visibility rather
  than pretending that all evidence is inspectable.

Demonstration:

- `release_filtering.json`

## Federation Bundle Export, Verification, Quarantine, And Promotion

GroundRecall supports signed exchange bundles and quarantine-before-promotion
import.

- Federation bundles include producer instance, owner instance, target release,
  source snapshot, record counts, content hash, signature, and policy report.
- HMAC signing is supported for local/shared-secret workflows.
- Ed25519 signing is supported for public-key verification workflows.
- Import verifies integrity and places accepted material into quarantine.
- Promotion from quarantine is separately planned and policy-gated.
- Valid signatures do not imply local authority.
- Promotion avoids last-write-wins behavior and preserves review/conflict state.

Demonstrations:

- `federation_quarantine.json`
- `local_authority.json`

## Local Federation Policy, Trust, And Audit

GroundRecall includes local federation policy and trust management.

- `FederationLocalPolicy` grants actions by subject, action, release level,
  instance, scope, and privileged allowance.
- Supported federation actions include export, import, and promote.
- CLI federation commands can write audit events for policy decisions when an
  audit path is supplied.
- Trust registries record active, expired, revoked, and superseded key state.
- Non-secret trust metadata export omits key material.
- Signed Ed25519 public keysets can be published and imported with receiver-side
  caps.
- Signed role directories can be imported only through receiver-side caps and
  local policy compilation.

## Institutional Federation Records And Workflows

GroundRecall now has a broad institutional federation prototype slice.

Implemented or partially implemented capabilities include:

- scope and work records;
- decision, contribution, contribution-review receipt, stewardship, custody
  event, review receipt, and federation feedback records;
- prior-work discovery over work, decisions, and claims;
- signed federation catalogs;
- receiver-local subscriptions and signed incremental change bundles;
- multi-party review quorum evaluation and dissent preservation;
- feedback bundle signing/verification;
- custody/orphan reports, tenancy departure dry-runs, and instance retirement
  dry-runs;
- release-capped orientation, impact, governance, and stewardship views;
- license-aware release packs and signed withdrawal notices;
- institutional MCP tools;
- policy-gated institutional write helpers;
- custody-event policy preflight.

Demonstrations:

- `prior_work_discovery.json`
- `signed_catalog_discovery.json`
- `incremental_subscription.json`
- `multi_party_review_feedback.json`
- `custody_planning.json`
- `release_pack_withdrawal.json`
- `policy_gated_institutional_writes.json`

## Prior-Work Discovery

Prior-work search can surface related projects, techniques, experiments,
decisions, claims, and negative/inconclusive outcomes before new durable work
begins.

- Exact-identity and lexical candidates are distinguished.
- Negative and inconclusive work can be found.
- Release caps hide inaccessible records while reporting inaccessible counts by
  release level.
- Semantic duplicate confirmation remains review-gated.

## Signed Federation Catalogs

Federation catalogs support discovery without transferring canonical records.

- Catalogs can be signed and verified.
- Detail levels include opaque, aggregate, and descriptive.
- Receiver-side caps can narrow accepted entries during quarantine.
- Querying a catalog surfaces discovery metadata, not local authority or
  canonical memory.
- Network transport and protected-topic inference evaluation remain future
  work.

## Subscriptions And Incremental Change Bundles

GroundRecall supports a file-based first slice for incremental federation.

- Subscriptions are receiver-local and include producer, scope filters, record
  kinds, change kinds, release ceiling, purpose, cursor, and active state.
- Signed change bundles are cursor-bounded and replay-safe.
- Imports are verified and quarantined idempotently.
- Acknowledgement advances only after cursor continuity and optional signature
  verification.
- Network polling and canonical promotion from change bundles remain future
  work.

## Multi-Party Review And Feedback

GroundRecall supports generalized review receipts and federation feedback.

- Quorum evaluation checks minimum approvals, required roles, duplicate
  principals, independence, dissent, and invalidated content hashes.
- Federation feedback records preserve producer and receiver adjudications as
  separate assertions.
- Feedback bundles can be signed and verified.
- Automatic promotion blocking from quorum results and direct feedback-bundle
  import remain follow-up work.

## Custody, Tenancy Departure, And Instance Retirement

GroundRecall supports continuity planning when people or hosts leave.

- Orphan stewardship reports identify stewardable records without active
  stewards.
- Tenancy departure planning separates private personal records from
  group-owned reviewed knowledge.
- Instance retirement planning reports trust keys, subscriptions, catalogs,
  pending contributions, stewardship, canonical counts, quarantine, and backup
  surfaces.
- Custody events cannot broaden release level relative to the subject record.
- `record_custody_event` now accepts policy preflight and blocks deny/hard-gate
  decisions before writes.
- Destructive apply commands and full role/authority validation remain future
  work.

## Institutional Views And Impact Routing

GroundRecall can generate read-only institutional views.

- Scope orientation packs include vocabulary, reviewed decisions, current work,
  negative results, unresolved contradictions, stale items, and steward roles.
- Change-impact reports expose reverse dependencies, contradiction state,
  confidence state, and incomplete-basis labels.
- Governance-health reports count unowned scopes/records, stale high-impact
  records, unresolved conflicts, incomplete provenance, and unacknowledged
  subscriptions.
- Stewardship views use explicit stewardship records and suppress activity
  ranking.
- Policy-plugin preflight and post-render filtering remain follow-up work.

## License-Aware Release Packs And Withdrawal

GroundRecall supports deterministic release packs and withdrawal notices.

- Release packs require compatible licenses and attribution.
- Records are content-hashed and signed.
- Protected provenance can be redacted according to redaction policy.
- Superseding pack relationships are recorded.
- Signed withdrawal notices are distinct from erasure and preserve historical
  audit state.
- Direct ClaimWright publication-gate preflight and distributed withdrawal
  propagation remain follow-up work.

## MCP Institutional Tooling

GroundRecall exposes assistant-facing MCP tools for selected institutional
operations.

Implemented MCP tools include:

- `prior_work_review`
- `catalog_discovery`
- `subscription_status`
- `impact_report`
- `stewardship_orphans`
- `propose_contribution`

The proposal tool performs no canonical store writes. MCP policy checks remain
caller-supplied rather than mandatory server-side policy configuration.

## Policy Plugin And ClaimWright Compatibility

GroundRecall owns the policy-plugin contract.

- Policy requests are bounded by decision point, action, release levels, scope,
  durable-memory-change status, and metadata.
- Static and ClaimWright-style directory providers can be composed
  conservatively.
- Deny/hard-gate decisions block selected MCP, import, export, federation,
  promotion, adjudication, relation-review, graph-maintenance, institutional
  write, and custody-event surfaces.
- ClaimWright remains example policy content, not a required GroundRecall
  dependency or authority source.

Demonstration:

- `policy_plugin_boundary.json`

## Preprint Demonstration Register

The current demo runner is `examples/preprint/run_preprint_demos.py`.

It emits:

- `provenance_promotion.json`
- `contradiction_adjudication.json`
- `contradiction_candidate_review.json`
- `release_filtering.json`
- `federation_quarantine.json`
- `local_authority.json`
- `policy_plugin_boundary.json`
- `search_mode_timing.json`
- `prior_work_discovery.json`
- `signed_catalog_discovery.json`
- `incremental_subscription.json`
- `multi_party_review_feedback.json`
- `custody_planning.json`
- `release_pack_withdrawal.json`
- `policy_gated_institutional_writes.json`
- `manifest.json`

`search_mode_timing.json` is an internal synthetic-store engineering indication
only. It is not a benchmark against external memory-layer systems.

## CLI And API Surface

Representative implemented CLI/API surfaces include:

- `groundrecall federation export`
- `groundrecall federation import`
- `groundrecall federation list-quarantine`
- `groundrecall federation promote`
- `groundrecall federation policy-from-roles`
- `groundrecall federation role-publish-directory`
- `groundrecall federation policy-import-roles`
- `groundrecall federation trust-add`
- `groundrecall federation trust-list`
- `groundrecall federation trust-revoke`
- `groundrecall federation trust-export-metadata`
- `groundrecall federation trust-publish-keyset`
- `groundrecall federation trust-import-keyset`
- `groundrecall contradictions sync`
- `groundrecall contradictions list`
- `groundrecall contradictions adjudicate`
- `groundrecall prior-work`
- `groundrecall catalog`
- `groundrecall changes`
- `groundrecall custody`
- `groundrecall inspect --policy-coverage`
- `groundrecall inspect --institutional-federation`
- `groundrecall inspect --institutional-conformance`
- `groundrecall-mcp`

## Test And Validation Status

As of PRR-03 preparation:

- Full GroundRecall suite: `316 passed`.
- Preprint demo tests: `5 passed`.
- `git diff --check` passes.
- The canonical repository is clean after committed changes.

## Preprint-Ready Claims

The implementation supports scoped preprint claims that GroundRecall
demonstrates:

- a provenance-preserving local memory layer;
- structured confidence and temporal-validity handling;
- explicit contradiction tracking and adjudication;
- release-level-aware export and federation;
- signed exchange bundles and quarantine-first import;
- local authority controls separate from signature validity;
- trust key lifecycle and capped role/key distribution;
- policy-plugin integration on selected enforcement surfaces;
- institutional federation records and file-based exchange;
- prior-work discovery and negative-result preservation;
- multi-party review, dissent preservation, custody planning, and release
  withdrawal as partial institutional-memory workflows.

## Remaining Work To Treat As Limitations Or Future Work

The current implementation must not be described as a completed distributed
memory platform.

Remaining limitations include:

- network transport and polling;
- real-time synchronization and CRDT merge;
- hosted review services;
- complete production IAM integration;
- mandatory server-side MCP policy configuration;
- policy-plugin preflight/post-render filtering for institutional views;
- direct ClaimWright publication-gate preflight for release packs;
- distributed withdrawal/revocation propagation;
- automatic semantic contradiction detection/resolution;
- destructive exceptional-erasure execution;
- broader benchmark comparisons against external memory-layer products;
- formal user-study evidence for productivity or safety outcomes.

These should be presented as limitations and future work, not as implemented
capabilities.
