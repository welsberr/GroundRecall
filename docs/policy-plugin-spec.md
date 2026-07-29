# GroundRecall Policy Plugin Specification

Status: authoritative GroundRecall contract

GroundRecall owns the policy plugin interface for governed memory operations.
Policy frameworks such as ClaimWright may implement this contract, but they do
not define the GroundRecall enforcement format.

## Purpose

Policy plugins let GroundRecall evaluate externally supplied policy content
without hardwiring one policy framework into the memory substrate.

GroundRecall enforcement surfaces call plugins at bounded decision points and
consume bounded decision values. Plugins may contain arbitrary policy content,
but their GroundRecall-facing output must conform to this specification.

## Decision Points

Plugins answer requests for these GroundRecall decision points:

- `read`
- `query`
- `propose`
- `review`
- `promote`
- `revise`
- `supersede`
- `adjudicate`
- `export`
- `publish`
- `federate_import`
- `federate_export`
- `redact`
- `delete`
- `cite_publicly`
- `act`

## Decision Values

Plugins return exactly one of:

- `allow`: operation may proceed.
- `require_review`: operation may proceed only as review-visible work, or the
  result must carry review obligations.
- `soft_gate`: operation may proceed with explicit warning, override, or review
  context.
- `hard_gate`: operation must not proceed until the required condition is
  satisfied or separately authorized.
- `deny`: operation is disallowed by policy.

GroundRecall treats `deny` and `hard_gate` as blocking decisions at enforcement
surfaces that support blocking. Softer decisions are attached to the operation
result and audit trail as review context.

## Policy Request Shape

GroundRecall sends a `PolicyRequest` with these fields:

| Field | Meaning |
| --- | --- |
| `decision_point` | One of the bounded decision points above. |
| `subject_id` | Principal, agent, user, role, or service requesting the action. |
| `action` | Operation-specific action name. |
| `record_kind` | Optional memory object kind. |
| `record_id` | Optional memory object identifier. |
| `release_level` | Current release level when known. |
| `target_release_level` | Intended release level for export/publication/federation. |
| `scope_id` | Project, host, organization, or entity scope. |
| `claim_state` | Optional external or local claim lifecycle state. |
| `evidence_state` | Optional evidence/review state. |
| `citation_state` | Optional citation state. |
| `contradiction_state` | Optional contradiction/adjudication state. |
| `stale` | Whether stale/supersession review is known to be relevant. |
| `destructive` | Whether the operation is destructive or hard to reverse. |
| `public_facing` | Whether the operation creates or affects public-facing output. |
| `durable_memory_change` | Whether the operation affects durable memory state. |
| `metadata` | Namespaced extension data. |

Plugins must ignore unknown metadata they do not understand. They must not
reinterpret unknown producer-specific fields as authority.

Restriction-aware federation should pass the following `metadata` keys when
known:

| Metadata key | Meaning |
| --- | --- |
| `restriction_markers` | Purpose, compartment, legal, HR, incident, source-protection, export-control, or originator-control markers that survive release-level checks. |
| `compartment_ids` | Explicit compartment/scope identifiers separate from release level. |
| `purpose` | Intended federation, publication, import, promotion, or query purpose. |
| `producer_instance_id` | Originating GroundRecall instance. |
| `receiver_instance_id` | Receiving GroundRecall instance when known. |
| `derivative_policy_id` | Redaction, declassification, or restriction policy authorizing a derivative. |

`restricted` is not a release level and must not be silently normalized to
`confidential`. It is a restriction marker that should fail closed unless the
policy plugin explicitly allows the marker, purpose, scope, producer, receiver,
and target release context.

## Policy Decision Shape

Plugins return a `PolicyDecision` with these fields:

| Field | Meaning |
| --- | --- |
| `decision` | One bounded decision value. |
| `policy_id` | Stable policy or composed-policy identifier. |
| `policy_version` | Policy version string. |
| `provider_id` | Plugin/provider identifier. |
| `decision_point` | Decision point evaluated. |
| `subject_id` | Subject evaluated. |
| `action` | Action evaluated. |
| `reasons` | Machine-readable reason codes. |
| `obligations` | Required follow-up actions or conditions. |
| `required_reviewers` | Roles or reviewer classes needed. |
| `allowed_release_level` | Most restrictive release level permitted by the decision. |
| `redactions` | Required redaction labels or transforms. |
| `confidence_effects` | Confidence/applicability effects to record or review. |
| `audit_tags` | Tags to carry into audit records. |
| `metadata` | Namespaced extension data. |

Reason codes, obligations, reviewer IDs, redaction labels, and confidence
effects are policy-specific, but they must remain inspectable strings or
structured JSON values. They must not be hidden in prose-only explanations.

## Composition Rule

GroundRecall composes plugin decisions conservatively:

1. `deny` dominates all other decisions.
2. `hard_gate` dominates `soft_gate`, `require_review`, and `allow`.
3. `soft_gate` dominates `require_review` and `allow`.
4. `require_review` dominates `allow`.
5. Obligations accumulate.
6. Required reviewers accumulate.
7. Redactions accumulate.
8. The most restrictive release level wins.
9. Confidence effects accumulate for later review.
10. Policy IDs, provider IDs, and audit tags remain visible in metadata.

Policy conflict is not silently resolved. Where a composed decision leaves
ambiguous obligations, the receiving workflow should treat that as review state.

## Current Built-In Provider Types

GroundRecall currently supports these plugin provider config types:

- `static`
- `groundrecall.static`
- `claimwright`
- `claimwright.directory`

The ClaimWright provider is an adapter over ClaimWright-style policy directory
content. When present, `policies/collaboration.yaml` contributes structured
institutional rules for contribution, review, promotion, custody, and rationale
preservation. It is not the policy contract authority.

## Plugin Config File

Plugin configuration is YAML:

```yaml
schema_version: groundrecall.policy_plugins.v1
policy_id: example.composed_policy
providers:
  - type: groundrecall.static
    policy_id: example.default_review
    default_decision: require_review
  - type: claimwright.directory
    root_dir: /path/to/ClaimWright
```

`schema_version` is recommended and should be
`groundrecall.policy_plugins.v1`. The initial loader accepts omitted
`schema_version` for compatibility but rejects unknown explicit versions.

## Enforcement Surfaces Currently Integrated

The policy plugin boundary is currently used by:

- MCP policy evaluation;
- MCP read/query/search/export tools;
- canonical import promotion into the local store;
- relation-review batch application;
- contradiction-case adjudication;
- federation export, quarantine import, and promotion;
- canonical public export.

Additional GroundRecall write, proposal, review, revision, supersession,
redaction, and delete surfaces should route through this same contract as they
mature.
