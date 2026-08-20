# Known Issues / Reconciliation Queue

## K-001 — Custody service is empty

`backend/app/modules/custody/service.py` has no implementation.

**Impact:** custody lifecycle orchestration is incomplete.

## K-002 — Custody router is empty

`backend/app/modules/custody/router.py` only defines the router.

**Impact:** documented custody API operations are not implemented.

## K-003 — Custody lifecycle integration tests are empty

`backend/tests/integration/test_custody_lifecycle.py` is empty.

**Impact:** end-to-end transaction/idempotency/concurrency guarantees are not currently demonstrated by this test file.

## K-004 — First-event concurrency requires a stable lock

`get_latest_for_update()` cannot lock a nonexistent first custody row.

The trigger also reads latest state without a serialization lock.

**Impact:** concurrent first custody inserts require explicit serialization.

## K-005 — Custody signature generation is unresolved

The custody DB model requires `digital_signature`, but the custody integrity artifact currently produces only canonical bytes/hash.

**Impact:** service design must connect custody to an approved signature mechanism.

## K-006 — OpenAPI is ahead of implementation

The contract documents 48 operations, but several routers are empty/thin.

**Impact:** implementation progress must be tracked independently from contract completeness.

## K-007 — Validation report is stale

`validation-report.json` records only two migrations even though eight backend migrations exist.

**Impact:** do not use that report as the current migration-state source of truth.

## K-008 — README phase labels are stale

Root/backend/database README files still describe Phase 3 foundation and authentication as the next implementation area, despite implemented auth/RBAC and AI/evidence functionality.

## K-009 — Parallel `database/` tree

A second database implementation exists under `database/`.

**Impact:** agents can accidentally edit the wrong tree. Prefer `backend/` unless explicitly working on the legacy/parallel tree.

## K-010 — Supplied archive contained local secrets

The uploaded archive included `.env` files and private evidence keys.

**Action:** rotate any credentials/private keys that may have been exposed outside the intended machine; never send those files to another AI.
