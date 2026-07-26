# Memory-Layer Technology Seed Bibliography

Date: 2026-07-26

This is the initial CiteGeist-seeded bibliography for the GroundRecall preprint. It focuses on memory-layer technology for LLM agents: memory streams, virtual-context management, graph-structured long-term memory, production memory services, and memory-operating-system proposals.

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

## Next Bibliography Expansion Targets

- LongMemEval and LoCoMo benchmark papers/datasets.
- GraphRAG and agentic GraphRAG surveys.
- Security/governance papers on persistent AI memory, privacy leakage, and retrieval authorization.
- Systems literature on append-only logs, capability-based access control, and provenance-aware data governance.
