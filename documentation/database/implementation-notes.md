# Database Implementation Notes

## ERD alignment

The initial migration implements the entities defined by the approved ERD, with one required
workflow refinement: `evidence_transfers`.

The OpenAPI contract defines transfer initiation, acceptance, and rejection. A transfer has a
mutable workflow state (`PENDING`, `ACCEPTED`, `REJECTED`, `EXPIRED`, or `CANCELLED`), while the
chain of custody must remain append-only. Therefore:

- `evidence_transfers` stores the current transfer workflow state.
- `chain_of_custody` stores immutable events such as `TRANSFER_INITIATED`,
  `TRANSFER_ACCEPTED`, and `TRANSFER_REJECTED`.
- Acceptance and rejection append custody records; they never update prior custody history.

## Redis-owned transient data

The following are deliberately not PostgreSQL tables:

- MFA challenges
- Login throttling counters
- Short-lived idempotency records
- Permission caches
- Refresh-token reuse alerts and temporary deny lists

Durable authentication sessions remain in PostgreSQL. Redis accelerates security controls but is
not the sole source of truth for long-lived sessions.

## Forensic integrity controls

The migration installs PostgreSQL triggers that prevent updates and deletes on:

- `audit_logs`
- `chain_of_custody`

A second custody trigger requires each new record to reference the latest custody record for the
same evidence item. The application service remains responsible for calculating and verifying the
cryptographic record hash and digital signature.

## Deletion strategy

Evidence, custody records, audit logs, and verification records use restrictive foreign keys.
Business deletion should be implemented as status transitions and retention workflows rather than
physical row deletion.
