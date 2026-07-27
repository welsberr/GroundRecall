# Memory-Layer Technology Seed Bibliography

Date: 2026-07-27

This is the CiteGeist-seeded bibliography for the GroundRecall preprint. It began with memory-layer technology for LLM agents: memory streams, virtual-context management, graph-structured long-term memory, production memory services, and memory-operating-system proposals. The 2026-07-27 expansion adds adjacent governance, provenance, access-control, zero-trust, and software-supply-chain sources.

The bibliography was started as a BibTeX seed file at `docs/preprint/memory-layer-seed.bib` and ingested into a dedicated CiteGeist database at `docs/preprint/citegeist-memory-layer.sqlite3`.

## How To Use This Bibliography In The Preprint

GroundRecall should position itself relative to this literature as a governance-oriented memory control plane:

- more provenance/governance-focused than memory-stream systems;
- more release-policy and federation-focused than most agent memory layers;
- compatible with graph/RAG memory trends, but stricter about review, access, contradiction handling, and local authority;
- not claiming automatic semantic contradiction detection or production IAM.

## Annotated Sources

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

## Source Links Used For Verification

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

## Next Bibliography Expansion Targets

- LongMemEval and LoCoMo benchmark papers/datasets.
- GraphRAG and agentic GraphRAG surveys.
- Persistent AI memory privacy leakage and retrieval authorization.
- Capability-based access control, information-flow control, append-only audit logs, provenance-aware data governance, and distributed revocation.
- Formal publication venues and source access checks for the governance/security additions.
