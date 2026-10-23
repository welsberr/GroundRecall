# GroundRecall Agentic Operating Model

Last reviewed: 2026-10-04
Owner: GroundRecall maintainers
Scope: cross-project software implementation

## Purpose

Coordinate implementation of session-safe, provenance-aware lede-brief
capabilities across GroundRecall, Epistemap, Didactopus, and CiteGeist.

## Source Of Truth

| Area | Authoritative Location | Notes |
|---|---|---|
| Roadmap and decisions | `docs/` and linked sibling roadmaps | Reviewed design and status only |
| Graph operations | sibling Epistemap checkout | Neutral graph authority |
| Persistent operational memory | GroundRecall workspace and canonical store | Never store secrets |
| Implementation run logs | `.agentos/runs/` | Private, append-only receipts |
| Public artifacts | Explicitly reviewed exports | No raw session logs |

## Agent Roles

| Role | Job | Allowed Actions | Must Not Do | Review Required |
|---|---|---|---|---|
| `lede-brief-implementer` | Implement the approved cross-project roadmap | Read sibling repositories, add scoped code/tests/docs, run local checks, write private receipts | Change production services, publish packages, alter canonical knowledge without a requested migration | Every milestone and cross-project contract |

## Verification

- [ ] Existing tests remain attributable and unrelated dirty changes are preserved.
- [ ] Graph structure, semantic coverage, provenance, and domain interpretation remain separate.
- [ ] Session and filesystem writes use declared operation paths.
- [ ] Generated artifacts retain source hashes, review state, and coverage status.
- [ ] Private paths, secrets, prompts, and runtime credentials are excluded from exports.

## Public / Private Boundary

Public candidates are reviewed documentation, schemas, and synthetic fixtures.
Private material includes AgentOS run logs, local paths, session telemetry,
unpublished source content, and credentials.

## Current State

The lede-brief design and cross-project roadmaps exist. Implementation is being
performed in dependency order: AgentOS control plane, Epistemap foundations,
portable transformation package, then consumer adapters and GroundRecall
session integration.
