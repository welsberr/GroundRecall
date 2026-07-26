# Confidence migration and readiness

GroundRecall keeps legacy scalar fields such as `confidence_hint` readable for
older stores, but typed confidence assessment records are now the preferred
contract for downstream Epistemap use.

## Commands

Run a non-mutating migration plan:

```bash
groundrecall confidence-migrate STORE --report confidence-migration.json
```

Apply the migration:

```bash
groundrecall confidence-migrate STORE --apply --report confidence-migration.json
```

Before applying, GroundRecall copies the store to `STORE.confidence-migrate.bak`
unless `--backup BACKUP_DIR` is supplied. Restore with:

```bash
groundrecall confidence-restore STORE BACKUP_DIR --report confidence-restore.json
```

Check whether a store is assessment-ready:

```bash
groundrecall confidence-readiness STORE --report confidence-readiness.json
```

## Semantics

- Migration is append-only at the record level: it appends typed
  `extraction_fidelity` assessments and preserves the legacy scalar fields.
- `confidence_hint` is adapter extraction fidelity only. It is not reviewer
  endorsement and is not promotion authority.
- Scalar hints are migrated only when producer metadata identifies method name,
  method version, policy ID, basis record IDs, deterministic basis hash,
  rationale, and extracted field.
- Legacy zero values are treated as ambiguous unless metadata explicitly marks
  the zero as intentional.
- New imports stamp adapter-specific confidence producer metadata centrally
  during ingest, so source adapters do not share one blanket conversion policy.

This keeps old stores usable while making confidence provenance explicit enough
for Epistemap graph assessment, calibration, and future Bayesian policy work.
