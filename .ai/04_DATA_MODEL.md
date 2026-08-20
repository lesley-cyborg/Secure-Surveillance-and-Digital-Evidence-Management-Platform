# Data Model

## Verified ORM scope

The backend has 24 mapped tables.

Core relationships include:

- users ↔ roles ↔ permissions
- sites → cameras
- cameras → AI configurations
- cameras → detection events
- detection events → incidents
- incidents → evidence
- evidence → evidence keys
- evidence → verification records
- evidence → transfers
- evidence → custody records
- incidents/evidence → notifications
- reports → incidents / exports

## Evidence model

`backend/app/db/models/evidence.py` defines evidence with:

- evidence number
- incident
- source detection/artifact
- submitting user
- source/evidence type
- original filename/MIME/size
- storage bucket/object/version
- original SHA-256
- encrypted SHA-256
- manifest SHA-256
- digital signature
- lifecycle status
- capture/ingestion timestamps

Evidence keys support versioning and an active-key constraint.

Evidence verification has idempotency support in the current model.

## Evidence transfers

Transfers contain:

- evidence
- from/to users
- initiating user
- purpose
- status
- expiry
- decision information
- idempotency keys

There is a partial uniqueness constraint intended to prevent more than one pending transfer for an evidence item.

## Custody

`chain_of_custody` contains:

- evidence ID
- actor
- from/to users
- previous record ID
- transfer ID
- event type
- purpose
- source IP
- device identifier
- metadata
- record hash
- digital signature
- occurrence time
- idempotency scope/key

There is a unique record-hash constraint and a lifecycle idempotency unique constraint.

## Important database rule

The Alembic migrations are authoritative for database behaviour.

Do not infer constraints from ORM models alone.
