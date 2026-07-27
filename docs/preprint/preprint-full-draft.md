---
title: "Memory Layers Should Be Governed: Properties for Durable AI Assistant and Agent Memory"
author: "Wesley R. Elsberry, Ph.D. (elsberry@msu.edu)"
date: 2026-07-26
bibliography: memory-layer-citegeist-export.bib
---

## Abstract

Current AI memory systems increasingly support long-term recall, graph retrieval, personalization, and memory operating-system abstractions. These systems make assistants and agents more persistent, but persistence also makes familiar failures more durable: unsupported claims, stale context, hidden contradictions, citation drift, private-to-public leakage, unreviewed promotion, and ambiguous authority over shared memory. We argue that memory layers for AI assistants and agents should be governed systems, not only retrieval systems. A governed memory layer preserves provenance, distinguishes historical support from current applicability, exposes confidence and uncertainty, tracks contradiction and adjudication, enforces release boundaries, quarantines imported memory, retains audit history, and integrates explicit policy frameworks for reliable, evidence-driven work. We present these requirements as a manifesto for governed AI memory and describe local-first prototype components that demonstrate several of the required controls: GroundRecall as a provenance-preserving, review-gated, federated memory substrate; ClaimWright as one suitable claim-policy and publication-safety framework; CiteGeist as a bibliography and source-review workbench; and Epistemap as a confidence and knowledge-graph operation layer. These prototypes show that governed-memory controls can be implemented in a local prototype while leaving retrieval benchmarking, semantic contradiction detection, hosted review, production identity management, exceptional erasure propagation, distributed synchronization, and broader governance/security literature integration as open work.

## 1. Introduction: Memory Is Not Just Recall

Long-lived AI assistants and agents need memory. A system that remembers user preferences, project state, research sources, code decisions, and prior failures can be more useful than a system that starts from zero at every turn. Recent work has therefore explored memory streams, long-term retrieval, graph-structured memory, production memory layers, and memory operating-system abstractions. Generative Agents used a natural-language memory stream, reflection, and retrieval to support believable agent behavior [1]. MemGPT framed long-context interaction as virtual context management across memory tiers [2]. HippoRAG connected LLMs, knowledge graphs, and Personalized PageRank for long-term multi-hop retrieval [3]. A-MEM proposed dynamically linked agentic memory inspired by Zettelkasten-style organization [4]. Mem0 presented a production-oriented long-term memory layer for AI agents [5]. MemoryOS and MemOS made the operating-system analogy explicit through hierarchical storage, lifecycle management, scheduling, and unified memory abstractions [6, 7].

These systems make AI agents more persistent. Persistence is useful, but it changes the risk profile of assistant and agent systems. If memory persists, unsupported claims persist. Stale assumptions persist. Incorrect citations persist. Private notes can become downstream public context. Contradictions can be smoothed over by retrieval ranking instead of confronted. A signed memory artifact can be mistaken for locally authorized memory. A polished summary can replace the evidence that should have remained available for review.

The central claim of this paper is that AI assistants and agents do not merely need more memory. They need governed memory layers.

A governed memory layer is not only a vector database, transcript store, or retrieval cache. It is a durable context substrate whose records carry provenance, confidence, temporal validity, release level, review status, contradiction state, policy constraints, and audit history. It treats memory promotion, memory sharing, contradiction resolution, and public use as governance events. It preserves disagreement and decision history rather than hiding them behind a single retrieval score.

This paper states the required properties first, then uses prototype systems as implementation evidence. GroundRecall is the main memory-substrate example. ClaimWright, CiteGeist, and Epistemap illustrate companion policy, source-review, and confidence/graph layers that support the same governed-memory stance.

## 2. Foreseeable Failure Modes

The current memory-layer literature is strong on persistence, retrieval, personalization, graph traversal, memory scheduling, and production deployment. The sources reviewed for this draft foreground governance less often than retrieval and memory-management performance. A system that optimizes for memory availability and relevance can still fail as an evidence-preserving substrate for research, publication, organizational action, or multi-agent collaboration.

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

These properties are orthogonal to retrieval performance. A memory layer can retrieve relevant material quickly while still lacking the review, provenance, and release controls needed for evidence-driven work. Conversely, a governed memory layer may be slower or more conservative while being better suited to research, legal, organizational, or public-facing tasks.

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

The prototype components discussed here are partial implementations and design probes, not a complete governed-agent platform or a validated safety intervention.

GroundRecall is the main memory substrate. It implements typed records for sources, artifacts, observations, claims, concepts, relations, contradiction cases, promotions, adjudications, and snapshots. It supports review-gated promotion, query/export surfaces, confidence and temporal-validity metadata, release-level classification, signed federation bundles, quarantine-before-promotion import, local policy checks, audit events, trust registries, signed public keysets, and signed role directories.

ClaimWright is a companion policy framework. It provides a human-readable collaboration memorandum, machine-readable policy files, claim lifecycle states, confidence dimensions, mixed enforcement defaults, agent role cards, pre-action and post-action checks, citation review patterns, and a public-safe artifact workflow. In the present implementation, ClaimWright is not an enforcement engine inside GroundRecall. It is an example of the sort of configurable policy framework that a governed memory layer can reflect and eventually enforce.

CiteGeist is a bibliography workbench. It supports BibTeX-centered ingestion, reference extraction, verification, enrichment, citation-graph expansion, topic-aware review, and export. For this paper, it was used to seed a memory-layer bibliography and produce a local CiteGeist database and BibTeX export. That seed supports initial related-work framing, not systematic-review completeness. CiteGeist represents the source-review side of governed memory: citations and bibliographic claims remain inspectable rather than merely embedded in prose.

Epistemap is a confidence and knowledge-graph operation layer. GroundRecall exposes Epistemap-compatible query and confidence surfaces. Its role is to support evidence representation, confidence measures, graph operations, and future contradiction/confidence interactions. The present evidence does not support claims of broad confidence calibration or empirical superiority.

Together, these prototypes show a feasible decomposition:

- memory substrate: GroundRecall;
- policy stance: ClaimWright-like frameworks;
- source review: CiteGeist;
- confidence and graph operations: Epistemap.

## 6. Relation to Memory-Layer Systems

Recent memory-layer systems establish the importance of durable memory for agents. A recent ACM TOIS survey organizes memory mechanisms for LLM-based agents around memory sources, forms, operations, and evaluation [10]. Generative Agents demonstrated memory streams, reflection, planning, and retrieval over remembered experience [1]. MemGPT framed long-context interaction as virtual context management across memory tiers [2]. HippoRAG combined LLMs, knowledge graphs, and Personalized PageRank for long-term multi-hop retrieval [3]. A-MEM proposed dynamically organized agentic memory with historical memory linking and evolution [4]. Mem0 presented a production-oriented long-term memory layer with extraction, consolidation, retrieval, and a graph-memory variant [5]. MemoryOS and MemOS developed memory operating-system abstractions with memory tiers, lifecycle control, scheduling, and unified memory units [6, 7]. AriGraph used a semantic and episodic knowledge-graph world model for agent planning [8]. Work on knowledge-graph alignment for retrieval-augmented generation also shows that graph representation and linearization choices affect downstream LLM use of graph knowledge [9].

The governance side of the argument draws on adjacent standards and security literature. The NIST AI RMF frames AI risk management around govern, map, measure, and manage functions and trustworthy-system characteristics [11]. NIST SP 800-53 provides a security and privacy control catalog covering access control, audit and accountability, identification and authentication, privacy, and supply-chain risk management [12]. NIST SP 800-207 frames zero trust as a move away from implicit trust toward resource- and identity-centered policy decisions [13]. W3C PROV defines interoperable provenance concepts for entities, activities, agents, derivation, and bundles [14, 15]. SLSA, Sigstore, and The Update Framework provide software-supply-chain analogues for verifiable provenance, transparency logs, signed metadata, roles, and key-compromise resilience [16, 17, 18]. Recent distributed access-control survey work reinforces that access control remains a core defense for distributed systems and organizational security [19].

Within this reviewed set, the most visible contributions concern recall, personalization, graph retrieval, memory scheduling, and production performance. Governance is less central. Release classification, provenance-preserving review, contradiction adjudication, quarantine-before-promotion federation, local authority, and auditable cross-host exchange appear as complementary controls rather than the main contribution of most reviewed memory-layer systems.

GroundRecall-style governed memory is therefore complementary to performance-oriented memory layers:

> Governed memory supplies review, provenance, contradiction, release-policy, federation, and local-authority controls that performance-oriented memory systems may need even when those controls are not their central contribution.

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

The current evidence is engineering evidence. The GroundRecall test suite passed on 2026-07-27 with 171 tests passing. Tests cover store round trips, snapshots, query bundles, confidence profiles, release lattice behavior, federation signatures, quarantine import, promotion, policy decisions, scoped grants, audit events, trust registry lifecycle, Ed25519 signatures, signed keysets, signed role directories, contradiction case generation, contradiction diagnostics, federation of contradiction cases, and contradiction adjudication workflow.

This evidence supports implementation claims about governed-memory properties in a local prototype. It does not establish improved user productivity, broad safety outcomes, retrieval superiority, or production security. Those claims require different evaluation designs.

The claim-to-evidence discipline is simple: each paper claim maps to implemented code, test coverage, reproducible demonstration, bibliography/source analysis, or explicit future-work status. Appendix A provides the current claim-to-evidence matrix. A separate ClaimWright review record applies claim-auditor, citation-reviewer, adversarial-reviewer, and publication-gatekeeper procedures to the draft. Claims that do not map to evidence are softened or removed.

The ClaimWright review result is conditional. The draft is suitable for internal and public draft review, but it is not yet final-public-safe. Before submission or authoritative publication, the paper needs a broader governance/security bibliography pass, stable reproducible demonstrations, and final human publication approval.

## 10. Demonstrations and Reproducibility

The current repository contains documentation artifacts, a CiteGeist-seeded bibliography database, BibTeX exports, HTML renderings of the manuscript planning materials, and a reproducible demonstration runner at `examples/preprint/run_preprint_demos.py`. The demonstration runner writes JSON summaries under `examples/preprint/out/`.

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

The current generated outputs are `provenance_promotion.json`, `contradiction_adjudication.json`, `release_filtering.json`, `federation_quarantine.json`, `local_authority.json`, and `manifest.json`. These demonstrations are not a substitute for benchmark evaluation. They are reproducibility artifacts for the paper’s engineering claims.

## 11. Limitations

GroundRecall is file-backed and local-first, not a finished distributed memory platform. It has no network transport or polling layer, no CRDT merge system, no hosted review UI, no production IAM integration, and no public/internal release-pack publishing workflow. It does not yet provide automatic semantic contradiction detection. It has no complete exceptional-erasure propagation mechanism. It has not been benchmarked against memory-layer systems on long-dialogue recall, multi-hop retrieval, latency, cost, or personalization. It does not yet enforce ClaimWright policy files inside GroundRecall. It does not provide a comprehensive security proof. The related-work section now includes initial governance, provenance, access-control, zero-trust, and supply-chain-security sources, but it is still not a full systematic review.

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

## Acknowledgments

The author acknowledges assistance from OpenAI Codex in drafting, editing, source organization, bibliography preparation, demonstration generation, and ClaimWright-style review of this manuscript. The author remains responsible for the claims, judgment, and final publication decisions.

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
11. Elham Tabassi. *Artificial Intelligence Risk Management Framework (AI RMF 1.0).* National Institute of Standards and Technology, NIST AI 100-1, 2023. DOI: [10.6028/NIST.AI.100-1](https://doi.org/10.6028/NIST.AI.100-1). Source: <https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10>.
12. Joint Task Force. *Security and Privacy Controls for Information Systems and Organizations.* National Institute of Standards and Technology, NIST SP 800-53 Rev. 5, 2020. DOI: [10.6028/NIST.SP.800-53r5](https://doi.org/10.6028/NIST.SP.800-53r5). Source: <https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final>.
13. Scott Rose, Oliver Borchert, Stu Mitchell, and Sean Connelly. *Zero Trust Architecture.* National Institute of Standards and Technology, NIST SP 800-207, 2020. DOI: [10.6028/NIST.SP.800-207](https://doi.org/10.6028/NIST.SP.800-207). Source: <https://www.nist.gov/publications/zero-trust-architecture-0>.
14. Paul Groth and Luc Moreau. *PROV-Overview: An Overview of the PROV Family of Documents.* W3C Working Group Note, 2013. Source: <https://www.w3.org/TR/prov-overview/>.
15. Luc Moreau and Paolo Missier. *PROV-DM: The PROV Data Model.* W3C Recommendation, 2013. Source: <https://www.w3.org/TR/prov-dm/>.
16. SLSA Contributors. *SLSA v1.2 Provenance.* 2026. Source: <https://slsa.dev/spec/v1.2/provenance>.
17. Sigstore. *What is Sigstore?* 2026. Source: <https://www.sigstore.dev/docs/what_is_sigstore>.
18. The Update Framework. *The Update Framework Specification.* 2026. Source: <https://theupdateframework.github.io/specification/>.
19. Lewis Golightly, Paolo Modesti, Rémi Garcia, and Victor Chang. "Securing Distributed Systems: A Survey on Access Control Techniques for Cloud, Blockchain, IoT and SDN." *Cyber Security and Applications*, 1, article 100015, 2023. DOI: [10.1016/j.csa.2023.100015](https://doi.org/10.1016/j.csa.2023.100015). Source: <https://www.sciencedirect.com/science/article/pii/S2772918423000036>.

\newpage

# Appendix A: Claim-To-Evidence Matrix

This appendix substantiates the manuscript discipline that each substantive paper claim maps to one of five evidence classes:

1. implemented code;
2. test coverage;
3. reproducible demonstration;
4. bibliography or source analysis;
5. explicit future-work status.

The matrix is also a restraint mechanism. Claims with only normative support are stated as design recommendations. Claims about implementation are limited to current code and tests. Claims about comparative performance, production deployment, semantic contradiction detection, and broad safety outcomes are marked as future work or excluded.

### Evidence Classes

| Evidence class | Meaning in this paper | Acceptable manuscript use |
| --- | --- | --- |
| Implemented code | A feature exists in the GroundRecall, ClaimWright, CiteGeist, or Epistemap repositories. | Supports "the prototype implements" or "the system exposes" claims when scoped to the current repository state. |
| Test coverage | Automated tests exercise the behavior. | Supports engineering evidence claims, not broad empirical performance claims. |
| Reproducible demonstration | A command, example, or generated artifact can reproduce a paper-visible behavior. | Supports manuscript examples and appendix walkthroughs. |
| Bibliography/source analysis | External literature or source review supports the framing. | Supports related-work and comparative-positioning claims. |
| Future-work status | The repository or manuscript explicitly identifies a missing capability. | Supports limitation and roadmap claims only. |

### Core Manuscript Claims

| Manuscript claim | Evidence class | Supporting artifacts | Current status | Caveat / restraint |
| --- | --- | --- | --- | --- |
| Durable AI memory needs governance, not only retrieval. | Bibliography/source analysis; design argument | `docs/preprint/preprint-draft.md`; `docs/preprint/memory-layer-comparative-analysis.md`; `docs/preprint/memory-layer-bibliography.md`; `docs/preprint/memory-layer-citegeist-export.bib` | Supported as a normative/design thesis. | Not an empirical proof that governed memory improves productivity or safety outcomes. |
| Current memory-layer systems foreground persistence, retrieval, graph organization, personalization, and memory-OS abstractions. | Bibliography/source analysis | References to Generative Agents, MemGPT, HippoRAG, A-MEM, Mem0, MemoryOS, MemOS, AriGraph, KG/RAG alignment, and an ACM TOIS memory-mechanism survey in `docs/preprint/preprint-draft.md` | Supported for related-work framing. | Bibliography is seeded, not exhaustive. |
| Governed memory draws on adjacent governance, provenance, access-control, zero-trust, and supply-chain-security patterns. | Bibliography/source analysis | NIST AI RMF, NIST SP 800-53, NIST SP 800-207, W3C PROV, SLSA, Sigstore, The Update Framework, and distributed access-control survey entries in `docs/preprint/memory-layer-citegeist-export.bib` | Supported for initial adjacent-literature framing. | Still not a systematic review of all governance/security literature. |
| GroundRecall is complementary to performance-oriented memory layers. | Bibliography/source analysis; implemented code | `docs/preprint/preprint-draft.md`; `docs/preprint/memory-layer-comparative-analysis.md`; GroundRecall governance features listed below | Supported as comparative positioning. | No benchmark comparison against Mem0, HippoRAG, A-MEM, MemoryOS, or MemOS. |
| ClaimWright is one suitable policy framework, not a universal stance. | Implemented code; design argument | ClaimWright repository policy substrate; `docs/preprint/preprint-draft.md` policy-pluralism section | Supported as an example policy stance. | ClaimWright policy files are not yet enforced directly inside GroundRecall. |
| CiteGeist provides a source-review and bibliography workbench relevant to governed memory. | Implemented code; reproducible artifact; bibliography/source analysis | CiteGeist repository; `docs/preprint/citegeist-memory-layer.sqlite3`; `docs/preprint/memory-layer-citegeist-export.bib`; `docs/preprint/memory-layer-bibliography.md` | Supported for bibliography seeding and source-review framing. | The current bibliography is not comprehensive and does not yet include a formal systematic-review protocol. |
| Epistemap provides a confidence and knowledge-graph operation layer relevant to governed memory. | Implemented code; test coverage | Epistemap repository; `src/groundrecall/epistemap_adapter.py`; `tests/test_epistemap_adapter.py`; `tests/test_claim_evaluation_export.py` | Supported for adapter/export surfaces. | Broad confidence calibration and cross-repository posterior validation remain future work. |

### GroundRecall Implementation Claims

| Manuscript claim | Evidence class | Supporting code | Supporting tests / artifacts | Current status | Caveat / restraint |
| --- | --- | --- | --- | --- | --- |
| GroundRecall stores durable memory as typed records rather than raw chat history alone. | Implemented code; test coverage | `src/groundrecall/models.py`; `src/groundrecall/store.py`; `src/groundrecall/groundrecall_models.py`; `src/groundrecall/groundrecall_store.py` | `tests/test_groundrecall_store.py` | Supported. | File-backed local prototype, not a distributed database. |
| Observations, claims, concepts, relations, promotions, adjudications, contradiction cases, and snapshots are first-class record types. | Implemented code; test coverage | `src/groundrecall/models.py`; `src/groundrecall/store.py` | `tests/test_groundrecall_store.py`; `tests/test_groundrecall_promotion.py`; `tests/test_contradictions.py` | Supported. | The supported claim is limited to the implemented record set, not every possible governance object. |
| Provenance is preserved across source, observation, claim, query, and export flows. | Implemented code; test coverage | `src/groundrecall/store.py`; `src/groundrecall/query.py`; `src/groundrecall/export.py`; `src/groundrecall/review_export.py` | `tests/test_groundrecall_store.py`; `tests/test_groundrecall_query.py`; `tests/test_groundrecall_export.py`; `tests/test_export_guardrails.py` | Supported for stored/queryable/exportable provenance metadata. | Extraction correctness depends on upstream adapters and review; the store does not guarantee source interpretation quality. |
| Review-gated promotion prevents candidate material from silently becoming canonical memory. | Implemented code; test coverage | `src/groundrecall/promotion.py`; `src/groundrecall/groundrecall_promotion.py`; `src/groundrecall/lint.py` | `tests/test_groundrecall_promotion.py`; `tests/test_relation_review.py`; `tests/test_groundrecall_review_workspace.py` | Supported. | Review UI and workflow ergonomics are prototype-level. |
| GroundRecall can expose query bundles with supporting provenance, graph context, contradictions, and supersessions. | Implemented code; test coverage | `src/groundrecall/query.py`; `src/groundrecall/groundrecall_query.py`; `src/groundrecall/graph_augment.py` | `tests/test_groundrecall_query.py`; `tests/test_graph_augment.py`; `tests/test_graph_diagnostics.py` | Supported. | This is a retrieval and packaging claim, not a benchmark claim. |
| Confidence is structured and reviewable rather than only a scalar hint. | Implemented code; test coverage | `src/groundrecall/confidence.py`; `src/groundrecall/epistemap_adapter.py` | `tests/test_confidence_profiles.py`; `tests/test_confidence_migration.py`; `tests/test_epistemap_adapter.py` | Supported for confidence profiles, assessments, temporal blocks, and migration/readiness reports. | The paper must not claim Bayesian calibration unless Epistemap/GroundRecall implements and validates it explicitly. |
| Temporal validity and expiry affect current applicability without erasing historical support. | Implemented code; test coverage | `src/groundrecall/confidence.py`; `src/groundrecall/query.py`; model metadata fields | `tests/test_confidence_profiles.py`; `tests/test_groundrecall_query.py` | Supported for current-applicability handling. | Time-qualified contradiction handling and broader temporal benchmark coverage remain future work. |
| Ordinary epistemic maintenance is non-destructive. | Implemented code; test coverage; design argument | Supersession, retraction, expiry, contradiction, and adjudication fields across `src/groundrecall/models.py`, `src/groundrecall/confidence.py`, and `src/groundrecall/contradictions.py` | `tests/test_confidence_profiles.py`; `tests/test_contradictions.py`; `tests/test_groundrecall_promotion.py` | Supported as design and partial implementation. | Exceptional erasure remains separate and incomplete. |
| Contradictions can be represented as explicit reviewable cases. | Implemented code; test coverage | `src/groundrecall/contradictions.py`; contradiction case models in `src/groundrecall/models.py`; CLI routes in `src/groundrecall/cli.py` | `tests/test_contradictions.py` | Supported for explicit contradiction links and deterministic case generation. | Automatic semantic contradiction detection is not implemented. |
| Contradiction adjudication records decisions without rewriting underlying claims. | Implemented code; test coverage | `src/groundrecall/contradictions.py`; adjudication records in `src/groundrecall/models.py` | `tests/test_contradictions.py` | Supported. | Adjudication does not yet automatically re-rank every downstream query result. |
| Release-level classification constrains export and federation. | Implemented code; test coverage | `src/groundrecall/federation.py`; `src/groundrecall/export_guardrails.py` | `tests/test_federation.py`; `tests/test_export_guardrails.py` | Supported for `public < internal < confidential < privileged < private` controls and private/local-only behavior. | Correctness depends on accurate metadata and review classification. |
| Export guardrails prevent lower-release bundles from carrying higher-release records or private support references. | Implemented code; test coverage | `src/groundrecall/export_guardrails.py`; federation filtering in `src/groundrecall/federation.py` | `tests/test_export_guardrails.py`; `tests/test_federation.py` | Supported. | This is not a substitute for end-to-end data-loss-prevention tooling. |
| Federation bundles are signed and content-hashed. | Implemented code; test coverage | `src/groundrecall/federation.py` | `tests/test_federation.py` signature, hash, tampering, HMAC, and Ed25519 tests | Supported. | Key management is local prototype-level; no key transparency or enterprise PKI integration. |
| Imported federation bundles are quarantine-first. | Implemented code; test coverage | `import_federation_bundle_to_quarantine` and promotion functions in `src/groundrecall/federation.py` | `tests/test_federation.py` quarantine and promotion tests | Supported. | No hosted review UI or network polling layer. |
| Promotion from quarantine is local-policy-gated and conflict-aware. | Implemented code; test coverage | `src/groundrecall/federation.py` local policy, scoped grants, conflict planning, audit events | `tests/test_federation.py` policy, scoped grants, conflict, promotion, and audit tests | Supported. | No enterprise IAM integration. |
| A valid signature does not by itself create local authority. | Implemented code; test coverage; design argument | Local policy evaluation, accepted release levels, trust registries, scoped grants, role directory import caps in `src/groundrecall/federation.py` | `tests/test_federation.py` policy, trust-registry, keyset, and role-directory tests | Supported. | This is a local-authority design property, not a comprehensive security proof. |
| Trust registries record active, expired, revoked, and superseded key state. | Implemented code; test coverage | Trust registry functions in `src/groundrecall/federation.py` | `tests/test_federation.py` trust registry lifecycle tests | Supported. | Does not include a distributed revocation propagation mechanism. |
| Signed public keysets and signed role directories can be imported only with receiver-side caps. | Implemented code; test coverage | Public keyset and role-directory publication/import functions in `src/groundrecall/federation.py` | `tests/test_federation.py` signed keyset and role-directory tests | Supported. | Requires pinned signer keys and local policy decisions. |
| Federation of contradiction cases respects release and claim exportability constraints. | Implemented code; test coverage | Contradiction-case filtering in `src/groundrecall/federation.py` | `tests/test_federation.py`; `tests/test_contradictions.py` | Supported. | Cross-host semantic reconciliation remains future work. |
| Audit events are recorded for federation policy decisions. | Implemented code; test coverage | `append_federation_audit_event` and `build_federation_audit_event` in `src/groundrecall/federation.py` | `tests/test_federation.py` audit tests | Supported. | Audit storage is local file-backed; no tamper-evident external audit log. |

### Claims That Are Explicitly Not Made

| Excluded claim | Status | Reason |
| --- | --- | --- |
| GroundRecall outperforms Mem0, HippoRAG, A-MEM, MemoryOS, or MemOS on memory benchmarks. | Not claimed. | No comparative benchmark has been run. |
| Governed memory has been shown to improve user productivity or reduce all AI-agent risk. | Not claimed. | Current evidence is engineering evidence, not user-study or broad safety evidence. |
| GroundRecall automatically detects semantic contradictions. | Future work. | Current contradiction workflow starts from explicit contradiction links. |
| GroundRecall provides production identity management or enterprise access control. | Future work. | Current controls are local policy, key, role, and release-level mechanisms. |
| GroundRecall provides complete exceptional-erasure propagation. | Future work. | Ordinary epistemic maintenance is non-destructive; exceptional erasure remains a separate incomplete mechanism. |
| GroundRecall is a complete distributed memory platform. | Future work. | No network transport, polling layer, CRDT merge, hosted review UI, or release-pack publication workflow is implemented. |
| ClaimWright is the only acceptable policy framework. | Not claimed. | The manuscript treats ClaimWright as one suitable operational stance under policy pluralism. |
| GroundRecall confidence measures are fully Bayesian or empirically calibrated. | Not claimed. | Current implementation supports structured confidence profiles and Epistemap-compatible exports; validated Bayesian updating remains outside current evidence. |

### Demonstration Register

The current manuscript can cite implementation, tests, and a stable demonstration runner. The runner lives at `examples/preprint/run_preprint_demos.py` and writes JSON summaries under `examples/preprint/out/`.

| Demonstration | Evidence class | Artifact | Claim supported |
| --- | --- | --- | --- |
| Provenance and promotion walkthrough | Reproducible demonstration | `examples/preprint/out/provenance_promotion.json` | Candidate observations and claims can be reviewed, promoted, and queried with provenance. |
| Contradiction adjudication walkthrough | Reproducible demonstration | `examples/preprint/out/contradiction_adjudication.json` | Contradictions become explicit cases and can be adjudicated without rewriting claims. |
| Release filtering walkthrough | Reproducible demonstration | `examples/preprint/out/release_filtering.json` | Public export excludes internal/private records and reports findings. |
| Federation quarantine walkthrough | Reproducible demonstration | `examples/preprint/out/federation_quarantine.json` | Signed import verifies origin/integrity but still lands in quarantine before local promotion. |
| Local authority walkthrough | Reproducible demonstration | `examples/preprint/out/local_authority.json` | A valid signed bundle is insufficient for promotion without receiver-side local policy. |
| CiteGeist bibliography expansion | Reproducible artifact | `docs/preprint/citegeist-memory-layer.sqlite3`; `docs/preprint/memory-layer-citegeist-export.bib` | Source review and BibTeX export remain inspectable. |

### Appendix Use in the Manuscript

The main paper can cite this appendix when making engineering claims. The safest formulation is:

> Appendix A maps each substantive manuscript claim to code, tests, source analysis, reproducible artifacts, or future-work status.

That statement is stronger and more auditable than saying only that the project follows a claim-to-evidence discipline.

\newpage

# Appendix B: ClaimWright Review Record

### Review Scope

Reviewed artifacts:

- `docs/preprint/preprint-draft.md`
- `docs/preprint/preprint-draft.html`
- `docs/preprint/claim-evidence-matrix.md`
- `docs/preprint/claim-evidence-matrix.html`

Applied ClaimWright materials:

- `MOU.md`
- `policies/principles.yaml`
- `policies/enforcement.yaml`
- `policies/claim_states.yaml`
- `checks/pre_action.yaml`
- `checks/post_action.yaml`
- `roles/claim-auditor.md`
- `roles/citation-reviewer.md`
- `roles/adversarial-reviewer.md`
- `roles/publication-gatekeeper.md`

### Pre-Action Check

| Check | Result |
| --- | --- |
| Action classification | Non-trivial review of public-facing draft artifacts. |
| Public/private status | Public-facing manuscript and appendix materials; local paths and private material require hard-gate screening. |
| Reversibility | Reversible through git. |
| Evidence standard | Implementation claims require code/test anchors; related-work claims require verified source or bibliography support; future-work claims require explicit limitation language. |
| Reputational risk | Moderate. Overclaiming implementation, comparative performance, or citation support would weaken the paper. |
| Adversarial review need | Required because the draft makes a design manifesto claim and uses local prototypes as evidence. |
| Model/tool suitability | Local repository inspection, grep, Pandoc rendering, and pytest are appropriate. |
| Capacity risk | Low. Full local test suite ran quickly. |
| Durable memory touch | Documentation and review artifacts only; no GroundRecall memory store changed. |
| Scientific virtues | Review emphasized veracity, skepticism, humility to evidence, provenance fairness, and public defensibility. |

### Claim Auditor Findings

| Claim area | State recommendation | Evidence | Required restraint |
| --- | --- | --- | --- |
| Governed memory as a necessary property set | `supported_but_contested` | Design argument, related-work comparison, and implemented governance features | Present as a normative/design thesis, not an empirical proof. |
| GroundRecall typed provenance-preserving record model | `supported_by_primary_evidence` | `src/groundrecall/models.py`, `src/groundrecall/store.py`, `tests/test_groundrecall_store.py` | Scope to current file-backed prototype. |
| Review-gated promotion | `supported_by_primary_evidence` | `src/groundrecall/promotion.py`, `tests/test_groundrecall_promotion.py` | Do not imply complete hosted review workflow. |
| Structured confidence and temporal applicability | `supported_by_primary_evidence` | `src/groundrecall/confidence.py`, `tests/test_confidence_profiles.py`, `tests/test_confidence_migration.py` | Do not claim full Bayesian calibration or empirical confidence validation. |
| Contradiction cases and adjudication | `supported_by_primary_evidence` | `src/groundrecall/contradictions.py`, `tests/test_contradictions.py` | State that semantic auto-detection is future work. |
| Release controls and federation quarantine | `supported_by_primary_evidence` | `src/groundrecall/federation.py`, `src/groundrecall/export_guardrails.py`, `tests/test_federation.py`, `tests/test_export_guardrails.py` | Do not present as enterprise IAM or complete DLP. |
| ClaimWright as policy framework | `supported_by_primary_evidence` for existence; `plausible_under_supported` for future integration | ClaimWright policy files and role/check documents | State that ClaimWright is an example and is not yet enforced inside GroundRecall. |
| CiteGeist bibliography support | `supported_by_primary_evidence` for seed artifacts | `docs/preprint/citegeist-memory-layer.sqlite3`, BibTeX export, bibliography notes | State that bibliography is seeded, not systematic or complete. |
| Epistemap confidence/graph layer | `supported_by_primary_evidence` for adapter surfaces | `src/groundrecall/epistemap_adapter.py`, `tests/test_epistemap_adapter.py` | Do not imply broad posterior validation. |

### Citation Reviewer Findings

| Citation set | Tier | Status | Notes |
| --- | --- | --- | --- |
| Generative Agents, MemGPT, HippoRAG, A-MEM, Mem0, MemoryOS, MemOS, AriGraph | A | Accepted | Directly supports the claim that recent systems foreground durable memory, retrieval, graph memory, production memory, and memory-OS abstractions. |
| KG/RAG alignment paper | B | Accepted | Supports the narrower point that graph representation and linearization affect downstream LLM use of graph knowledge. |
| ACM TOIS memory-mechanism survey | A | Accepted | Supports general framing that LLM-agent memory is an identifiable technical subsystem with sources, forms, operations, and evaluation concerns. |
| ClaimWright local policy substrate | A for example-policy claim | Accepted with access caveat | Supports the existence and contents of the example policy framework, not external validation of ClaimWright. |
| CiteGeist local bibliography artifacts | A for seed-bibliography claim | Accepted with completeness caveat | Supports that bibliography seeding exists; does not support systematic-review completeness. |
| Privacy, provenance governance, distributed systems, IAM, and security literature | B | Initial expansion accepted | Added NIST AI RMF, NIST SP 800-53, NIST SP 800-207, W3C PROV, SLSA, Sigstore, The Update Framework, and a distributed access-control survey. This supports adjacent-literature framing but remains short of a systematic review. |

### Adversarial Review Memo

The strongest objections are predictable and should remain visible:

1. The paper could sound as if it proves safety benefits. The current evidence does not do that. The draft now confines itself to engineering evidence and design argument.
2. The related-work section could be criticized as selective. The bibliography is explicitly seeded and should be expanded before submission.
3. The phrase "memory layers should be governed" is normative. That is acceptable in manifesto mode, but the claim should not be disguised as a benchmark result.
4. GroundRecall’s implementation is local-first and file-backed. Claims about federation, policy, and trust should remain scoped to prototype mechanisms.
5. ClaimWright is not yet an enforcement engine inside GroundRecall. The draft states this directly.
6. Confidence support is structured and exportable, but not yet a validated Bayesian confidence system. The appendix explicitly blocks that overclaim.
7. Contradiction handling depends on explicit contradiction links. Automatic semantic contradiction detection remains future work.
8. Public-facing artifacts must avoid absolute local paths. The appendix previously contained local paths; those were replaced with repository-level references.

### Publication Gate Result

| Gate | Result | Notes |
| --- | --- | --- |
| Unresolved high-risk public claims | Pass with caveats | High-risk claims are either scoped, caveated, or listed as not made/future work. |
| Fabricated or unverified citations | Pass for current cited set | Current references have DOI/source links. Broader bibliography remains an expansion task. |
| Private material in public output | Pass after correction | Absolute local paths were removed from the appendix. |
| Destructive irreversible action | Pass | Documentation-only changes; git revertable. |
| Contradicted or stale claims | Pass with caveats | No known contradicted/stale claims relied on for public argument; future literature expansion may create revision duties. |

Release status: conditionally suitable for internal/public draft review, pending human publication approval. The draft is closer to final-public-safe after initial bibliography expansion and reproducible demonstrations, but it is not final-public-safe because the bibliography is still not systematic and final human publication approval remains open.

### Review Results Applied

| Review result | Applied change |
| --- | --- |
| Avoid implying proof of safety benefits. | Abstract and prototype sections now say the systems demonstrate implementable local controls, not validated safety outcomes. |
| Avoid overbroad claims about the literature. | Related-work language now refers to "the sources reviewed for this draft" and "within this reviewed set" rather than all memory-layer literature. |
| Keep GroundRecall claims local/prototype-scoped. | Abstract, prototype, evaluation, and limitations language now emphasizes local prototype evidence and incomplete production features. |
| Keep ClaimWright integration scoped. | Existing wording that ClaimWright is not yet enforced inside GroundRecall was retained; the limitations section keeps it explicit. |
| Avoid Bayesian confidence overclaim. | Existing Epistemap/confidence caveats were retained; no Bayesian calibration claim was added. |
| Keep semantic contradiction detection as future work. | Existing contradiction caveats were retained in the abstract and limitations. |
| Expose final-public-safety status. | The evaluation section now states that the draft is suitable for internal/public draft review but not final-public-safe until bibliography scope and human publication approval are resolved. |
| Resolve public/private path issue. | Repository-level references remain in the appendix; no absolute local paths are used for public evidence references. |
| Broaden bibliography. | Added governance, provenance, access-control, zero-trust, and supply-chain-security entries to the seed BibTeX, CiteGeist database, exported BibTeX, bibliography notes, draft related-work text, and references. |
| Add empirical demonstrations. | Added `examples/preprint/run_preprint_demos.py`, `examples/preprint/README.md`, and generated JSON outputs for provenance/promotion, contradiction adjudication, release filtering, federation quarantine, and local authority. |

### Post-Action Check

| Check | Result |
| --- | --- |
| Files changed | Added this review record; updated the draft, bibliography, BibTeX exports, claim-evidence matrix, demonstration runner, generated demonstration outputs, and regenerated HTML outputs. |
| Claims introduced/modified | Test-suite claim changed from "latest implementation pass" to a dated concrete result: 171 tests passed on 2026-07-27. Appendix support references were changed from absolute local paths to repository-level descriptions. Demonstration claims are now backed by generated JSON outputs. |
| Citations recorded | Added governance/security/provenance citations: NIST AI RMF, NIST SP 800-53, NIST SP 800-207, W3C PROV Overview, W3C PROV-DM, SLSA provenance, Sigstore, The Update Framework, and Golightly et al. distributed access-control survey. |
| Assumptions visible | The review assumes the local ClaimWright repository represents the applicable review policy; it does not assert external validation of ClaimWright. |
| Unresolved risks | Bibliography is broader but not systematic; ClaimWright is not yet enforced inside GroundRecall; semantic contradiction detection remains future work; human publication approval remains open. |
| Tasks opened | Remaining gaps are now bibliography completeness/systematic-review scope, final publication approval, and future feature work, not absence of initial demonstrations. |
| Capacity used | Local inspection, web source verification, CiteGeist ingest/export, Pandoc rendering, demo execution, and pytest; no GPU use. |
| Branch outcome | Conservative/balanced branch chosen: keep manifesto framing but tighten evidence scope and gate overclaims. |
| Broader review trigger | Yes. Before submission, run a broader literature/security/governance review and add reproducible demonstrations. |
| Scientific virtues | The pass preserved veracity, skepticism, humility to evidence, public defensibility, and provenance fairness by weakening unsupported implications and making gaps explicit. |

\newpage

# Appendix C: Memory-Layer Bibliography Notes

## Memory-Layer Technology Seed Bibliography

Date: 2026-07-27

This is the CiteGeist-seeded bibliography for the GroundRecall preprint. It began with memory-layer technology for LLM agents: memory streams, virtual-context management, graph-structured long-term memory, production memory services, and memory-operating-system proposals. The 2026-07-27 expansion adds adjacent governance, provenance, access-control, zero-trust, and software-supply-chain sources.

The bibliography was started as a BibTeX seed file at `docs/preprint/memory-layer-seed.bib` and ingested into a dedicated CiteGeist database at `docs/preprint/citegeist-memory-layer.sqlite3`.

### How To Use This Bibliography In The Preprint

GroundRecall should position itself relative to this literature as a governance-oriented memory control plane:

- more provenance/governance-focused than memory-stream systems;
- more release-policy and federation-focused than most agent memory layers;
- compatible with graph/RAG memory trends, but stricter about review, access, contradiction handling, and local authority;
- not claiming automatic semantic contradiction detection or production IAM.

### Annotated Sources

| Key | Source | Why it matters for GroundRecall |
| --- | --- | --- |
| `park2023generativeagents` | Park et al., 2023, *Generative Agents* | Establishes memory streams, reflection, and retrieval as an agent architecture pattern. GroundRecall differs by centering durable provenance, review gates, release controls, and federation. |
| `packer2023memgpt` | Packer et al., 2023/2024, *MemGPT* | Frames LLM memory as an operating-system-style virtual context problem. GroundRecall extends the OS analogy toward governance, provenance, release policy, contradiction cases, and audit. |
| `gutierrez2024hipporag` | Gutiérrez et al., 2024, *HippoRAG* | Shows graph-based long-term retrieval can improve multi-hop memory use. GroundRecall’s graph operations and contradiction diagnostics fit this direction but add review and policy controls. |
| `xu2025amem` | Xu et al., 2025, *A-MEM* | Uses dynamically linked memory notes and memory evolution. GroundRecall should cite it as evidence that adaptive graph memory is a current research direction, while contrasting GroundRecall’s non-destructive adjudication/history model. |
| `chhikara2025mem0` | Chhikara et al., 2025, *Mem0* | Represents production-oriented long-term agent memory, including consolidation/retrieval and graph-memory variant. GroundRecall should contrast its governance controls with production memory performance claims. |
| `kang2025memoryos` | Kang et al., 2025, *Memory OS of AI Agent* | Hierarchical short/mid/long-term personal memory architecture. Useful for comparing memory tiers and update policies. |
| `li2025memos` | Li et al., 2025, *MemOS* | Memory OS abstraction treating memory as a manageable system resource across plaintext, activation, and parameter memories. Strong conceptual neighbor for GroundRecall’s memory control-plane framing. |
| `anokhin2025arigraph` | Anokhin et al., 2025, *AriGraph* | Uses semantic and episodic knowledge graph memory for agent planning. Useful for graph-memory comparison. |
| `zhang2025memorysurvey` | Zhang et al., 2025, *A Survey on the Memory Mechanism of LLM-based Agents* | Provides survey/taxonomy support for the claim that memory mechanisms are a defined LLM-agent subsystem. |
| `tian2025kgalignment` | Tian et al., 2025, *Knowledge Graph Alignment with LLMs in RAG* | Supports the point that KG representation/linearization choices matter for downstream LLM use. |
| `tabassi2023airmf` | NIST AI RMF 1.0 | Supports the governance/risk-management framing, especially govern/map/measure/manage and trustworthy-system characteristics. |
| `jointtaskforce2020sp80053r5` | NIST SP 800-53 Rev. 5 | Provides security and privacy control context for access control, audit/accountability, identification/authentication, privacy, and supply-chain risk management. |
| `rose2020zerotrust` | NIST SP 800-207, *Zero Trust Architecture* | Supports the local-authority/no-implicit-trust framing for federation and role/key distribution. |
| `groth2013provoverview` | W3C PROV Overview | Provides provenance terminology and interoperability framing for entities, activities, agents, and trustworthiness assessment. |
| `moreau2013provdm` | W3C PROV-DM | Supports the claim that provenance can be modeled as structured entities, activities, agents, derivations, and bundles. |
| `slsa2026provenance` | SLSA v1.2 Provenance | Provides a supply-chain provenance analogue: verifiable information about where, when, and how artifacts were produced. |
| `sigstore2026overview` | Sigstore overview | Supports comparison to signing, transparency logs, provenance, integrity, and explicit trust decisions. |
| `theupdateframework2026spec` | The Update Framework specification | Supports role/key/signature and key-compromise-resilience analogies for federation trust metadata. |
| `golightly2023accesscontrolsurvey` | Golightly et al., 2023, distributed access-control survey | Provides current distributed-systems access-control context for protected-resource access and organizational security. |

### Source Links Used For Verification

- Park et al., *Generative Agents*: https://research.google/pubs/generative-agents-interactive-simulacra-of-human-behavior/
- arXiv `2304.03442`: https://arxiv.org/abs/2304.03442
- arXiv `2310.08560`: https://arxiv.org/abs/2310.08560
- HippoRAG ML Anthology page: https://mlanthology.org/neurips/2024/gutierrez2024neurips-hipporag/
- arXiv `2502.12110`: https://arxiv.org/abs/2502.12110
- arXiv `2504.19413`: https://arxiv.org/abs/2504.19413
- arXiv `2506.06326`: https://arxiv.org/abs/2506.06326
- arXiv `2507.03724`: https://arxiv.org/abs/2507.03724
- IJCAI AriGraph page: https://www.ijcai.org/proceedings/2025/0002
- ACM TOIS memory survey DOI: https://doi.org/10.1145/3748302
- AAAI KG alignment paper: https://ojs.aaai.org/index.php/AAAI/article/view/34716
- NIST AI RMF 1.0: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10
- NIST SP 800-53 Rev. 5: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-207 Zero Trust Architecture: https://www.nist.gov/publications/zero-trust-architecture-0
- W3C PROV Overview: https://www.w3.org/TR/prov-overview/
- W3C PROV-DM: https://www.w3.org/TR/prov-dm/
- SLSA v1.2 provenance: https://slsa.dev/spec/v1.2/provenance
- Sigstore overview: https://www.sigstore.dev/docs/what_is_sigstore
- The Update Framework specification: https://theupdateframework.github.io/specification/
- Golightly et al. access-control survey: https://www.sciencedirect.com/science/article/pii/S2772918423000036

### Next Bibliography Expansion Targets

- LongMemEval and LoCoMo benchmark papers/datasets.
- GraphRAG and agentic GraphRAG surveys.
- Persistent AI memory privacy leakage and retrieval authorization.
- Capability-based access control, information-flow control, append-only audit logs, provenance-aware data governance, and distributed revocation.
- Formal publication venues and source access checks for the governance/security additions.
