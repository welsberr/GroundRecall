# GroundRecall Preprint Threat Model

Date: 2026-07-26

This threat model is scoped to the current GroundRecall prototype. It supports the preprint claim that GroundRecall is a governed memory control plane, not a finished distributed platform or complete IAM/security product.

| Threat | Implemented mitigation | Residual limitation |
| --- | --- | --- |
| Stale memory treated as current | Confidence and temporal-validity metadata; expiry, supersession, retraction, applicability, and confidence review markers. | No complete automated policy engine for every downstream context-use decision. |
| Ungrounded summary replaces evidence | Claims link back to observations/fragments and provenance records; exports preserve IDs and content hashes. | Upstream extraction can still be wrong; review remains necessary. |
| Contradictions remain invisible | Explicit `contradicts_claim_ids` can be materialized into contradiction cases; diagnostics flag missing cases and open promoted conflicts; adjudications can target cases. | No automatic semantic contradiction detection yet. |
| Conflicting imported record overwrites local canonical memory | Federation import quarantines first; promotion detects existing-record conflicts; promotion avoids overwriting differing canonical records. | No CRDT merge layer or rich conflict-resolution UI yet. |
| Private/internal material leaks through public export | Release lattice blocks broadening; `private` is local-only; hidden basis is marked partial; derivatives require redaction/declassification metadata. | Correct classification still depends on import/review discipline. |
| Privileged material is shared too broadly | Privileged federation requires explicit privileged allowance in policy. | Not a substitute for enterprise IAM, DLP, legal-hold, or HSM-backed controls. |
| Valid signature is mistaken for local authority | Import verifies signatures but still requires local release acceptance, policy, quarantine, and promotion. | Operators must maintain local policies and trust registries correctly. |
| Malicious or mistaken role directory grants too much authority | Signed role directories are locally capped before compilation into local policy. | No production identity integration or external revocation propagation service. |
| Stale, expired, or revoked trust key remains usable | Trust registry records expiry, revocation, active state, supersession, and trusted actions; resolver blocks expired/inactive/revoked keys. | No automated global key transparency or recovery service. |
| Audit history is lost during ordinary forgetting | Ordinary lifecycle changes are non-destructive; history remains via statuses, metadata, adjudications, and audit logs. | Exceptional erasure workflows are not yet implemented end-to-end. |
| Imported knowledge expands access scope indirectly | Federation filtering requires dependencies to be exportable; contradiction cases export only when referenced claims are included and case release level is allowed. | Transitive semantic leakage still requires conservative review/redaction practices. |
| Agent writes bypass review | Promotion gates candidate/imported material before canonical persistence; contradiction adjudication records explicit reviewer decisions. | GroundRecall does not by itself sandbox all host tools or prevent direct filesystem writes outside its store. |

## Paper Framing

The paper should state that GroundRecall addresses memory governance at the data-model and workflow layer:

- provenance is kept inspectable;
- promotion is review-gated;
- cross-host exchange is signed and quarantined;
- release-level policy prevents obvious access broadening;
- contradiction/adjudication state is preserved rather than erased;
- local policy remains final authority.

The paper should not claim complete security against host compromise, full regulatory compliance, complete erasure propagation, or production organization identity management.
