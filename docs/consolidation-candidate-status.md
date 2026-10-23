# Consolidation development candidates

Status: preserved development work, 2026-10-23. This branch is not a release.

Branch: `development/consolidation-candidates-20261023`.

This branch preserves the pending application API/browser dashboard, workspace
retrieval, context packages, operator utilities, tests, and design documents.
The source files are candidates for selective graduation onto `main`, not a
claim that the entire consolidation roadmap has passed.

The UPR-0 typed-record reconciliation gate remains open. Application service
authorization, scope/cursor contracts, and browser acceptance remain required
before release. The experimental application routes in the MCP HTTP server
are disabled by default even when a store is configured. Enabling them from
Python is for isolated development fixtures only; it is not supported for a
shared or remotely exposed service. The owner-local dashboard is a separate
development surface with its own controls and still requires browser QA.

Private run receipts and generated indexes are excluded from this branch and
retained locally. A verified private copy of every originally pending file was
made before consolidation. Further work and individual release decisions are
tracked in the [consolidation roadmap](repository-consolidation-roadmap.md).
