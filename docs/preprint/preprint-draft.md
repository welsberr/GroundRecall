---
title: "Memory Layers Should Be Governed: Properties for Durable AI Assistant and Agent Memory"
date: 2026-07-26
bibliography: memory-layer-citegeist-export.bib
---

## Abstract

Current AI memory systems increasingly support long-term recall, graph retrieval, personalization, and memory operating-system abstractions. These systems make assistants and agents more persistent, but persistence also makes familiar failures more durable: unsupported claims, stale context, hidden contradictions, citation drift, private-to-public leakage, unreviewed promotion, and ambiguous authority over shared memory. We argue that memory layers for AI assistants and agents should be governed systems, not only retrieval systems. A governed memory layer preserves provenance, distinguishes historical support from current applicability, exposes confidence and uncertainty, tracks contradiction and adjudication, enforces release boundaries, quarantines imported memory, retains audit history, and integrates explicit policy frameworks for reliable, evidence-driven work. We present these requirements as a manifesto for governed AI memory and describe local-first prototype components that demonstrate many of the required properties: GroundRecall as a provenance-preserving, review-gated, federated memory substrate; ClaimWright as one suitable claim-policy and publication-safety framework; CiteGeist as a bibliography and source-review workbench; and Epistemap as a confidence and knowledge-graph operation layer. These prototypes show that governed memory is practical while leaving retrieval benchmarking, semantic contradiction detection, hosted review, production identity management, exceptional erasure propagation, and distributed synchronization as open work.

## 1. Introduction: Memory Is Not Just Recall

Long-lived AI assistants and agents need memory. A system that remembers user preferences, project state, research sources, code decisions, and prior failures can be more useful than a system that starts from zero at every turn. Recent work has therefore explored memory streams, long-term retrieval, graph-structured memory, production memory layers, and memory operating-system abstractions. Generative Agents used a natural-language memory stream, reflection, and retrieval to support believable agent behavior [1]. MemGPT framed long-context interaction as virtual context management across memory tiers [2]. HippoRAG connected LLMs, knowledge graphs, and Personalized PageRank for long-term multi-hop retrieval [3]. A-MEM proposed dynamically linked agentic memory inspired by Zettelkasten-style organization [4]. Mem0 presented a production-oriented long-term memory layer for AI agents [5]. MemoryOS and MemOS made the operating-system analogy explicit through hierarchical storage, lifecycle management, scheduling, and unified memory abstractions [6, 7].

These systems make AI agents more persistent. Persistence is useful, but it changes the risk profile of assistant and agent systems. If memory persists, unsupported claims persist. Stale assumptions persist. Incorrect citations persist. Private notes can become downstream public context. Contradictions can be smoothed over by retrieval ranking instead of confronted. A signed memory artifact can be mistaken for locally authorized memory. A polished summary can replace the evidence that should have remained available for review.

The central claim of this paper is that AI assistants and agents do not merely need more memory. They need governed memory layers.

A governed memory layer is not only a vector database, transcript store, or retrieval cache. It is a durable context substrate whose records carry provenance, confidence, temporal validity, release level, review status, contradiction state, policy constraints, and audit history. It treats memory promotion, memory sharing, contradiction resolution, and public use as governance events. It preserves disagreement and decision history rather than hiding them behind a single retrieval score.

This paper states the required properties first, then uses prototype systems as implementation evidence. GroundRecall is the main memory-substrate example. ClaimWright, CiteGeist, and Epistemap illustrate companion policy, source-review, and confidence/graph layers that support the same governed-memory stance.

## 2. Foreseeable Failure Modes

The current memory-layer literature is strong on persistence, retrieval, personalization, graph traversal, memory scheduling, and production deployment. Its center of gravity is less often governance. A system that optimizes for memory availability and relevance can still fail as an evidence-preserving substrate for research, publication, organizational action, or multi-agent collaboration.

The foreseeable failure modes include:

- ungrounded summaries becoming durable context;
- citations remembered without accepted, rejected, or unresolved review state;
- stale facts reused as current planning assumptions;
- contradictions resolved accidentally by retrieval ranking rather than explicit adjudication;
- public artifacts outrunning private or speculative grounding;
- private, internal, confidential, or privileged context leaking through export or federation;
- valid signatures being mistaken for local authority;
- imported memory overwriting local canonical memory;
- role or key distribution bypassing local policy;
- deletion being used where expiry, supersession, or confidence reduction would better preserve provenance.

These failures are not exotic. They follow from treating memory as a relevance mechanism without enough attention to authority, review, and lifecycle. If assistants are used to produce reliable, evidence-driven products, memory must encode the conditions under which remembered material may be trusted, used, shared, challenged, revised, or published.

The threat model here is scoped to memory-layer governance. It does not assume protection against host compromise, complete regulatory compliance, production identity management, or complete erasure propagation. It focuses on making several important governance failures explicit and reviewable at the memory-layer level: stale memory, ungrounded summaries, hidden contradictions, unreviewed imports, access broadening, stale trust, overbroad roles, and loss of audit history.

## 3. Required Properties of Governed Memory Layers

A memory layer suitable for durable AI assistant and agent work requires at least the following properties.

| Property | Requirement |
| --- | --- |
| Provenance preservation | Claims remain linked to observations, sources, citations, and derivation context. |
| Review-gated promotion | Candidate or imported memory does not silently become canonical. |
| Confidence structure | Confidence encodes dimensions and basis, not merely one scalar. |
| Temporal validity | The system distinguishes historical support from current applicability. |
| Non-destructive forgetting | Expiry, supersession, retraction, and confidence reduction preserve evidence history except where exceptional erasure is required. |
| Contradiction tracking | Contradictions become explicit cases, not hidden retrieval noise. |
| Adjudication history | Resolutions are recorded as review state without silently rewriting underlying claims. |
| Release classification | Memory carries public, internal, confidential, privileged, private, or equivalent release levels. |
| No access broadening | Export or federation does not make memory less restrictive without redaction or declassification authority. |
| Quarantine before promotion | Imported memory is verified and quarantined before local acceptance. |
| Local authority | Signed memory, keys, and roles do not override receiver policy. |
| Auditability | Export, import, promotion, adjudication, and policy decisions leave reviewable records. |
| Policy integration | Memory is governed by explicit claim, publication, and action policies. |

These properties are orthogonal to retrieval performance. A memory layer can retrieve relevant material quickly while remaining unsafe for evidence-driven work. Conversely, a governed memory layer may be slower or more conservative while being better suited to research, legal, organizational, or public-facing tasks.

The governance level can vary with risk. Private exploratory work may use advisory policy. Durable, expensive, public, privacy-relevant, or authority-bearing actions require stronger gates. The minimum requirement is that memory makes such distinctions possible and inspectable.

## 4. Policy Pluralism and Common Policy Elements

Governed memory requires a policy stance, but not a single universal policy. Different users, teams, institutions, and jurisdictions will set different thresholds for evidence depth, adversarial review, privacy classification, model/tool risk, cost tolerance, and human sign-off.

ClaimWright is one suitable policy framework, not the policy framework. Its role in this work is to demonstrate the kind of operational stance that a memory layer can reflect: claim lifecycle states, citation review, confidence dimensions, role cards, public/private gates, and pre-action/post-action checks.

The generalizable claim is narrower and stronger: reliable AI-assisted work needs explicit policy, and many policy elements are broadly applicable even when thresholds differ.

| Policy element | Broadly applicable requirement |
| --- | --- |
| Claim lifecycle | Claims have states such as exploratory, supported, contested, stale, contradicted, private-only, and public-safe or equivalent. |
| Evidence traceability | Public or durable claims identify their source basis and review status. |
| Citation review | Accepted, rejected, and unresolved citation candidates remain inspectable. |
| Uncertainty visibility | Confidence, ambiguity, and limits of applicability are not hidden by polished prose. |
| Contradiction review | Contradicted claims trigger review or adjudication rather than silent selection. |
| Staleness review | New evidence can mark related claims stale or superseded. |
| Public/private boundary | Movement from private exploration to public artifact requires stricter gates. |
| Role/authority boundaries | Agents know whether they are auditing, drafting, publishing, maintaining memory, or escalating to a human. |
| Pre-action checks | Costly, durable, public, destructive, or privacy-relevant actions check reversibility, evidence, assumptions, and authorization. |
| Post-action checks | Outputs are checked for unsupported claims, citation drift, unresolved risks, and downstream memory effects. |

Policy pluralism avoids treating one project’s values and thresholds as universal while still rejecting the idea that persistent AI memory can remain policy-neutral in high-stakes or public-facing use.

## 5. Prototype Components

The prototype components discussed here are partial implementations and design probes, not a complete governed-agent platform.

GroundRecall is the main memory substrate. It implements typed records for sources, artifacts, observations, claims, concepts, relations, contradiction cases, promotions, adjudications, and snapshots. It supports review-gated promotion, query/export surfaces, confidence and temporal-validity metadata, release-level classification, signed federation bundles, quarantine-before-promotion import, local policy checks, audit events, trust registries, signed public keysets, and signed role directories.

ClaimWright is a companion policy framework. It provides a human-readable collaboration memorandum, machine-readable policy files, claim lifecycle states, confidence dimensions, mixed enforcement defaults, agent role cards, pre-action and post-action checks, citation review patterns, and a public-safe artifact workflow. In the present implementation, ClaimWright is not an enforcement engine inside GroundRecall. It is an example of the sort of configurable policy framework that a governed memory layer can reflect and eventually enforce.

CiteGeist is a bibliography workbench. It supports BibTeX-centered ingestion, reference extraction, verification, enrichment, citation-graph expansion, topic-aware review, and export. For this paper, it was used to seed a memory-layer bibliography and produce a local CiteGeist database and BibTeX export. It represents the source-review side of governed memory: citations and bibliographic claims remain inspectable rather than merely embedded in prose.

Epistemap is a confidence and knowledge-graph operation layer. GroundRecall exposes Epistemap-compatible query and confidence surfaces. Its role is to support evidence representation, confidence measures, graph operations, and future contradiction/confidence interactions. The present evidence does not support claims of broad confidence calibration or empirical superiority.

Together, these prototypes show a feasible decomposition:

- memory substrate: GroundRecall;
- policy stance: ClaimWright-like frameworks;
- source review: CiteGeist;
- confidence and graph operations: Epistemap.

## 6. Relation to Memory-Layer Systems

Recent memory-layer systems establish the importance of durable memory for agents. A recent ACM TOIS survey organizes memory mechanisms for LLM-based agents around memory sources, forms, operations, and evaluation [10]. Generative Agents demonstrated memory streams, reflection, planning, and retrieval over remembered experience [1]. MemGPT framed long-context interaction as virtual context management across memory tiers [2]. HippoRAG combined LLMs, knowledge graphs, and Personalized PageRank for long-term multi-hop retrieval [3]. A-MEM proposed dynamically organized agentic memory with historical memory linking and evolution [4]. Mem0 presented a production-oriented long-term memory layer with extraction, consolidation, retrieval, and a graph-memory variant [5]. MemoryOS and MemOS developed memory operating-system abstractions with memory tiers, lifecycle control, scheduling, and unified memory units [6, 7]. AriGraph used a semantic and episodic knowledge-graph world model for agent planning [8]. Work on knowledge-graph alignment for retrieval-augmented generation also shows that graph representation and linearization choices affect downstream LLM use of graph knowledge [9].

This literature is strong on recall, personalization, graph retrieval, memory scheduling, and production performance. The visible gap is governance. Release classification, provenance-preserving review, contradiction adjudication, quarantine-before-promotion federation, local authority, and auditable cross-host exchange are not the central contributions of most memory-layer systems.

GroundRecall-style governed memory is therefore complementary to performance-oriented memory layers:

> Governed memory supplies review, provenance, contradiction, release-policy, federation, and local-authority controls that memory systems often need but do not foreground.

This framing avoids an unsupported performance comparison. GroundRecall has not been evaluated against Mem0, HippoRAG, A-MEM, MemoryOS, or MemOS on long-dialogue recall, multi-hop retrieval, cost, latency, or personalization benchmarks. Its current evidence is engineering evidence for governance properties.

## 7. GroundRecall as a Governed Memory Substrate

GroundRecall’s data model starts from typed durable records rather than raw chat history. Observations carry provenance metadata. Claims reference source observations, supporting fragments, concepts, contradictions, superseded claims, confidence hints, assessments, and lifecycle status. Concepts and relations support graph-oriented query and export. Promotions and adjudications record review decisions. Snapshots provide deterministic export views.

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

The design principle is that ordinary epistemic maintenance is non-destructive. If a fact expires, is superseded, becomes stale, or is contradicted, the system preserves provenance and decision history while reducing current applicability or confidence. Exceptional erasure remains a separate privacy, legal, or security operation, not the ordinary model for knowledge maintenance.

GroundRecall’s contradiction-case workflow illustrates this stance. Explicit `contradicts_claim_ids` links can be materialized into deterministic contradiction case records. A case has participating claim IDs, case kind, status, severity, timestamps, rationale, metadata, and optional adjudication linkage. Diagnostics flag contradiction links without cases, cases referencing missing claims, and open cases involving promoted claims. Adjudication records can target contradiction cases. The CLI synchronizes cases, lists review batches, and adjudicates cases without rewriting the underlying claims.

This matters because contradiction is a common failure mode of durable memory. A system that retrieves the most relevant or most recent claim can hide disagreement. A governed memory layer exposes disagreement as review state.

## 8. Release Levels, Federation, and Local Authority

GroundRecall uses a release-level lattice:

```text
public < internal < confidential < privileged < private
```

The release lattice prevents obvious access broadening. `private` records are local-only. Public exports block internal, confidential, privileged, private, and unclassified records unless policy allows. Hidden or redacted basis can be represented explicitly as partial basis visibility. Derivatives require redaction or declassification metadata. Privileged federation requires explicit privileged allowance.

Federation is quarantine-first. A producer exports a signed, content-hashed bundle. A receiver verifies the signature, expected key ID, content hash, accepted release level, and bundle policy. Verification permits quarantine, not canonical acceptance. Promotion remains a separate local decision governed by release acceptance, local policy, conflict checks, and reviewer action.

This distinction is central:

> A valid signed memory artifact proves something about origin and integrity; it does not prove that the receiver should make the memory canonical.

GroundRecall extends this local-authority model to trust and role distribution. Trust registries record key material, active status, expiry, revocation, supersession, release levels, and trusted actions. Signed public keysets and signed role directories can be imported only through receiver-side caps. A hub can propose trust or role structure; the receiver decides the maximum authority it accepts.

## 9. Evaluation Evidence

The current evidence is engineering evidence. The full GroundRecall test suite passes as of the latest implementation pass. Tests cover store round trips, snapshots, query bundles, confidence profiles, release lattice behavior, federation signatures, quarantine import, promotion, policy decisions, scoped grants, audit events, trust registry lifecycle, Ed25519 signatures, signed keysets, signed role directories, contradiction case generation, contradiction diagnostics, federation of contradiction cases, and contradiction adjudication workflow.

This evidence supports implementation claims about governed-memory properties in a local prototype. It does not establish improved user productivity, broad safety outcomes, retrieval superiority, or production security. Those claims require different evaluation designs.

The claim-to-evidence discipline is simple: each paper claim maps to implemented code, test coverage, reproducible demonstration, bibliography/source analysis, or explicit future-work status. Claims that do not map to evidence are softened or removed.

## 10. Demonstrations and Reproducibility

The current repository contains documentation artifacts, a CiteGeist-seeded bibliography database, BibTeX exports, and HTML renderings of the manuscript planning materials. Reproducible demonstrations remain the next missing evidence layer.

The demonstration set is organized by property:

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

These demonstrations are not yet a substitute for benchmark evaluation. They are reproducibility artifacts for the paper’s engineering claims.

## 11. Limitations

GroundRecall is file-backed and local-first, not a finished distributed memory platform. It has no network transport or polling layer, no CRDT merge system, no hosted review UI, no production IAM integration, and no public/internal release-pack publishing workflow. It does not yet provide automatic semantic contradiction detection. It has no complete exceptional-erasure propagation mechanism. It has not been benchmarked against memory-layer systems on long-dialogue recall, multi-hop retrieval, latency, cost, or personalization. It does not yet enforce ClaimWright policy files inside GroundRecall. It does not provide a comprehensive security proof.

These limitations bound the contribution. They do not defeat the core argument. Governed memory properties are necessary and implementable; the current prototypes are partial evidence, not complete systems.

## 12. Design Implications

The design implications follow directly from the property list.

First, memory layers expose governance state to agents. Retrieval results carry provenance, confidence, release level, temporal status, and contradiction/adjudication state where available.

Second, public-facing agent work requires publication gates, not just source retrieval. A citation being retrievable is not the same as a citation being reviewed, adequate, current, and safe to use publicly.

Third, contradiction and staleness handling are ordinary workflows. Durable memory expects claims to become stale, contested, contradicted, superseded, or retracted.

Fourth, signed exchange is insufficient without local authority. A memory artifact can be authentic and still unsuitable for local promotion.

Fifth, policy frameworks and memory substrates are designed together. Policy is configurable because different entities adopt different stances. Some explicit policy stance is nevertheless necessary for reliable, evidence-driven assistant and agent work.

## 13. Conclusion

The next generation of AI assistants and agents will remember more. That is useful, but not sufficient. Durable memory should not simply make context persistent; it should make context inspectable, reviewable, scoped, challengeable, and governed.

This paper has argued for a property-first view of governed memory layers. A suitable memory layer preserves provenance, gates promotion, represents confidence and temporal validity, tracks contradictions and adjudications, enforces release boundaries, quarantines imports, preserves audit history, respects local authority, and integrates explicit policy frameworks.

GroundRecall, ClaimWright, CiteGeist, and Epistemap provide partial local-first examples of these properties. They are not a complete governed-agent platform. They are evidence that governed memory can be built, inspected, tested, and improved.

The practical recommendation is direct: when building memory for AI assistants and agents, do not ask only how much the system can remember or how well it retrieves. Ask what the memory is allowed to mean, who reviewed it, where it came from, whether it is current, what it contradicts, who may see it, who may promote it, and what policy governs its use.

## References

1. Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy Liang, and Michael S. Bernstein. "Generative Agents: Interactive Simulacra of Human Behavior." *Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology*, 2023. DOI: [10.1145/3586183.3606763](https://doi.org/10.1145/3586183.3606763). Source: <https://research.google/pubs/generative-agents-interactive-simulacra-of-human-behavior/>.
2. Charles Packer, Sarah Wooders, Kevin Lin, Vivian Fang, Shishir G. Patil, Ion Stoica, and Joseph E. Gonzalez. "MemGPT: Towards LLMs as Operating Systems." arXiv:2310.08560, submitted 2023, revised 2024. DOI: [10.48550/arXiv.2310.08560](https://doi.org/10.48550/arXiv.2310.08560). Source: <https://arxiv.org/abs/2310.08560>.
3. Bernal Jiménez Gutiérrez, Yiheng Shu, Yu Gu, Michihiro Yasunaga, and Yu Su. "HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models." *Advances in Neural Information Processing Systems*, 2024. DOI: [10.52202/079017-1902](https://doi.org/10.52202/079017-1902). Source: <https://mlanthology.org/neurips/2024/gutierrez2024neurips-hipporag/>.
4. Wujiang Xu, Zujie Liang, Kai Mei, Hang Gao, Juntao Tan, and Yongfeng Zhang. "A-MEM: Agentic Memory for LLM Agents." arXiv:2502.12110, 2025. DOI: [10.48550/arXiv.2502.12110](https://doi.org/10.48550/arXiv.2502.12110). Source: <https://arxiv.org/abs/2502.12110>.
5. Prateek Chhikara, Dev Khant, Saket Aryan, Taranjeet Singh, and Deshraj Yadav. "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory." arXiv:2504.19413, 2025. DOI: [10.48550/arXiv.2504.19413](https://doi.org/10.48550/arXiv.2504.19413). Source: <https://arxiv.org/abs/2504.19413>.
6. Jiazheng Kang, Mingming Ji, Zhe Zhao, and Ting Bai. "Memory OS of AI Agent." arXiv:2506.06326, 2025. DOI: [10.48550/arXiv.2506.06326](https://doi.org/10.48550/arXiv.2506.06326). Source: <https://arxiv.org/abs/2506.06326>.
7. Zhiyu Li et al. "MemOS: A Memory OS for AI System." arXiv:2507.03724, 2025. DOI: [10.48550/arXiv.2507.03724](https://doi.org/10.48550/arXiv.2507.03724). Source: <https://arxiv.org/abs/2507.03724>.
8. Petr Anokhin, Nikita Semenov, Artyom Sorokin, Dmitry Evseev, Andrey Kravchenko, Mikhail Burtsev, and Evgeny Burnaev. "AriGraph: Learning Knowledge Graph World Models with Episodic Memory for LLM Agents." *Proceedings of the Thirty-Fourth International Joint Conference on Artificial Intelligence*, 2025, pp. 12--20. DOI: [10.24963/ijcai.2025/2](https://doi.org/10.24963/ijcai.2025/2). Source: <https://www.ijcai.org/proceedings/2025/0002>.
9. Shiyu Tian, Shuyue Xing, Xingrui Li, Yangyang Luo, Caixia Yuan, Wei Chen, Huixing Jiang, and Xiaojie Wang. "A Systematic Exploration of Knowledge Graph Alignment with Large Language Models in Retrieval Augmented Generation." *Proceedings of the AAAI Conference on Artificial Intelligence*, 39(24), 2025, pp. 25291--25299. DOI: [10.1609/aaai.v39i24.34716](https://doi.org/10.1609/aaai.v39i24.34716). Source: <https://ojs.aaai.org/index.php/AAAI/article/view/34716>.
10. Zeyu Zhang, Quanyu Dai, Xiaohe Bo, Chen Ma, Rui Li, Xu Chen, Jieming Zhu, Zhenhua Dong, and Ji-Rong Wen. "A Survey on the Memory Mechanism of Large Language Model-based Agents." *ACM Transactions on Information Systems*, 43(6), article 155, 2025, pp. 1--47. DOI: [10.1145/3748302](https://doi.org/10.1145/3748302). Source: <https://dl.acm.org/doi/10.1145/3748302>.
