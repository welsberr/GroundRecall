# Manifesto-First Preprint Outline

Date: 2026-07-26

This outline reframes the preprint away from “here is GroundRecall, therefore these principles matter” and toward “these are the properties governed memory layers should have; GroundRecall and companion tools are examples of partial implementation.”

## Working Title

Memory Layers Should Be Governed: Properties For Durable AI Assistant And Agent Memory

Alternate titles:

- A Manifesto For Governed AI Memory Layers
- Durable AI Memory Needs Provenance, Policy, And Review
- From Persistent Context To Governed Memory Layers

## Core Thesis

AI assistants and agents do not merely need more memory. They need memory layers with explicit governance properties: provenance, review gates, confidence, temporal validity, contradiction handling, release classification, local authority, audit, and policy-aware publication boundaries.

The paper should state the desired properties first, then show that these properties are implementable through working prototype components:

- GroundRecall as a provenance-preserving, review-gated, federated memory substrate;
- ClaimWright as a claim-policy and publication-safety operating stance;
- CiteGeist as a bibliography/provenance workbench for source review;
- Epistemap as a confidence and knowledge-graph operation layer.

This is stronger than a repository-first paper because the argument does not depend on any one codebase being complete. The repos become existence proofs and design probes.

## Abstract Shape

Current AI memory systems increasingly support long-term recall, graph retrieval, personalization, and memory operating-system abstractions. These systems make agents more persistent, but persistence also makes familiar failures more durable: unsupported claims, stale context, hidden contradictions, citation drift, private-to-public leakage, unreviewed promotion, and ambiguous authority over shared memory.

We argue that memory layers for AI assistants and agents should be governed systems, not only retrieval systems. A governed memory layer should preserve provenance, distinguish historical support from current applicability, expose confidence and uncertainty, track contradiction and adjudication, enforce release boundaries, quarantine imported memory, retain audit history, and integrate policy frameworks for public-safe claim use.

We present these requirements as a manifesto for governed AI memory. We then describe prototype implementations across GroundRecall, ClaimWright, CiteGeist, and Epistemap that demonstrate many of the required properties in local-first form. We position these prototypes as evidence that governed memory is practical, while identifying retrieval benchmarks, semantic contradiction detection, hosted review, production IAM, and distributed synchronization as future work.

## Paper Structure

### 1. Manifesto: Memory Is Not Just Recall

Claim:

Durable AI memory changes the risk profile of assistant and agent systems. If memory persists, then unsupported claims, stale assumptions, hidden contradictions, and privacy mistakes persist too.

Properties introduced:

- memory should be inspectable;
- memory should be reviewable;
- memory should be governed before it becomes authoritative;
- memory should preserve disagreement and history;
- memory should respect release boundaries;
- memory should operate under explicit policy.

### 2. Foreseeable Failure Modes

Frame the problem around current-state-of-the-art weaknesses:

- ungrounded summaries becoming durable context;
- citations remembered without review state;
- stale facts reused as current;
- contradictions resolved by retrieval accident rather than adjudication;
- agent memory sharing without local authority;
- public artifacts outrunning private or speculative grounding;
- memory deletion used where expiry/supersession would better preserve provenance.

This section should use `docs/preprint/threat-model.md`.

### 3. Required Properties Of Governed Memory Layers

This should be the normative core of the paper.

| Property | Requirement |
| --- | --- |
| Provenance preservation | Claims should remain linked to observations, sources, citations, and derivation context. |
| Review-gated promotion | Candidate or imported memory should not silently become canonical. |
| Confidence structure | Confidence should encode dimensions and basis, not merely one scalar. |
| Temporal validity | Systems should distinguish historical support from current applicability. |
| Non-destructive forgetting | Expiry, supersession, retraction, and confidence reduction should preserve evidence history except where exceptional erasure is required. |
| Contradiction tracking | Contradictions should become explicit cases, not hidden retrieval noise. |
| Adjudication history | Resolutions should be recorded as review state without silently rewriting underlying claims. |
| Release classification | Memory should carry public/internal/confidential/privileged/private or equivalent release levels. |
| No access broadening | Export/federation should not make memory less restrictive without redaction/declassification authority. |
| Quarantine before promotion | Imported memory should be verified and quarantined before local acceptance. |
| Local authority | Signed memory, keys, and roles should not override receiver policy. |
| Auditability | Export, import, promotion, and policy decisions should leave reviewable records. |
| Policy integration | Memory should be governed by explicit claim/publication/action policies. |

### 4. Example Implementations

Use the repos as implementation examples rather than the main argumentative starting point.

| Prototype | Demonstrated properties |
| --- | --- |
| GroundRecall | Provenance records, review-gated promotion, contradiction cases, release levels, federation quarantine, local policy, audit, trust/role distribution. |
| ClaimWright | Claim lifecycle, adversarial review, citation review, public/private gates, role cards, pre/post action checks, scientific-virtue policy stance. |
| CiteGeist | Bibliographic extraction, verification, enrichment, citation graph expansion, source review, BibTeX export, memory-layer bibliography seeding. |
| Epistemap | Confidence measures, Bayesian-style evidence representation where implemented, knowledge-graph operations, contradiction/confidence interaction targets. |

This section should be explicit that integration is partial. GroundRecall has not yet imported ClaimWright policies as enforcement rules. CiteGeist and Epistemap are companion tools, not hidden GroundRecall subsystems.

### 5. Relation To Memory-Layer Systems

Use `docs/preprint/memory-layer-comparative-analysis.md`.

Argument:

Current memory-layer systems are strong on recall, personalization, graph retrieval, memory scheduling, and production performance. GroundRecall-style governed memory is complementary: it supplies review, provenance, contradiction, release-policy, federation, and local-authority controls.

### 6. Demonstrations

Demonstrations should be property-driven:

1. Provenance and review:
   - create source/observation/claim;
   - promote to canonical memory;
   - query with provenance.
2. Contradiction handling:
   - create contradictory claims;
   - sync contradiction case;
   - adjudicate without rewriting claims.
3. Release controls:
   - public export excludes internal/private records;
   - redacted derivative requires policy metadata.
4. Federation and local authority:
   - signed bundle import to quarantine;
   - local policy-gated promotion;
   - conflict detection.
5. ClaimWright operating stance:
   - show a claim moving from exploratory/private to public-safe through policy checks.
6. CiteGeist source review:
   - seed and export a bibliography;
   - preserve accepted/rejected/unresolved source review state where available.

### 7. Limitations

State explicitly:

- no production IAM;
- no hosted review UI;
- no semantic contradiction detection yet;
- no retrieval-performance benchmark claims;
- no CRDT sync;
- no complete exceptional-erasure propagation;
- no full ClaimWright-to-GroundRecall enforcement bridge yet;
- no comprehensive security proof.

### 8. Design Implications

The paper should close with design implications:

- memory layers should expose governance state to agents, not hide it behind retrieval scores;
- public-facing agent work needs publication gates, not just source retrieval;
- contradiction and stale-claim handling should be ordinary workflows;
- signed exchange is insufficient without local authority and quarantine;
- policy frameworks and memory substrates should be designed together.

## Recommended Claim Boundary

Claim:

Governed memory layers are feasible and necessary; the included prototypes demonstrate many of the required properties.

Do not claim:

- this is a complete governed-agent platform;
- the prototypes outperform memory-layer systems on recall benchmarks;
- ClaimWright policy enforcement is fully integrated into GroundRecall;
- semantic contradiction detection is solved.

## Immediate Revision Tasks

1. Rewrite the roadmap’s core claim around governed memory properties.
2. Add a property-to-implementation matrix.
3. Add a ClaimWright integration note.
4. Reorganize the eventual manuscript draft around properties before repos.
5. Keep GroundRecall as the main implementation example, not the sole subject.
