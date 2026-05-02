# GenieHive Foundation Gateway Notes

Last updated: 2026-05-01

This document records how GroundRecall should relate to the optional GenieHive
Foundation gateway profile.

## Boundary

GroundRecall remains the grounded knowledge substrate. It owns:

- source import and provenance
- normalized knowledge objects
- review candidates and promotion records
- canonical query and export
- assistant-neutral bundles

GenieHive remains the model and routing control plane. The Foundation gateway
profile adds governance around model access:

- named, revocable client credentials
- request audit logging without prompt or completion content
- model and operation allowlists
- future provider credential indirection
- future provider adapters, quotas, and operator tooling

GroundRecall should not duplicate GenieHive's credential, audit, routing, or
budgeting state.

## Integration Pattern

GroundRecall-powered workflows that need model assistance should treat
GenieHive as an external OpenAI-compatible endpoint:

```text
GroundRecall source/query/export -> client workflow -> GenieHive role/model
```

The client workflow should carry only:

- `GENIEHIVE_BASE_URL`
- `GENIEHIVE_API_KEY`
- requested role or model, preferably a role such as `archive_migrator`

Provider root keys must not be stored in GroundRecall source notes, promoted
objects, exports, assistant bundles, or repo docs.

## What To Record In GroundRecall

Allowed operational facts:

- which GenieHive deployment profile is in use, such as `casual` or
  `foundation_gateway`
- non-secret endpoint locations, such as a localhost or ZeroTier base URL
- role names used by workflows
- commit IDs for GenieHive capability changes
- whether request audit logging and allowlist enforcement are enabled
- test or smoke-test outcomes

Not allowed:

- raw GenieHive API keys
- provider API keys
- provider dashboard credentials
- prompt or completion content copied from audit logs
- secrets embedded in `.env` files

## Current GenieHive Milestones Reflected Here

As of this note, the local GenieHive roadmap has completed:

- baseline and compatibility guard
- config profiles and feature flags
- named client key storage, opt-in named auth, and admin key endpoints
- opt-in request audit logging
- named-key model and operation authorization

Remaining GenieHive work that may matter to GroundRecall-assisted workflows:

- archive migration role/profile config
- provider credential indirection
- Anthropic Messages adapter
- budget and quota enforcement
- admin CLI and operations documentation
- security review

## GroundRecall Implications

No GroundRecall schema change is needed for these GenieHive milestones.

GroundRecall may eventually benefit from optional metadata fields or source-note
conventions for:

- `model_gateway`
- `model_role`
- `request_id`
- `workflow_run_id`

Those should remain provenance metadata for generated or assisted artifacts, not
a copy of GenieHive's audit table.
