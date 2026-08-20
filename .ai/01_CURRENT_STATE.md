# Current State

## Snapshot

### Backend

The current `backend/` contains:

- application factory/lifespan
- security middleware
- JWT authentication
- password hashing
- MFA challenge infrastructure
- refresh-token lifecycle
- RBAC dependencies/service/repository
- user management
- AI ingestion
- evidence lifecycle
- evidence encryption
- evidence signing
- evidence verification
- evidence transfers
- incident classification
- audit repository/actions
- database models and migrations
- health endpoints

### AI engine

The current `ai-engine/` contains:

- detector protocol/schema layer
- frame decoding/processing
- model registry
- device selection
- inference gate
- Ultralytics detector adapter
- model lifecycle
- streaming/RTSP source
- frame sampling/queueing
- reconnect policy
- detection event serialization/dispatch
- backend incident sink
- API composition
- unit/integration tests
- CPU Docker packaging artifacts

## Database

The repository contains **24 ORM tables** in the backend model graph, confirmed by the repository's validation report:

- ai_models
- audit_logs
- auth_sessions
- camera_ai_configs
- cameras
- chain_of_custody
- detection_events
- evidence
- evidence_keys
- evidence_transfers
- evidence_verifications
- incident_assignments
- incident_notes
- incidents
- notifications
- permissions
- report_exports
- report_incidents
- reports
- role_permissions
- roles
- sites
- user_roles
- users

## Migrations

The current backend has more migrations than the original validation report recorded.

Current migration chain:

`20260719_0001`
→ `20260719_0002`
→ `20260801_0003`
→ `20260809_0004`
→ `d42977a3d0bc`
→ `cc0c02de375c`
→ `2a69569bb323`
→ `bf2b79caa708`

The latest custody-related migration is:

`bf2b79caa708_add_custody_lifecycle_idempotency.py`

It adds custody idempotency scope/key plus a unique constraint and paired-null check.

## API contract

`documentation/api/openapi.yaml` is OpenAPI 3.1.2.

Repository validation reports:

- 39 paths
- 48 operations
- 70 schemas
- 36 RBAC permissions
- RBAC metadata on every operation
- audit metadata on every operation
- sensitive writes require an idempotency key

These are contract/documentation facts, not proof that every operation is implemented.

## Important documentation drift

The following documents are stale relative to current implementation:

- root README still describes a Phase 3 foundation
- backend README says Authentication/RBAC is the next module, although authentication/RBAC code and tests exist
- the original validation report only lists the first two migrations even though the backend now has eight migrations
- Phase 5.2 documentation contains unchecked work items even though real-model validation and CPU performance baseline items are marked complete

AI agents must prefer current code/tests/migrations and flag this drift.

## Current high-priority area

Custody is the most obvious incomplete security-sensitive module:

- `backend/app/modules/custody/integrity.py` is implemented and tested.
- `backend/app/modules/custody/repository.py` is partially implemented.
- `backend/app/modules/custody/service.py` is empty.
- `backend/app/modules/custody/router.py` only creates the router.
- `backend/tests/unit/test_custody_integrity.py` contains integrity tests.
- `backend/tests/integration/test_custody_lifecycle.py` is empty.

This means custody lifecycle orchestration is not yet implemented despite the data model and database triggers existing.
