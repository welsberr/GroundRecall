# GroundRecall AgentOS Entry Point

Last reviewed: 2026-07-03

This repository follows the host-level AgentOS configuration at
`/home/netuser/.agentos`.

Overlay: `groundrecall`

Default roles:

- `grounded-research-assistant`
- `security-operator`
- `agentos-steward`

Required checks:

- `memory-export-guardrails`
- `operations-security`
- `stale-context-audit`

Private by default:

- Privileged operational notes.
- Draft or unreviewed records.
- Raw assistant logs.
- Private source pointers.

Public release rule:

- Memory-derived exports must pass guardrail tests and expose only reviewed
  public-safe records.
- Do not store or publish secret values in GroundRecall or AgentOS files.

Before changing export behavior or publishing memory-derived artifacts, run:

```sh
cd /home/netuser/bin/GroundRecall
PYTHONPATH=src:/home/netuser/bin/Epistemap/src pytest -q \
  tests/test_export_guardrails.py \
  tests/test_groundrecall_export.py \
  tests/test_groundrecall_assistants.py
```
