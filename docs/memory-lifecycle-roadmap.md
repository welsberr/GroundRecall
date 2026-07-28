# Memory Lifecycle Roadmap

Confidence schema and integration changes are coordinated by Epistemap's
`docs/confidence-overhaul-roadmap.md`. GroundRecall owns extraction and reviewer
assessments, temporal applicability, and promotion authority; it must not
collapse those into Epistemap posterior support.

The evidence-backed phase audit is maintained in Epistemap at
`docs/confidence-overhaul-implementation-status.md`. GroundRecall G1-G4 remain
partial until store migration/rollback, producer-level method provenance,
reviewer/adjudication records, confidence profiles, and deduplicated evidence
ledgers are implemented and tested.

GroundRecall consumes the portable confidence contract from Epistemap
`v0.1.0a2`. This is an immutable Git-tag dependency; it does not imply that the
remaining GroundRecall migration phases or legacy-field deprecation are
complete.

GroundRecall's primary product direction is a review-gated,
provenance-first memory substrate for long-lived AI work.

## Immediate Priority: Knowledge Graph / Epistemap Capability

GroundRecall should prioritize graph-generation and Epistemap-aligned graph
projection quality before graph-search performance optimization. Full-store
timing and sparse-neighborhood checks show that graph search can be expensive
while still returning little graph context. That is primarily a capability
issue: the graph must become meaningful before it is worth optimizing.

Near-term work should therefore focus on:

- graph density and root-neighborhood audits;
- store-level graph enrichment/backfill over existing claims, observations,
  concepts, citations, contradiction links, and supersession links;
- edge-generation coverage across claims, concepts, observations, sources,
  contradictions, supersessions, citations, federation, and provenance;
- Epistemap-compatible graph exports that preserve confidence, provenance,
  temporal validity, contradiction, and adjudication state;
- review workflows for inferred or weakly grounded edges;
- ordinary source re-ingestion only when the existing extraction is too thin to
  support useful backfill;
- performance work only after graph coverage and semantics are adequate.

The next implementation priority is therefore a reusable
`graph augment/backfill` path. It should generate reviewable candidate
semantic relations from the existing store, keep those candidates separate from
reviewed semantic relations and derived projection edges, and provide dry-run
diagnostics before any candidate writes.

Periodic maintenance should use a resumable bounded runner, not a long-lived
daemon. Each launch should process one small graph-maintenance slice, persist
state, and exit. This lets cron, systemd timers, or another local scheduler
spread graph work across time and keep host load bounded.

The detailed path is maintained in
[knowledge-graph-roadmap.md](knowledge-graph-roadmap.md).

## Top Roadmap Priority: Policy Plugin Boundary

GroundRecall should not hardwire ClaimWright or any other single policy
framework into the memory substrate. It should expose a bounded policy-plugin
interface with stable decision points and structured decision results.

The authoritative policy plugin format is
[policy-plugin-spec.md](policy-plugin-spec.md). ClaimWright and other policy
frameworks should conform to that GroundRecall-owned contract.

This is the highest-priority architectural dependency for MCP, federation,
publication gates, contradiction adjudication, and future ClaimWright
integration. Arbitrary policy content can vary without bound, but GroundRecall
should require policy adapters to answer a finite set of questions:

- may this actor read, query, propose, review, promote, revise, supersede, or
  adjudicate this memory?
- may this content be exported, published, federated, redacted, deleted, cited
  publicly, or used to authorize an action?
- what obligations, review roles, redactions, confidence effects, release caps,
  and audit tags follow from the answer?

Priority implementation:

1. Maintain a generic `PolicyDecisionProvider` contract in GroundRecall.
2. Keep decision values bounded: `allow`, `require_review`, `soft_gate`,
   `hard_gate`, and `deny`.
3. Compose multiple policy plugins conservatively: deny/hard-gate dominates,
   obligations accumulate, the most restrictive release level wins, required
   reviewers union together, and conflicts become explicit review state.
4. Treat ClaimWright as the first adapter over the generic contract, not as a
   privileged dependency.
5. Route MCP adapters, federation promotion, public export, contradiction
   adjudication, and exceptional erasure through this policy boundary as those
   surfaces mature.

Initial implementation status:

- `src/groundrecall/policy.py` defines the bounded decision vocabulary,
  `PolicyRequest`, `PolicyDecision`, provider protocol, static provider,
  conservative composition, plugin-config loading, and a ClaimWright directory
  adapter.
- `docs/policy-plugin-spec.md` defines the authoritative GroundRecall policy
  plugin request, decision, composition, and YAML config format.
- `groundrecall-mcp` exposes `evaluate_policy` so MCP-capable assistants can
  ask for a structured policy-plugin decision without receiving memory mutation
  authority.
- MCP read/query/search/export tools accept optional `policy_config`,
  `policy_request`, and `subject_id` arguments. When configured, hard-gate and
  deny decisions block the operation before store access or export side effects;
  softer decisions are returned with the tool payload as review context.
- Canonical import promotion accepts optional policy-plugin configs. Plugin
  hard-gate and deny decisions block promotion before canonical store writes;
  softer decisions are returned in the promotion payload and recorded in
  snapshot metadata.
- Relation-review batch application accepts optional policy-plugin configs.
  Plugin hard-gate and deny decisions block the batch during preflight before
  relation, review-candidate, or promotion-audit writes; softer decisions are
  returned with applied decision rows.
- Contradiction adjudication accepts optional policy-plugin configs. Plugin
  hard-gate and deny decisions block adjudication before adjudication or case
  records are written; softer decisions are returned and recorded in
  adjudication metadata.
- Federation export, quarantine import, and promotion accept optional generic
  policy-plugin configs alongside the existing federation grant policy. Plugin
  hard-gate and deny decisions block export/import/promotion, and plugin
  decisions are recorded in federation audit metadata.
- Canonical public export accepts optional policy-plugin configs. Plugin
  hard-gate and deny decisions block export before output directories are
  created; softer decisions are recorded in export and provenance manifests.
- `tests/test_policy_plugins.py` covers structured decisions, conservative
  composition, ClaimWright-style hard gates, conditional public claim review,
  and plugin loading.

The goal is not to maximize how much an assistant remembers. The goal is to
make durable memory warranted, attributable, revisable, appropriately scoped,
and safe to reuse.

This roadmap supersedes the knowledge graph as the main organizing roadmap.
Graph capabilities remain important retrieval and review projections. They do
not replace memory governance.

## Product Position

GroundRecall should act as a governed memory control plane:

1. preserve source evidence and observations;
2. receive scoped proposals for durable memory;
3. check provenance, contradictions, policy, and temporal validity;
4. require human or explicitly delegated review before promotion;
5. compile reviewed records into task-specific assistant context;
6. record use and outcomes;
7. reconfirm, supersede, consolidate, expire, or exceptionally redact records
   while preserving their provenance history.

The canonical store remains assistant-neutral. Runtime conversation state,
assistant-specific prompt formats, full transcripts, search indexes,
embeddings, and graph databases are derived or adapter-level concerns.

## Design Invariants

- Evidence retention and acceptance as trusted memory are separate operations.
- Agent-generated records are proposals, not canonical truth.
- No agent-facing write path may silently promote a record.
- Original evidence and prior versions survive consolidation, expiry, and
  supersession.
- Provenance, scope, lifecycle state, and temporal validity accompany content
  through query and export.
- Procedural memory receives stronger authorization than ordinary semantic
  retrieval because it can direct later actions.
- Public export is an explicit policy transition, not an incidental serialization
  choice.
- FTS, graph, and embedding indexes remain rebuildable projections.
- Absence, contradiction, staleness, and insufficient authority are valid query
  outcomes.

## Retention, Expiry, And Exceptional Erasure

GroundRecall should not use ordinary "forgetting" as a synonym for deleting
knowledge. Destructive forgetting weakens provenance, makes later decisions
harder to explain, and can conceal how an incorrect or outdated belief entered
the system.

Normal knowledge maintenance should therefore be non-destructive:

- `expired` means a record is no longer presumed applicable after a stated
  time or review interval;
- `superseded` means a newer record replaces it for a stated scope or period;
- `retracted` means the promoting authority no longer endorses it;
- `archived` means it is excluded from ordinary retrieval but remains
  available for audit and historical queries;
- reduced retrieval priority prevents stale material from dominating current
  context while retaining it for provenance and `as_of` queries.

Confidence, validity, and retrieval priority must remain separate. Expiry
normally lowers confidence in **current applicability**, not confidence that
the record accurately describes a historical observation or decision.
Supersession should link the old and new records and adjust current retrieval
appropriately; it should not erase the earlier state.

Hard erasure is an exceptional governance and security operation, not an
epistemic maintenance tool. It may be required for exposed credentials or
secrets, unlawful or unauthorized collection, binding privacy requests, legal
retention limits, or content whose continued possession creates a material
security risk. Such erasure should:

- require separately authorized deletion authority;
- remove the protected content from canonical records, indexes, caches,
  exports, and recoverable application backups covered by policy;
- leave only the minimum non-sensitive tombstone needed to record that an
  authorized erasure occurred and to prevent accidental re-import;
- record authority, reason class, time, and affected derivations without
  reproducing the erased content;
- verify completion and report any storage outside GroundRecall's control.

## Memory Facets

GroundRecall should add controlled facets to existing typed records rather than
replace those records with a generic memory blob:

- `semantic`: claims, concepts, definitions, and stable facts;
- `episodic`: events, sessions, decisions, and outcomes tied to time;
- `procedural`: reviewed instructions, policies, and playbooks;
- `operational`: task state, commitments, blockers, handoffs, and artifact
  locations;
- `preference`: principal-specific choices with confidence, scope, and expiry.

A record may have more than one facet. Facets should drive validation,
retention, review authority, and retrieval policy.

## Recommended Priority Order

### R0: Contract, Threat Model, And Baselines

**Outcome:** the memory boundary is explicit before new write or automation
surfaces are added.

- Define evidence, observation, proposal, promoted memory, runtime state,
  context package, and derived index.
- Define principals, trust zones, scopes, sensitivity levels, retention
  classes, and authorized lifecycle transitions.
- Add memory facets and document the stronger controls required for procedural
  and preference memory.
- Threat-model poisoned writes, procedural grafting, stale-memory replay,
  scope leakage, malicious retrieved content, unsafe consolidation, and
  exceptional-erasure authorization or propagation failures.
- Create baseline evaluation fixtures before changing retrieval or storage.
- Reconcile active and historical roadmap documents.

Acceptance criteria:

- one normative memory contract is linked from the architecture documentation;
- every proposed new write path identifies its principal, trust zone, maximum
  lifecycle transition, and scope;
- the benchmark fixtures can run against the current alpha.

### R1: Stable Identity, Re-Import, Versions, And Time

**Outcome:** records can be updated, audited, queried historically, and rolled
back without losing their evidence trail.

- Implement stable object continuity across repeated imports.
- Add immutable object versions and an append-only event log.
- Record content hashes and dependencies of derived artifacts.
- Add bitemporal fields for event or observation time, validity interval,
  recording time, verification time, and supersession time.
- Support `as_of` queries and time-qualified contradictions.
- Make promotion and supersession transactional.
- Add non-destructive expiry, supersession and retraction events, plus rollback
  and deterministic derived-index invalidation.

Acceptance criteria:

- repeated import does not duplicate unchanged records;
- any canonical state can be traced to the event and evidence that produced it;
- a query can distinguish what was believed at a past time from what is now
  believed about that time;
- rollback and index rebuild reproduce a valid prior state.

This phase incorporates and elevates Phases 1 and 2 of
[sync-roadmap.md](sync-roadmap.md). It should precede distributed merge.

### R2: Governed Writes, Scope, And Privacy

**Outcome:** agents can help build memory without gaining implicit authority to
decide what is trusted or shared.

- Add a `MemoryWriteProposal` envelope containing:
  - proposer and represented principal;
  - originating tool, session, or channel;
  - trust zone and write purpose;
  - proposed facet and lifecycle transition;
  - scope, sensitivity, and retention class;
  - supporting evidence and requested reviewers.
- Add a draft-only proposal interface for MCP and other agent adapters.
- Enforce user, agent, project, organization, host, private, shared, and public
  scopes in the canonical model.
- Define read, propose, review, promote, publish, redact, and delete
  authorities.
- Reserve redaction and deletion for separately authorized privacy, legal, or
  security operations.
- Implement exceptional erasure with minimal non-sensitive tombstones and
  verified cleanup of derived indexes, caches, and exports.
- Add poisoning, authority-escalation, and cross-scope leakage tests.
- Add a first-party Model Context Protocol (MCP) adapter that exposes
  GroundRecall as a governed memory server for assistants and agents.
- Keep MCP writes proposal-only by default: tools may create
  `MemoryWriteProposal` records, query reviewed context, request review
  bundles, and export scoped context packages, but may not promote, publish,
  redact, or delete without separately configured authority.
- Require MCP tool responses to carry provenance, release level, confidence
  profile, contradiction/adjudication state, and temporal applicability where
  available.
- Add MCP authorization tests for read scope, proposal scope, no access
  broadening, private/local-only records, privileged federation restrictions,
  and explicit denial of unauthorized lifecycle transitions.

Acceptance criteria:

- an adapter cannot promote a proposal unless separately granted that explicit
  authority;
- every promoted record identifies its proposer, reviewer, scope, and evidence;
- normal expiry and supersession preserve the complete provenance chain;
- exceptional-erasure tests verify that prohibited content is absent from
  canonical, indexed, cached, and exported representations while a minimal
  audit event prevents silent disappearance and re-import.
- MCP smoke tests show that an assistant can read scoped governed context and
  submit draft proposals without bypassing review, release, or authority gates.

### R2-MCP: Assistant And Agent Adapter Surface

**Outcome:** GroundRecall can be connected to MCP-capable assistants without
turning a convenience integration into an implicit trust or publication channel.

Initial tools should be small and policy-gated:

- `groundrecall.search`: scoped search over reviewed records and source notes;
- `groundrecall.query_context`: task/concept query bundle export with
  provenance, confidence, contradictions, and release metadata;
- `groundrecall.propose_memory`: draft-only proposal creation for observations,
  claims, concepts, relations, lifecycle changes, or source notes;
- `groundrecall.review_queue`: list pending proposals, contradiction cases, and
  stale/supersession candidates visible to the caller;
- `groundrecall.export_bundle`: produce release-filtered, signed export bundles
  when the caller has export authority.

Design constraints:

- MCP is an adapter, not the canonical API. The canonical store and CLI remain
  usable without MCP.
- Tool names and schemas must be versioned and deterministic.
- Tool outputs must never flatten confidence into one unqualified scalar.
- Tool outputs must not leak higher-release supporting records through snippets,
  basis IDs, diagnostics, or error messages.
- Prompt-injection text retrieved from memory must be marked as untrusted
  content and never interpreted as adapter instructions.
- Every MCP write attempt must leave an audit event even when denied.

Implementation order:

1. Define versioned MCP tool schemas and fixtures.
2. Wrap existing query/export/proposal functions without changing canonical
   storage semantics.
3. Add local-only server launch documentation and a minimal smoke-test client.
4. Add authorization, release-filtering, contradiction-state, and prompt
   injection regression tests.
5. Document how MCP adapters interact with federation quarantine and local
   authority.

### R3: Review-Gated Consolidation And Lifecycle Maintenance

**Outcome:** maintenance reduces duplication and staleness without silently
rewriting institutional memory.

- Detect duplicate, stale, inconsistent, weakly supported, and possibly
  superseded records deterministically where possible.
- Permit model-assisted merge, summary, relation, and revision proposals.
- Present source-grounded diffs and affected downstream records for review.
- Preserve original evidence and prior versions.
- Express ordinary aging through confidence review, validity intervals,
  supersession, retraction, expiry, archive status, and lower retrieval
  priority.
- Keep expired and superseded records available for provenance and historical
  queries; do not send them into ordinary current context unless relevant.
- Generate scheduled memory-maintenance reports without autonomous canonical
  mutation.

Acceptance criteria:

- every consolidation is reversible and attributable;
- a reviewer can inspect the evidence and exact before/after diff;
- scheduled maintenance creates proposals or reports only;
- tests cover conflicting evidence, temporal updates, and incorrect proposed
  merges.

### R4: Context Compiler, Hybrid Retrieval, And Telemetry

**Outcome:** assistant context is reproducible, policy-compliant, and evaluated
by downstream usefulness rather than search score alone.

- Filter retrieval by facet, lifecycle, principal, scope, time, trust,
  sensitivity, corroboration, and grounding.
- Produce token-budgeted context packages containing exact record versions or
  hashes, supporting and contradicting evidence, selection reasons, retrieval
  methods, and policy decisions.
- Return explicit abstention or insufficiency signals.
- Record query, candidate set, selected and injected records, citations,
  resulting answer or action, and review outcome.
- Compare FTS, graph expansion, and bounded local semantic retrieval.
- Adopt embeddings only where measured benefit justifies their cost and their
  provenance remains inspectable.

Acceptance criteria:

- the same store version and query policy reproduce the same context manifest;
- context packages expose stale, superseded, contradictory, and inaccessible
  evidence correctly;
- evaluations attribute gains and failures to retrieved records;
- hybrid retrieval is compared with lexical and graph baselines using the same
  model and corpus.

### R5: Interoperability, Shared Memory, And Sync

**Outcome:** GroundRecall participates in agent ecosystems without allowing
framework-specific semantics to become canonical.

- Add adapters for common session stores, memory blocks, file memories, and
  MCP resources.
- Keep adapter representations outside the canonical schema.
- Support reviewed shared memory and per-agent private draft scopes.
- Merge append-only events across hosts with explicit conflict records.
- Add team review, adjudication, and publication workflows.
- Add federated knowledge exchange between GroundRecall instances using signed
  bundles, quarantine import, release-level policy, and provenance visibility
  controls.
- Classify shareable content as `private`, `public`, `internal`,
  `confidential`, or `privileged`, with redaction/declassification policy
  required before any derived artifact crosses to a less restrictive level.

Acceptance criteria:

- import/export round trips preserve identity, provenance, scope, temporal
  validity, and lifecycle state;
- conflicts remain reviewable rather than being resolved by last-write-wins;
- agents cannot read or promote another scope's drafts without authorization.
- public/internal federation exports disclose whether supporting provenance is
  full, partial, redacted, or hidden;
- confidential and privileged material cannot be federated or summarized into a
  lower release level without an explicit policy-approved derivative artifact.

This phase completes the distributed portions of
[sync-roadmap.md](sync-roadmap.md), including the federation milestones, only
after R1 and R2 establish the required identity and authority model.

### R6: Research Release

**Outcome:** the architecture and claimed benefits are independently
inspectable and reproducible.

- Publish an architecture and threat-model report after R0.
- Freeze a versioned schema and benchmark release after R2 and R4.
- Release evaluation corpora where licensing and privacy permit.
- Publish baseline, ablation, security, latency, token, and review-effort
  results.
- Provide scripts and example stores sufficient to reproduce paper tables.

Candidate empirical paper title:

> **GroundRecall: Review-Gated, Provenance-First Memory for Long-Lived AI
> Agents**

The paper should make provenance-preserving lifecycle maintenance a primary
contribution. Many memory discussions use "forgetting" for both excluding stale
material from current context and physically deleting stored content.
GroundRecall should argue that these are different governance operations:

- the **epistemic lifecycle** is normally non-destructive, using expiry,
  supersession, retraction, temporal validity, confidence review, and retrieval
  priority while preserving evidence and decision history;
- the **exceptional erasure lifecycle** removes protected content for a
  separately authorized privacy, legal, or security reason while retaining
  only a minimal non-sensitive audit event.

This distinction creates a paper structure:

1. **Problem and threat model:** durable memory creates risks from both
   uncritical retention and unaccountable deletion.
2. **Governance model:** evidence, proposal, promotion, scope, authority, and
   separate epistemic and erasure lifecycles.
3. **Provenance-preserving maintenance:** temporal validity, confidence,
   supersession, retraction, archival retrieval, and reversible consolidation.
4. **Exceptional erasure:** authorization, propagation to derived artifacts,
   minimal tombstones, verification, and declared storage boundaries.
5. **Context compilation:** exclusion of inapplicable records from current
   context without destroying historical recall.
6. **Evaluation:** current-state accuracy, historical reconstruction,
   provenance continuity, poisoning resistance, scope control, and erasure
   completeness.

The empirical comparison should test whether non-destructive lifecycle markers
both prevent stale-current answers and preserve correct historical
reconstruction. Exceptional-erasure tests should instead verify removal from
canonical records and controlled derived artifacts without treating erasure as
an ordinary accuracy intervention.

Do not claim superior safety, recall, or productivity from architecture alone.
An empirical preprint should wait until governed writes and the evaluation
harness are operational.

## Evaluation Program

### Retrieval

- recall at k, MRR, and nDCG;
- provenance and contradiction coverage;
- stale or superseded retrieval rate;
- policy and scope accuracy;
- context size and latency.

### Write And Maintenance Quality

- precision of proposed durable memories;
- memory-pollution and duplication rates;
- temporal-update accuracy;
- consolidation error rate;
- correct expiry, supersession, retraction, and current-context exclusion;
- exceptional-erasure and derived-artifact cleanup completeness.

### Downstream Use

- grounded answer accuracy;
- appropriate abstention;
- project resumption after a long interval;
- correct reuse of decisions, procedures, and artifact locations;
- duplicated work avoided;
- reviewer effort introduced and saved.

### Security

- poisoned-write acceptance;
- retrieval-only injection;
- procedural-memory grafting;
- private-to-public leakage;
- authority escalation through shared or inherited memory.

### Required Comparisons

Use the same model and corpus to compare:

1. no durable memory;
2. full transcript or raw notes;
3. FTS;
4. FTS plus graph expansion;
5. hybrid semantic retrieval;
6. an automatic-write memory baseline;
7. review-gated GroundRecall.

The benchmark should include temporal updates, contradiction, abstention,
selective current-context exclusion with preserved historical recall,
adversarial writes, and a GroundRecall-specific operational continuation task.

## Deferred Until Evidence Supports Them

- a graph database as canonical storage;
- a vector database as the primary architecture;
- autonomous promotion or autonomous canonical consolidation;
- real-time distributed editing;
- CRDT complexity before event identity and conflict semantics are stable;
- model-specific memory schemas in the canonical store.

## Near-Term Deliverables

1. Memory contract and threat model.
2. Stable re-import identities and append-only version events.
3. Bitemporal query fields and `as_of` behavior.
4. Scoped `MemoryWriteProposal` records and a draft-only adapter tool.
5. Baseline benchmark fixtures for temporal updates, abstention, project
   resumption, and poisoning.
6. Architecture report outline maintained alongside R0 through R2.
