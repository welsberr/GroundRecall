# Memory Layers Should Be Governed: Properties For Durable AI Assistant And Agent Memory

Date: 2026-07-26

Status: first internal preprint draft.

## Abstract

Current AI memory systems increasingly support long-term recall, graph retrieval, personalization, and memory operating-system abstractions. These systems make assistants and agents more persistent, but persistence also makes familiar failures more durable: unsupported claims, stale context, hidden contradictions, citation drift, private-to-public leakage, unreviewed promotion, and ambiguous authority over shared memory.

We argue that memory layers for AI assistants and agents should be governed systems, not only retrieval systems. A governed memory layer should preserve provenance, distinguish historical support from current applicability, expose confidence and uncertainty, track contradiction and adjudication, enforce release boundaries, quarantine imported memory, retain audit history, and integrate explicit policy frameworks for reliable, evidence-driven work.

We present these requirements as a manifesto for governed AI memory. We then describe local-first prototype components that demonstrate many of the required properties: GroundRecall as a provenance-preserving, review-gated, federated memory substrate; ClaimWright as one suitable claim-policy and publication-safety framework; CiteGeist as a bibliography and source-review workbench; and Epistemap as a confidence and knowledge-graph operation layer. We treat these prototypes as evidence that governed memory is practical while identifying retrieval benchmarking, semantic contradiction detection, hosted review, production identity management, exceptional erasure propagation, and distributed synchronization as future work.

## 1. Memory Is Not Just Recall

Long-lived AI assistants and agents need memory. A system that remembers user preferences, project state, research sources, code decisions, and prior failures can be more useful than a system that starts from zero at every turn. This need has driven memory streams, retrieval-augmented generation, graph memories, long-term personalization layers, and memory operating-system proposals.

But durable memory changes the risk profile of assistant and agent systems. If memory persists, then unsupported claims persist. Stale assumptions persist. Incorrect citations persist. Private notes can become downstream public context. Contradictions can be smoothed over by retrieval ranking instead of confronted. A signed memory artifact can be mistaken for locally authorized memory. A polished summary can replace the evidence that should have remained available for review.

The core claim of this paper is that AI assistants and agents do not merely need more memory. They need governed memory layers.

A governed memory layer is not just a vector database, transcript store, or retrieval cache. It is a durable context substrate whose records carry provenance, confidence, temporal validity, release level, review status, contradiction state, policy constraints, and audit history. It treats memory promotion, memory sharing, contradiction resolution, and public use as governance events. It preserves disagreement and decision history rather than hiding them behind a single retrieval score.

This paper is written in manifesto mode. The argument starts from properties that memory layers should have, then uses prototype implementations as evidence that these properties are practical. GroundRecall is the main implementation example, but not the entire point. ClaimWright, CiteGeist, and Epistemap illustrate companion policy, source-review, and confidence/graph layers that support the same governed-memory stance.

## 2. Foreseeable Failure Modes

The current state of AI memory work is strong on persistence, retrieval, and personalization. It is weaker on the controls needed when persistent memory becomes a substrate for research, publication, organizational action, or multi-agent collaboration.

The foreseeable problems include:

- ungrounded summaries becoming durable context;
- citations remembered without accepted/rejected/unresolved review state;
- stale facts reused as current planning assumptions;
- contradictions resolved accidentally by retrieval ranking rather than explicit adjudication;
- public artifacts outrunning private or speculative grounding;
- private, internal, confidential, or privileged context leaking through export or federation;
- valid signatures being mistaken for local authority;
- imported memory overwriting local canonical memory;
- role or key distribution bypassing local policy;
- deletion being used where expiry, supersession, or confidence reduction would better preserve provenance.

These are not exotic edge cases. They are predictable outcomes when memory is optimized only for availability and relevance. If assistants are used to produce reliable, evidence-driven products, memory must also encode the conditions under which remembered material may be trusted, used, shared, challenged, revised, or published.

The threat model for the current prototype is modest. It does not claim protection against host compromise, complete regulatory compliance, production identity management, or a complete erasure propagation mechanism. It does claim that several important governance failures can be made explicit and reviewable at the memory-layer level: stale memory, ungrounded summaries, hidden contradictions, unreviewed imports, access broadening, stale trust, overbroad roles, and loss of audit history.

## 3. Required Properties Of Governed Memory Layers

This section states the normative core of the paper. A memory layer suitable for durable AI assistant and agent work should have at least the following properties.

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
| No access broadening | Export or federation should not make memory less restrictive without redaction or declassification authority. |
| Quarantine before promotion | Imported memory should be verified and quarantined before local acceptance. |
| Local authority | Signed memory, keys, and roles should not override receiver policy. |
| Auditability | Export, import, promotion, adjudication, and policy decisions should leave reviewable records. |
| Policy integration | Memory should be governed by explicit claim, publication, and action policies. |

These properties are deliberately orthogonal to retrieval performance. A memory layer can retrieve relevant material quickly while still being unsafe for evidence-driven work. Conversely, a governed memory layer may be slower or more conservative while being better suited to research, legal, organizational, or public-facing tasks.

The point is not that every personal assistant needs enterprise-grade policy on every memory write. Enforcement should vary with risk. Private exploratory work may use advisory policy. Durable, expensive, public, privacy-relevant, or authority-bearing actions should require stronger gates. The minimum claim is that memory should make such policy distinctions possible and inspectable.

## 4. Policy Pluralism And Common Policy Elements

Governed memory requires a policy stance, but not a single universal policy. Different users, teams, institutions, and jurisdictions will reasonably set different thresholds for evidence depth, adversarial review, privacy classification, model/tool risk, cost tolerance, and human sign-off.

ClaimWright is therefore best understood as one suitable policy framework, not as the policy framework. Its value for this paper is that it shows the kind of operational stance a memory layer can be coupled to: claim lifecycle states, citation review, confidence dimensions, role cards, public/private gates, and pre-action/post-action checks.

The generalizable point is narrower and stronger: reliable AI-assisted work needs explicit policy, and many policy elements are broadly applicable even when thresholds differ.

| Policy element | Broadly applicable requirement |
| --- | --- |
| Claim lifecycle | Claims should have states such as exploratory, supported, contested, stale, contradicted, private-only, and public-safe or equivalent. |
| Evidence traceability | Public or durable claims should identify their source basis and review status. |
| Citation review | Accepted, rejected, and unresolved citation candidates should remain inspectable. |
| Uncertainty visibility | Confidence, ambiguity, and limits of applicability should not be hidden by polished prose. |
| Contradiction review | Contradicted claims should trigger review or adjudication rather than silent selection. |
| Staleness review | New evidence should be able to mark related claims stale or superseded. |
| Public/private boundary | Movement from private exploration to public artifact should require stricter gates. |
| Role/authority boundaries | Agents should know whether they are auditing, drafting, publishing, maintaining memory, or escalating to a human. |
| Pre-action checks | Costly, durable, public, destructive, or privacy-relevant actions should check reversibility, evidence, assumptions, and authorization. |
| Post-action checks | Outputs should be checked for unsupported claims, citation drift, unresolved risks, and downstream memory effects. |

This policy-pluralist framing matters. It avoids treating one project’s values and thresholds as universal while still rejecting the idea that persistent AI memory can remain policy-neutral in high-stakes or public-facing use.

## 5. Example Prototype Components

The prototype components discussed here are not presented as a complete governed-agent platform. They are partial implementations and design probes.

GroundRecall is the main memory substrate. It implements typed records for sources, artifacts, observations, claims, concepts, relations, contradiction cases, promotions, adjudications, and snapshots. It supports review-gated promotion, query/export surfaces, confidence and temporal-validity metadata, release-level classification, signed federation bundles, quarantine-before-promotion import, local policy checks, audit events, trust registries, signed public keysets, and signed role directories.

ClaimWright is a companion policy framework. It provides a human-readable collaboration memorandum, machine-readable policy files, claim lifecycle states, confidence dimensions, mixed enforcement defaults, agent role cards, pre-action and post-action checks, citation review patterns, and a first public-safe artifact workflow. In the present work, ClaimWright is not yet an enforcement engine inside GroundRecall. It is an example of the sort of policy framework that a governed memory layer should be able to reflect and enforce.

CiteGeist is a bibliography workbench. It supports BibTeX-centered ingestion, reference extraction, verification, enrichment, citation-graph expansion, topic-aware review, and export. For this preprint, it has been used to seed a memory-layer bibliography and produce a local CiteGeist database and BibTeX export. It represents the source-review side of governed memory: citations and bibliographic claims should remain inspectable, not merely embedded in prose.

Epistemap is a confidence and knowledge-graph operation layer. GroundRecall already exposes Epistemap-compatible query and confidence surfaces. The intended role is to support evidence representation, confidence measures, graph operations, and future contradiction/confidence interactions. The current draft should be careful not to overclaim full calibration or broad empirical validation.

Together, these prototypes show a feasible decomposition:

- memory substrate: GroundRecall;
- policy stance: ClaimWright-like frameworks;
- source review: CiteGeist;
- confidence and graph operations: Epistemap.

## 6. Relation To Memory-Layer Systems

Recent memory-layer systems establish the importance of durable memory for agents. Generative Agents demonstrated memory streams, reflection, planning, and retrieval over remembered experience. MemGPT framed LLM memory in operating-system terms, treating context as scarce fast memory and external storage as backing memory. HippoRAG, A-MEM, and AriGraph show that graph organization can support multi-hop retrieval, contextual linking, and agent planning. Mem0 represents production-oriented memory extraction, consolidation, and retrieval. MemoryOS and MemOS develop explicit memory operating-system abstractions with tiers, scheduling, and lifecycle management.

This literature is strong on recall, personalization, graph retrieval, memory scheduling, and production performance. The visible gap is governance. Release classification, provenance-preserving review, contradiction adjudication, quarantine-before-promotion federation, local authority, and auditable cross-host exchange are not the central contributions of most memory-layer systems.

GroundRecall should therefore not be framed as “better memory” or as outperforming Mem0, HippoRAG, A-MEM, MemoryOS, or MemOS on retrieval benchmarks. That is not the current evidence. The better claim is complementary:

> GroundRecall-style governed memory supplies review, provenance, contradiction, release-policy, federation, and local-authority controls that performance-oriented memory layers often need but do not foreground.

This framing also clarifies future work. Retrieval benchmarks such as long-memory dialogue or multi-hop recall evaluations would be useful, but they are not prerequisites for the manifesto claim. The manifesto claim is about memory governance properties. The current evidence is engineering evidence from prototypes and tests, not broad empirical performance superiority.

## 7. GroundRecall As A Governed Memory Substrate

GroundRecall’s data model starts from typed, durable records rather than raw chat history. Observations carry provenance metadata. Claims reference source observations, supporting fragments, concepts, contradictions, superseded claims, confidence hints, assessments, and lifecycle status. Concepts and relations support graph-oriented query and export. Promotions and adjudications record review decisions. Snapshots provide deterministic export views.

The canonical lifecycle is:

```text
source/artifact
    ↓
observation extraction
    ↓
claim/concept/relation candidates
    ↓
review and promotion
    ↓
canonical store
    ↓
query/export/federation
```

The design principle is that ordinary epistemic maintenance should be non-destructive. If a fact expires, is superseded, becomes stale, or is contradicted, the system should preserve provenance and decision history while reducing current applicability or confidence. Exceptional erasure remains a separate privacy, legal, or security operation, not the ordinary model for knowledge maintenance.

GroundRecall’s recent contradiction-case workflow illustrates this stance. Explicit `contradicts_claim_ids` links can be materialized into deterministic contradiction case records. A case has participating claim IDs, case kind, status, severity, timestamps, rationale, metadata, and optional adjudication linkage. Diagnostics can flag contradiction links without cases, cases referencing missing claims, and open cases involving promoted claims. Adjudication records can target contradiction cases. The CLI can synchronize cases, list review batches, and adjudicate cases without rewriting the underlying claims.

This matters because contradiction is a common failure mode of durable memory. A system that simply retrieves the most relevant or most recent claim can hide disagreement. A governed memory layer should expose disagreement as review state.

## 8. Release Levels, Federation, And Local Authority

GroundRecall uses a release-level lattice:

```text
public < internal < confidential < privileged < private
```

The release lattice prevents obvious access broadening. `private` records are local-only. Public exports block internal, confidential, privileged, private, and unclassified records unless policy allows. Hidden or redacted basis can be represented explicitly as partial basis visibility. Derivatives require redaction or declassification metadata. Privileged federation requires explicit privileged allowance.

Federation is deliberately quarantine-first. A producer exports a signed, content-hashed bundle. A receiver verifies the signature, expected key ID, content hash, accepted release level, and bundle policy. Verification permits quarantine, not canonical acceptance. Promotion remains a separate local decision governed by release acceptance, local policy, conflict checks, and reviewer action.

This distinction is central:

> A valid signed memory artifact proves something about origin and integrity; it does not prove that the receiver should make the memory canonical.

GroundRecall extends this local-authority model to trust and role distribution. Trust registries record key material, active status, expiry, revocation, supersession, release levels, and trusted actions. Signed public keysets and signed role directories can be imported only through receiver-side caps. A hub can propose trust or role structure; the receiver decides the maximum authority it will accept.

## 9. Evaluation Evidence

The current evidence is engineering evidence. The full GroundRecall test suite passes as of the latest implementation pass. Tests cover store round trips, snapshots, query bundles, confidence profiles, release lattice behavior, federation signatures, quarantine import, promotion, policy decisions, scoped grants, audit events, trust registry lifecycle, Ed25519 signatures, signed keysets, signed role directories, contradiction case generation, contradiction diagnostics, federation of contradiction cases, and contradiction adjudication workflow.

The preprint should present these tests as evidence that the design properties are implemented in a local prototype. It should not treat them as evidence of improved user productivity, broad safety outcomes, or retrieval superiority. Those require different evaluation designs.

The claim-to-evidence matrix should be maintained as a live constraint on the manuscript. Each paper claim should map to one of:

- implemented code;
- test coverage;
- reproducible demonstration;
- bibliography/source analysis;
- explicit future-work status.

Claims that do not map to evidence should be softened or removed.

## 10. Demonstrations To Add

The manuscript needs reproducible demonstrations organized around properties rather than repositories.

Recommended demonstrations:

1. Provenance and review:
   - create source, observation, and claim records;
   - promote to canonical memory;
   - query with provenance.
2. Contradiction handling:
   - create contradictory claims;
   - synchronize a contradiction case;
   - adjudicate without rewriting claims.
3. Release controls:
   - seed public, internal, and private records;
   - export a public bundle;
   - show excluded records and policy findings.
4. Federation and local authority:
   - export a signed bundle;
   - import to quarantine;
   - promote only under matching local policy;
   - show conflict detection.
5. ClaimWright operating stance:
   - move a claim from exploratory/private toward public-safe status through policy checks.
6. CiteGeist source review:
   - seed a bibliography;
   - ingest into CiteGeist;
   - export reviewed BibTeX.

These demonstrations should live under `examples/preprint/` or `scripts/preprint/` and produce stable JSON/Markdown outputs that can be cited in the paper.

## 11. Limitations

This work should state its limitations plainly.

GroundRecall is file-backed and local-first, not a finished distributed memory platform. It has no network transport or polling layer, no CRDT merge system, no hosted review UI, no production IAM integration, and no public/internal release-pack publishing workflow. It does not yet provide automatic semantic contradiction detection. It has no complete exceptional-erasure propagation mechanism. It has not been benchmarked against memory-layer systems on long-dialogue recall, multi-hop retrieval, latency, cost, or personalization. It does not yet enforce ClaimWright policy files inside GroundRecall. It does not provide a comprehensive security proof.

These limitations bound the contribution. They do not defeat the core argument. The paper argues that governed memory properties are necessary and implementable. It does not claim that the current prototypes are complete.

## 12. Design Implications

The design implications are the main contribution of a manifesto-first paper.

First, memory layers should expose governance state to agents. Retrieval results should carry provenance, confidence, release level, temporal status, and contradiction/adjudication state where available.

Second, public-facing agent work needs publication gates, not just source retrieval. A citation being retrievable is not the same as a citation being reviewed, adequate, current, and safe to use publicly.

Third, contradiction and staleness handling should be ordinary workflows. Durable memory should expect claims to become stale, contested, contradicted, superseded, or retracted.

Fourth, signed exchange is insufficient without local authority. A memory artifact can be authentic and still unsuitable for local promotion.

Fifth, policy frameworks and memory substrates should be designed together. Policy should be configurable, because different entities will adopt different stances. But some explicit policy stance is necessary for reliable, evidence-driven assistant and agent work.

## 13. Conclusion

The next generation of AI assistants and agents will remember more. That is useful, but it is not enough. Durable memory should not simply make context persistent; it should make context inspectable, reviewable, scoped, challengeable, and governed.

This paper has argued for a property-first view of governed memory layers. A suitable memory layer should preserve provenance, gate promotion, represent confidence and temporal validity, track contradictions and adjudications, enforce release boundaries, quarantine imports, preserve audit history, respect local authority, and integrate explicit policy frameworks.

GroundRecall, ClaimWright, CiteGeist, and Epistemap provide partial local-first examples of these properties. They are not a complete governed-agent platform. They are evidence that governed memory can be built, inspected, tested, and improved.

The practical recommendation is direct: when building memory for AI assistants and agents, do not ask only how much the system can remember or how well it retrieves. Ask what the memory is allowed to mean, who reviewed it, where it came from, whether it is current, what it contradicts, who may see it, who may promote it, and what policy governs its use.

## References To Seed Bibliography

The current related-work seed is maintained in:

- `docs/preprint/memory-layer-bibliography.md`
- `docs/preprint/memory-layer-seed.bib`
- `docs/preprint/memory-layer-citegeist-export.bib`
- `docs/preprint/citegeist-memory-layer.sqlite3`

The manuscript should eventually convert these references into the target preprint venue format. Current seed topics include Generative Agents, MemGPT, HippoRAG, A-MEM, Mem0, MemoryOS, MemOS, AriGraph, LLM-agent memory surveys, and knowledge-graph/RAG alignment.
