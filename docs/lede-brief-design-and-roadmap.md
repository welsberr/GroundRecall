# Lede-brief: concise presentation with explicit conceptual coverage

Status: proposed design and implementation extension, 2026-10-04. No features
described here are implemented by this document. Companion to the
[Session Context and Cost Roadmap](session-context-and-cost-roadmap.md).

Implementation status: the first local distributable package exists at the
sibling `LedeBrief` checkout as `lede-brief==0.1.0a2`; Epistemap coverage
foundations are released locally as `0.1.0a6`. Consumer metadata now declares
bounded package-index dependencies. External package publication remains an
operator release step because this checkout has no configured LedeBrief remote
or package-index destination.

Lede-brief should lead with the central point and provide an explicit choice
about how much meaning to retain. It supports a selective brief, a concise
document covering the source's full conceptual inventory, or a navigable set
of documents that collectively covers that inventory. Every mode makes its
scope, omissions, and verification status visible.

## Cross-project ownership and dependency direction

Architecture revision: lede-brief is a shared capability, with GroundRecall as
its first operational consumer. This document remains the coordinating design
until the shared library has its own documentation home. Its current location
does not assign the whole implementation to GroundRecall.

| Owner | Responsibility | Boundary |
| --- | --- | --- |
| Epistemap | Neutral coverage schemas/mappings, typed dependency traversal, structural validation, coverage differences and change-impact traversal | Does not generate prose, judge semantic equivalence, choose domain requirements, or authorize publication. |
| Shared lede-brief library | Inventory extraction, concise drafting, partitioning, semantic-review orchestration, repair and portable Markdown/JSON packages | Depends on Epistemap and injected generation/review interfaces; no mandatory GroundRecall, assistant runtime, bibliography database or learner store dependency. |
| GroundRecall | Artifact persistence/provenance, review/access policy, operational checkpoints, session loading, cost advice and runtime integration | Consumes shared packages; does not redefine neutral graph semantics. |
| Didactopus | Educational preservation profiles, learner-appropriate explanations, prerequisite selection, practice and assessment | Concept coverage is not demonstrated mastery or sufficient instruction. |
| CiteGeist | Bibliographic identity, source/version provenance, literature profiles, citation and bibliography review | Citation edges and relatedness are not evidential support. |

Companion plans specify [Epistemap foundations](../../Epistemap/docs/lede-brief-foundations-roadmap.md),
[Didactopus integration](../../Didactopus/docs/lede-brief-integration-roadmap.md),
and [CiteGeist integration](../../CiteGeist/docs/lede-brief-integration-roadmap.md).
These cross-repository links assume sibling local checkouts; published packages
must supply documentation links pinned to their compatible releases.

The dependency direction is Epistemap → shared lede-brief → consumer adapters.
Epistemap must not import the shared library or any consumer. Begin with a small
installable library and optional model backends, not a required service. LB-0
must select its repository/package location and distribution name, ownership,
schema-version policy and compatibility matrix before implementation. No new
repository, package publication, or release is performed by this roadmap change.

Epistemap owns portable unit/relation identifiers, inventory references, output
span mappings and structural coverage results. The shared library owns prose
formats and semantic-review workflow. Consumers provide required-unit sets,
edge-type traversal policy, permissions and domain review decisions. Keep graph
structure, extraction fidelity, semantic fidelity, evidential support, coverage,
retrieval relevance and learner mastery as distinct assessments.

## Graph operations that support lede-brief

Use typed graph projections to attach assertions to definitions, evidence,
conditions, exceptions, attribution and output spans. Topic nodes alone cannot
represent conceptual coverage. Preserve complex qualifications as explicit units
or structured relations; shared metadata must not erase their scope.

Compute dependency closure using only caller-selected relation types and
directions. Partition related units together and retain cross-document
dependencies. Cycles need explicit handling: mutual explanation may be valid,
while a strict prerequisite cycle requires domain review. Reuse the graph
correctness work rather than duplicating cycle/traversal implementations.

Coverage differences expose missing required units and relationships. Reverse
dependency traversal identifies documents affected by a corrected source. These
are structural operations: a `represents` edge records a mapping assertion and
its review evidence, not proof that the output preserves meaning. Source-to-
inventory recall and semantic fidelity still require independent evaluation.

Budgeted selection can prioritize useful units subject to required dependency
closure. Centrality may inform optional selection; it cannot remove mandatory
exceptions or establish truth. A preservation conflict must be reported when
the required closure exceeds budget. No graph database service is required for
these portable bundle operations.

## Inspiration and naming

Axios HQ describes Smart Brevity as a communication approach that foregrounds
news and relevance and uses readable presentation. See its [official
description](https://axioshq.com/smart-brevity), consulted 2026-10-04. That is a
useful editorial starting point, but the distinguishing requirement proposed
here is an auditable account of conceptual coverage.

“Always lossy” needs a qualification: removing redundancy can shorten text
without losing concepts. Changing wording normally loses the exact expression,
but it need not lose the assertions. Conversely, a concise presentation style
alone does not establish that every assertion survived. Lede-brief should state
which kind of preservation it attempts and how that claim was checked.

Use `lede-brief` as a working name with independently written terminology,
documentation, and presentation. This is not a trademark clearance conclusion.
A different name alone does not establish freedom from infringement; the USPTO
recommends checking similar marks and common-law uses for related goods/services.
See its [clearance-search guidance](https://www.uspto.gov/trademarks/search/comprehensive-clearance-search-similar-trademarks).
No comprehensive name clearance was performed for this design.

## Three delivery modes

| Mode | Output contract | What may be omitted |
| --- | --- | --- |
| `selective` | A short, useful account for a named audience/task, with an omission report | Lower-priority concepts; indispensable qualifications must remain with any retained claims. |
| `complete-single` | One document expressing every required meaning unit and relationship in the declared inventory | Repetition and wording; examples only when they add no distinct meaning under the declared preservation profile. |
| `complete-set` | An overview and a finite, versioned collection whose combined contents express every required unit and relationship | Individual documents may cover subsets. The overview is labeled selective; the collection carries the completeness claim. |

Scope and packaging are independent. `source-complete` requires an inventory of
the entire declared source input. `task-complete` covers an explicitly selected
subset and must not be labeled source-complete. Declare the audience and assumed
background separately so implicit prerequisites do not disappear unnoticed.

“Complete” means complete relative to a versioned, reviewed conceptual inventory
and preservation profile. It is not a guarantee of exact textual reconstruction,
every possible interpretation, or the source's factual correctness. Keep the
original source for exact quotations, reinspection, and later reinterpretation.
Merely retaining or linking the original does not make the transformed documents
conceptually complete.

Shorter output is an objective subject to preservation constraints. Dense
sources may not admit meaningful shortening; a document set may be longer in
total because it includes navigation and necessary overlap. If a length limit
cannot be met without losing required content, return a budget conflict and
offer a larger limit, a collection, or an explicitly selective scope. Never
silently weaken a completeness requirement.

## What the coverage inventory must represent

A topic label such as “safety” or “cost” is not a sufficient unit. Capture
assertions and the conditions that give them their meaning. Suggested fields:

```text
unit_id; source_version; source_spans; kind; normalized_statement;
entities; quantities_and_units; polarity; modality; attribution;
time_and_scope; qualifications; dependencies; verification_status
```

Represent definitions, distinctions, claims, hypotheses, recommendations,
procedural steps and ordering, evidence and methods, exceptions, negative
findings, disagreements, and open questions. Preserve numbers and denominators,
uncertainty, “may” versus “must,” correlation versus causation, and who asserted
what. A factual claim and a report that someone made that claim are different.

Capture relationships as well as units: evidence supports a claim; an exception
limits a rule; a condition precedes an action; two sources disagree. Merging
repetition requires checking that scope, confidence, attribution, and time are
equivalent. Preserve all supporting source references after merging.

Source processing includes footnotes, tables, captions, equations, and figures
when present. Unreadable or unprocessed material is an explicit coverage gap.
Every meaningful source span must map to a unit or a reviewed explanation such
as “repetition of U17”; unexplained spans block source-complete status.

Use preservation profiles for different inputs. A technical profile preserves
methods, quantities, prerequisites and limitations. A rhetorical/literary profile
may also require tone, framing, examples and argumentative structure. Code,
datasets, legal language, or mathematical proofs may need exact referenced
artifacts as well as an explanation; conceptual coverage does not substitute
for executable equivalence, a proof, or exact wording.

## Transformation and verification

1. Freeze the source version and inventory all input sections and media. Record
   hashes, provenance, access restrictions, and parsing gaps.
2. Extract meaning units and relationships. Run a separate source-to-inventory
   review to look for missing units, rather than letting the generator define
   the only denominator against which it is evaluated.
3. Apply the requested preservation profile and scope. Record exclusions before
   compression. Full-source mode cannot exclude hard material just to fit.
4. Draft a qualified lede and concise supporting explanations. Deduplicate,
   simplify syntax, and share definitions without collapsing distinct claims.
5. Map each required unit and relationship to exact output spans. A matching
   topic word or a citation without an explanation is insufficient.
6. Verify in both directions: source to output for omission or distortion, and
   output to source for unsupported additions. Label new editorial interpretation
   separately. Test numbers, negation, conditions and attribution explicitly.
7. Repair gaps, recheck dependencies, and publish a versioned coverage report.
   Generation success alone never confers verified-complete status.

Use mechanical checks for links, hashes, required IDs, and numeric consistency;
use semantic review for meaning. Model-based checking and question-answer tests
can reveal failures but do not prove exhaustive equivalence. High-confidence
release claims require a reviewed inventory and adjudication of uncertain
mappings. Record who or what reviewed the material and with which version.

Report statuses such as `candidate`, `gaps-found`, and
`complete-against-reviewed-inventory`. The last requires all required units and
relationships to be represented, no unresolved parsing/extraction gaps, and no
unresolved fidelity findings. An unavailable required document invalidates a
complete-set delivery even if it existed during generation.

Track unit coverage and relationship coverage separately. Distinguish represented,
partial, omitted, out-of-scope, and unresolved. Importance-weighted coverage is
useful for selective briefs, but cannot conceal one missing required exception.
Any percentage names its inventory version and review status; “100% of extracted
units” is not automatically “100% of the source.”

## Single document and document-set construction

A single document starts with a qualified lede, then groups related assertions
into readable sections. Conditions that materially change the lede belong in
the lede, even if their full explanation appears later. Avoid shrinking the text
into unexplained abbreviations or compressed prose that increases reading effort.

A complete set contains an overview, topic documents, a shared glossary when
needed, and a manifest mapping every unit and relationship to its owning output
span. Keep the human reading path separate from the machine coverage ledger.
For example:

```text
brief-set/
  overview.md             # selective orientation and reading routes
  findings.md             # outcomes with their qualifications
  methods.md              # population, procedure, measurements
  limitations.md          # uncertainties and boundaries
  glossary.md             # shared definitions, if needed
  manifest.json           # source version, files, hashes, dependencies
  coverage.json           # units/relationships -> output spans and review
```

Partition by conceptual dependencies rather than arbitrary token chunks. Give
each unit a primary home; controlled repetition is appropriate where omission
would make another document misleading. A document either includes the needed
definitions and qualifications or declares a dependency that the reading route
and assistant retrieval must include. Do not hide a decisive limitation in an
optional link while presenting an unconditional claim in the overview.

Completeness requires the union of the documents to cover all required units
and relationships, with accessible dependencies and consistent versions.
Aggregate union coverage alone is insufficient if cross-document explanations
contradict each other. Revisions invalidate affected mappings and dependent
documents; do not combine yesterday's overview with today's changed findings
under an old completeness report.

## Small worked example

Synthetic source, for illustrating the contracts:

> In an uncontrolled two-week pilot, 18 of 24 adults reported faster searches.
> Median query time fell from 12 to 9 minutes, but setup took 40 minutes per
> person. No children participated. Longer-term performance was not measured.

Selective brief:

> An uncontrolled adult pilot reported faster searches over two weeks, with
> setup overhead; longer-term results remain unknown.

The omission report identifies the participant count, response count, exact
timing measurements, setup duration, and explicit child exclusion as omitted
or insufficiently explicit. Calling this brief complete would be incorrect.

Complete-single candidate:

> Two-week uncontrolled pilot, 24 adults, no children: 18 reported faster
> searches. Median query time fell 12→9 minutes; setup took 40 minutes/person.
> Longer-term performance was unmeasured.

This candidate retains the substantive assertions with less wording. It still
needs inventory-based review. It does not infer that the intervention caused
the improvement or that everyone benefited.

A complete set could put outcomes and setup cost in `findings.md`, with the
uncontrolled design, duration, population and unmeasured outcomes in `methods.md`.
The findings must carry the limiting study description and link the methods as
a required dependency. Splitting this tiny source offers little practical value;
the pattern becomes useful for much longer inputs.

## GroundRecall and session-cost integration

Store the source, unit inventory, relations, mappings and review receipts as
linked artifacts with provenance. Reuse GroundRecall's claims/relations and
review mechanisms where semantics match; do not force definitions, unresolved
questions, or instructions into factual claim records. Preserve release levels
and access policy throughout transformation and retrieval.

Generate a portable Markdown/JSON bundle so the same artifacts work for Codex,
Claude Code, people, and non-assistant applications. Runtime adapters may load a
small overview and then retrieve dependency-complete topic bundles. Retrieval
reports `collection_coverage` (preserved), `required_coverage` for the current
task, and `loaded_context_coverage` for the active session. All reference the
same inventory/profile versions. A complete archive does not mean the active
model has seen every concept, and a delivery receipt does not prove comprehension.
Record unconfirmed delivery when the runtime cannot establish it; invalidate or
reconcile loaded coverage after compaction rather than assuming retention.

Source-complete coverage and task-sufficient active context serve different
purposes. A task loader selects relevant units plus dependencies and checks for
missing evidence before answering. Cross-topic questions may require loading
the full collection or a staged synthesis; that process also needs coverage
tracking. Model-specific token budgets apply to the loaded subset without
changing the collection's semantic contract.

Count the cost of extraction, verification, storage where metered, subsequent
retrieval, regeneration and repeated reloads. Report source words/tokens, total
derived bundle size including duplicated material and coverage metadata, and
actual per-session loaded tokens separately. A shorter overview or lower peak
context does not necessarily reduce total processing cost. Cache verified
artifacts by source hash, inventory/profile version, and transformation version.

Lede-brief packages are the preparation layer in the session roadmap's
observe/select/prepare/compare/transition/verify lifecycle. The session manager
binds packages to the task and workspace; the advisor compares reuse, new
preparation, and selective retrieval; the runtime adapter performs only supported
transitions. The [session roadmap](session-context-and-cost-roadmap.md) owns the
transition state machine, authority checks, and cost-accounting contract.

Add an operational preservation profile for recovery checkpoints: objective,
user constraints, decisions, unresolved issues, workspace/worktree identity,
uncommitted changes and attribution limits, verified results, pending jobs, and
next action are mandatory. This profile supplements source-document coverage.
Resume validates current bindings and file hashes; reading the checkpoint does
not transfer permissions or leases. A changed task revises required coverage,
while a source change invalidates affected preserved and loaded mappings.

Preparation and semantic verification may involve model calls even though the
advisor's rules remain deterministic. Meter those calls and failed attempts.
Account for actual preparation once, show any allocation across consuming
sessions separately, and label projected reuse savings as estimates. Package
reuse must satisfy access restrictions as well as matching version hashes.

Within GroundRecall, generation writes use the session-specific operation paths
and conditional publication defined in the session roadmap. The shared library
returns artifacts or writes to an explicit isolated destination; each consumer
owns publication and concurrency policy. Failure to verify leaves a draft
and a gap report; it cannot replace the last verified bundle. Corrections to
the source invalidate dependent checkpoints or mark them stale. Retaining
source access is essential for recovering details outside the initial profile.

## Implementation sequence

| Stage | Deliverable | Completion gate |
| --- | --- | --- |
| LB-0: Preservation contract and ownership | Epistemap ELB-0 neutral schemas plus shared-library mode/profile/package contracts; choose package home and compatibility policy with all three consumers | Reviewed fixtures distinguish topic mention from claim preservation, exact-text loss from concept loss, and selective from complete output; ownership and dependency direction are explicit. |
| LB-1: Selective brief | Qualified lede, readable condensation, omission report and source mapping | Important qualifiers survive; unsupported additions and unknown source sections are reported. |
| LB-2: Complete single document | Inventory-driven drafting, forward/reverse checks, repair loop and budget-conflict result | All required units/relations pass reviewed mappings; an impossible length constraint never produces a false success. |
| LB-3: Complete document set | Dependency-aware partitioning, overview, navigation and versioned collection publication | Union and dependency checks pass; missing/stale files and misleading standalone claims fail release checks. |
| LB-4: Consumer integrations | Shared package adapter contract; GroundRecall session/retrieval profile; Didactopus educational profile; CiteGeist literature profile | The same shared format supports each consumer without copying mutable domain authority; GroundRecall validates recovery, Didactopus validates instructional sufficiency, CiteGeist validates attribution and source scope. |
| LB-5: Cross-project evaluation and release | Adversarial fixtures, human review, session-recovery/educational/scholarly pilots, cost comparison and installed compatibility matrix | Evaluate omission, unsupported additions, qualification loss, cross-document inconsistency and comprehension; consumer gates below pass, and shortening alone cannot establish success. |

LB-1 through LB-3 belong to the shared library, building on tested Epistemap
ELB-1/ELB-2 operations. Generation and semantic review backends are injected and
versioned; their output does not bypass consumer acceptance policy. LB-0 through
LB-3 can use isolated offline fixtures. ELB-3 validates the installed package
matrix before integrated release.

Only GroundRecall durable writes depend on SC-2; its cost measurement uses SC-3
and its context loading extends SC-5. LB-4 must preserve each consumer's records
and review status. Didactopus and CiteGeist can use the shared library directly
without GroundRecall. Their separate unified-retrieval plans retain the UPR-0
gate when that integration is used; it does not block standalone lede-brief
fixtures. Native assistant compaction remains optional.

Cross-project release gates use three reviewed fixtures: a session resumes with
constraints and correct file targets; a learner receives prerequisites and
needed practice without coverage being counted as mastery; and a scholarly
synthesis preserves methods, limitations, disagreement and attribution without
promoting citations or claiming full-paper coverage from an abstract. Pin source,
inventory, graph-operation, generator and reviewer versions for reproduction.

The integrated delivery sequence is I-1 packages/checkpoints, I-2 coverage-aware
loading and cost advice, and I-3 optional automated transitions, as specified in
the session roadmap. LB-0 through LB-3 supply I-1 package formats; LB-4/LB-5 and
the SC-5 loader contract are developed together for I-2. I-3 adds runtime control
without changing the portable preservation contract or requiring automation for
manual use. Each increment has its acceptance gate in the session roadmap.

Test nested exceptions, negation, conflicting sources, repeated statements with
different scope, table-only facts, figure-only evidence, footnotes, ambiguous
pronouns, procedural ordering, exact quantities, source updates and deliberately
unachievable word budgets. Evaluate source-to-inventory recall independently
from inventory-to-output coverage. Use fresh readers or task evaluations to
test whether shorter output remains understandable, not merely checklist-complete.
