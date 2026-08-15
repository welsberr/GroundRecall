# ChatGPT MCP Integration Roadmap

Date: 2026-08-09
Status: implementation track; remote adapter pilot is advancing toward an Edu read-only pilot
Primary repository: `/home/netuser/bin/GroundRecall`

## Purpose

Make a GroundRecall instance on a private LAN usable from ChatGPT web sessions
as a governed knowledge service. This is an assistant-access surface, not a
replacement for GroundRecall federation or for ChatGPT's native memory.

ChatGPT web does not connect directly to an arbitrary LAN stdio process. The
integration therefore needs a remote MCP adapter and a private-network access
path such as Secure MCP Tunnel. Consult the current
[official OpenAI MCP guidance](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt)
before deployment because availability, plan support, permissions, and MCP
behavior may change.

## Design principles

1. **Read-only first.** Initial ChatGPT access is limited to search, prior-work,
   catalog, orientation, impact, stewardship, and review-backlog reads.
2. **Availability is not authority.** ChatGPT may retrieve a remote assertion;
   it must not make that assertion canonical merely by seeing it.
3. **Server-side policy is mandatory.** Caller-supplied policy arguments are
   useful for local development but are not sufficient for a remote service.
4. **Identity selects a realm.** The authenticated user maps to a principal,
   project, or team realm; the adapter never exposes the whole host store.
5. **Provenance and freshness remain visible.** Results retain origin, review
   state, release level, scope, and stale/offline indicators.
6. **Writes are separate products.** Contribution proposals, acknowledgements,
   promotion, adjudication, and federation actions need distinct tools,
   approvals, audit records, and policy decisions.
7. **The local service remains useful alone.** Tunnel or ChatGPT outages must
   not interrupt local GroundRecall, assistant, or review workflows.
8. **Assistants share state, not sessions.** ChatGPT and Codex exchange compact,
   governed task records and references; neither chat history nor a terminal
   session becomes canonical memory.
9. **Execution remains explicit.** A ChatGPT handoff may propose work for
   Codex, but it does not grant ChatGPT arbitrary shell, repository, or host
   authority.

## Target architecture

```text
ChatGPT web custom MCP app
        │ authenticated remote MCP transport
Secure MCP Tunnel / approved private-network path
        │
GroundRecall MCP HTTP adapter
  ├─ authentication and principal/project mapping
  ├─ mandatory server policy and release filtering
  ├─ bounded query/read tools
  ├─ task/plan/progress/result handoff records
  ├─ audit and correlation IDs
  └─ GroundRecall local query/review APIs
        │
local canonical store, federation cache, quarantine, and review ledger
```

The existing `groundrecall-mcp` stdio server remains useful for local MCP
clients. It is not itself the remote ChatGPT endpoint.

## Work packages

### CG-00: Contract and product boundary

Status: contract documented; remote transport implementation is still a pilot.

- Define the remote tool inventory and mark each tool `read`, `proposal`, or
  `write`.
- Add a server identity and adapter schema version.
- Define error responses that do not disclose inaccessible scope existence.
- Define provenance, freshness, offline, and incomplete-basis fields for every
  remote result.
- Document that ChatGPT tool use is explicit/relevance-driven, not invisible
  replacement of native ChatGPT memory.

Exit: a client can distinguish local, federated, quarantined, stale, and
accepted information without inspecting private paths or raw logs.

### CG-01: Remote MCP transport adapter

Status: bounded JSON-RPC-over-HTTP pilot implemented in
`src/groundrecall/mcp_http.py` and exposed as `groundrecall-mcp-http`. The
adapter now serves stable MCP `initialize` and `ping` responses, with a
read-only tools capability advertisement. Request and response bodies are
bounded; an oversized response is replaced with a fixed error body so result
content cannot leak through an error path. It is not yet validated against
ChatGPT or a streamable-HTTP compatibility suite.

- Add a supported HTTP MCP transport around the existing handlers, preserving
  JSON schemas and stable tool names.
- Keep stdio and HTTP adapters on the same core implementation.
- Bound request size, response size, result count, execution time, and tool
  concurrency.
- Add health/readiness endpoints outside the MCP tool namespace without
  exposing store contents.

Exit: an authenticated remote MCP client can initialize, list tools, and call a
read-only GroundRecall tool over the selected transport.

### CG-02: Authentication, realm mapping, and mandatory policy

Status: pilot adapter requires an existing server-owned policy file, supports
either a fixed bearer token or a server-owned JSON identity file, advertises
`readOnlyHint` for its default tool set, and maps each configured identity to
an explicit subject, realm, release cap, and tool allow-list. Full
OAuth/tunnel identity mapping and dynamic project/team realm resolution remain
future work. Each HTTP response now carries a server-generated correlation ID,
and tool-call policy metadata includes that ID plus the server-selected realm.
When `--audit-log-path` is configured, the adapter appends privacy-conscious
JSONL access events with correlation ID, principal/realm, method/tool, decision,
result class, HTTP outcome, and bounded denial reason; request arguments and
bearer tokens are never recorded. Audit remains opt-in and local-file backed.
An operator logrotate template now provides bounded daily rotation (14 archives,
50 MiB size trigger, compression). Active-file records now carry a SHA-256
previous-record link and record hash, with a verifier helper; rename-based
rotation deliberately starts a new independently verifiable chain in each file.
Centralized export and deployment-specific retention approval remain future work.

The logrotate template now includes an operator-controlled `postrotate` hook
that invokes `groundrecall-mcp-audit-manifest` using a documented, editable
binary-path placeholder. Manifest output is atomically replaced and command
output is suppressed; missing or failed commands produce only a bounded host
warning so log rotation itself remains safe.

The `groundrecall-mcp-audit-verify` operator command verifies an active JSONL
chain and returns a nonzero status for malformed or tampered records while
printing only bounded summary data by default.

The identity-file pilot keeps authorization server-owned: callers cannot select
another subject, realm, release level, or tool outside the intersection of the
server and identity allow-lists. It is intentionally a local/private-network
credential mechanism, not a replacement for tunnel-issued identity or OAuth.

- Add an authentication adapter suitable for the chosen tunnel/service path.
- Map authenticated identity to principal, project, and team realms.
- Load policy from server-owned configuration; reject requests when policy is
  missing, stale, or unable to classify the requested scope.
- Apply release, restriction, provenance-visibility, and purpose checks before
  retrieval and again before rendering.
- Audit identity, realm, tool, decision, result class, correlation ID, and
  denial reason without storing unnecessary prompt content.

Exit: a ChatGPT user cannot select a broader realm or override policy by
passing request metadata.

### CG-03: Private-network deployment

Status: a non-installed systemd deployment template is available at
`deploy/systemd/groundrecall-mcp-http.service`, with a least-privilege service
account, loopback binding, bounded restart behavior, and explicit writable
paths. Setup and credential handling are documented in
`docs/mcp-http-systemd.md`. Tunnel enrollment, rotation/revocation, and a
production health supervisor remain operator/integration work. The accompanying
logrotate template can generate a metadata-only audit manifest after rotation;
operators must set the local command path and review retention/permissions.

The adapter now provides bounded `/healthz` and `/readyz` endpoints. Liveness
does not inspect data; readiness checks only the server-owned policy file and
configured store availability, returning boolean checks without paths or store
contents. The systemd template supplies `--store-dir` for this probe.
It also enables `--require-policy`, so policy removal or invalidation fails
closed for MCP requests and readiness. Local development retains the
backward-compatible opt-out.
The adapter also applies a configurable bounded concurrency semaphore; overload
returns a fixed `server busy` response and does not queue unlimited work.
An optional execution wait returns a fixed timeout response while allowing the
underlying worker to finish under the same semaphore; unsafe thread killing is
not attempted.
An operator export utility now provides a bounded, verified redacted audit
projection for handoff/retention workflows without deleting source logs.

- Package the adapter and tunnel as a least-privilege service.
- Bind the GroundRecall adapter to loopback or a dedicated LAN interface;
  never expose the canonical store directly.
- Add systemd ordering, restart limits, health checks, log rotation, and
  explicit secret/key file permissions.
- Document tunnel enrollment, rotation, revocation, and emergency shutdown.
- Test operation with the tunnel unavailable; local GroundRecall must continue.

Exit: the service is reachable from approved ChatGPT web sessions without a
publicly exposed GroundRecall port.

### CG-04: ChatGPT read-only pilot and assistant handoff

- Create a private custom MCP app in ChatGPT developer mode where the account
  and workspace plan support it.
- Publish only read/search/fetch-style tools initially.
- Define versioned `AssistantHandoff`, task, plan, progress, and result records
  linked by stable task and handoff IDs.
- Expose proposal/query methods such as `handoff_propose`, `handoff_get`,
  `handoff_list`, `handoff_update_status`, `progress_append`, and
  `result_propose`; keep canonical promotion separate and policy-gated.
- The local MCP implementation now provides these lifecycle methods plus
  `handoff_events`: status transitions are constrained and idempotent, and
  progress/result records are append-only operational proposals. The bounded
  HTTP adapter exposes event reads by default; lifecycle writes require an
  explicit allow-list.
- Handoff status and lease persistence uses an atomic per-record journal with
  fsync and bounded read-time recovery; interrupted writes are completed
  idempotently before returning a scoped handoff.
- Store context references, constraints, acceptance criteria, provenance,
  expiry, and idempotency keys rather than copied transcripts or prompt-sized
  context.
- Provide an explicit Codex-side discovery path scoped to host, repository,
  project, and subject. Do not assume every Codex session automatically
  claims or executes a handoff.
- `groundrecall-handoff-discover` now provides that path as a bounded,
  policy-filtered read-only command, with project/host/subject/realm/status and
  release-level filters. It never auto-claims or executes a handoff.
- Add explicit `handoff_claim` and `handoff_release` calls for Codex-side
  acceptance. Claims require matching subject, target host, project, realm,
  expected status, idempotency key, and a 1--3600 second lease. Expired leases
  can be reclaimed or released only within the original scope; claim/release
  never executes host work and remain opt-in HTTP writes.
- Test prompts for prior-work lookup, reviewed claim retrieval, freshness,
  contradiction visibility, and scope denial.
- Verify that inaccessible topics, counts, assignees, and error paths do not
  leak protected project existence.
- Record the app tool snapshot and review changes before republishing updates.

Exit: an Edu/Enterprise browser session can retrieve useful,
provenance-bearing GroundRecall context and create a governed, proposal-only
handoff that a scoped Codex session can accept and complete.

### CG-05: Governed proposals and review actions

- Add explicit proposal tools for contribution, review acknowledgement,
  deferral, assignment, and import request.
- Keep proposal writes in the operational ledger or quarantine; never write
  canonical memory directly from a ChatGPT tool call.
- Require confirmation for consequential actions and preserve the ChatGPT
  correlation ID in GroundRecall audit records.
- Add appeal, rejection, dissent, and correction paths.

Exit: ChatGPT can help route work without becoming an unreviewed promotion or
publication authority.

### CG-06: Evaluation and operational hardening

- Measure retrieval usefulness, stale-result rate, denial correctness, result
  leakage, latency, and review burden.
- Test prompt injection in stored records and malicious tool arguments.
- Test tunnel outage, policy reload, identity revocation, key rotation, and
  ChatGPT app tool-schema drift.
- Add deployment-specific retention/deletion approval, tamper evidence, and
  centralized export for remote request/audit data.
- Document supported ChatGPT plans and workspace administrator controls as
  deployment prerequisites, not product guarantees.

Exit: the integration has reproducible security and usefulness evidence and
clear unsupported-boundary statements.

## Recommended execution order

```text
CG-00 contract
  ↓
CG-01 HTTP adapter ──→ CG-02 identity/policy
                           ↓
CG-03 tunnel/service
                           ↓
                 CG-04 read-only + handoff pilot
                           ↓
                      CG-05 governed proposals
                           ↓
                      CG-06 evaluation/hardening
```

CG-01 should not be deployed to ChatGPT before CG-02. A remote MCP endpoint
without server-owned policy would turn the LAN host into a broad retrieval
surface.

## Non-goals

- Treating ChatGPT as the canonical memory store.
- Sending raw assistant transcripts or the complete GroundRecall store to
  ChatGPT by default.
- Making all browser sessions share one unrestricted principal identity.
- Assuming ChatGPT app availability, plan support, or permissions are stable.
- Replacing organization IAM, DLP, legal hold, or incident-compartment
  controls.
