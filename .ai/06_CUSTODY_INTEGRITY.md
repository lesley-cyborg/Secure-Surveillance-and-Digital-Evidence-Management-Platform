# Custody Integrity — Grounded State

## Current implementation

File:

`backend/app/modules/custody/integrity.py`

The implementation is real, not merely planned.

It currently:

- uses schema version `1.0`
- requires timezone-aware timestamps
- normalizes timestamps to UTC
- serializes timestamps to microsecond precision
- builds a deterministic JSON payload
- uses `ensure_ascii=False`
- rejects NaN
- sorts keys
- uses compact separators
- encodes canonical JSON as UTF-8
- calculates SHA-256
- validates previous hashes as lowercase 64-character SHA-256 values

The artifact returned contains:

- `canonical_bytes`
- `record_hash`

## Current tests

`backend/tests/unit/test_custody_integrity.py` verifies:

- deterministic hashes
- metadata changes alter the hash
- SHA-256 output shape
- naive timestamps are rejected

## Current repository

`backend/app/modules/custody/repository.py` provides:

- latest custody lookup
- latest lookup with `FOR UPDATE`
- custody creation
- custodian-anchor lookup with `FOR UPDATE`
- idempotency lookup

## Critical incomplete area

`backend/app/modules/custody/service.py` is currently empty.

`backend/app/modules/custody/router.py` is currently only a router declaration.

`backend/tests/integration/test_custody_lifecycle.py` is currently empty.

Therefore the custody lifecycle is not complete.

## Concurrency concern

The repository's `get_latest_for_update()` locks an existing custody row.

For the first custody event, no custody row exists, so there is no row to lock.

The database trigger `validate_custody_chain_link()` also queries the latest custody record but does not itself serialize concurrent first inserts.

Therefore the "first custody record" concurrency path requires careful transaction serialization around a stable parent row (for example the evidence row) or another proven locking mechanism.

Do not assume the existing `FOR UPDATE` on the custody query solves this race.

## Database trigger

The initial migration defines:

- immutable custody records
- latest-link validation

The trigger expects each new record to reference the latest custody record for that evidence, or no previous record for the first event.

## Idempotency

Migration:

`bf2b79caa708_add_custody_lifecycle_idempotency.py`

adds:

- `idempotency_scope`
- `idempotency_key`
- unique `(evidence_id, idempotency_scope, idempotency_key)`
- a check constraint requiring both values to be NULL or both non-NULL

## Digital signature gap

`CustodyRecord.digital_signature` is non-null in the ORM/database model.

The current `integrity.py` function only returns canonical bytes and a SHA-256 hash.

The evidence module has a separate, implemented RSA-PSS signing system.

A future custody service must explicitly resolve how custody signatures are produced and verified rather than inventing a second cryptographic scheme.

## Recommended next implementation

Before implementing the custody router:

1. define the service contract
2. inspect the evidence signing implementation
3. decide how custody signatures are generated
4. implement stable-row locking for concurrency
5. implement idempotent lifecycle orchestration
6. add lifecycle integration tests
7. add chain verification/tamper tests
8. then implement the thin API router
