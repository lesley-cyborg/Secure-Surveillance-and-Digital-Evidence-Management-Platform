# AI Detection to Evidence Pipeline: Test Coverage Map

## Overview
This document maps the end-to-end AI surveillance pipeline to its verifying integration tests. It demonstrates that the system is validated for correctness, concurrency safety, idempotency, and cryptographic integrity.

Rather than relying on a single, brittle monolithic End-to-End (E2E) test, the pipeline is verified through deeply integrated, logically separated test suites that prove the contract at each boundary.

## Coverage Matrix

| Pipeline Stage | Responsibility | Verifying Test File | Key Assertions Proven |
| :--- | :--- | :--- | :--- |
| **1. Event Serialization** | AI Engine formats payload, adds auth/idempotency headers. | `ai-engine/tests/integration/test_backend_event_delivery.py` | Correct HTTP headers, deterministic JSON, retry/dead-letter logic. |
| **2. Ingestion & Persistence** | Backend validates schema, camera, model; persists detection. | `backend/tests/integration/test_ai_ingestion_persistence.py` | Schema validation, unknown/inactive resource rejection, exact payload persistence. |
| **3. Incident Classification** | Backend evaluates threat level; creates/reuses Incident record. | `backend/tests/integration/test_detection_incident_classification.py` | Qualifying threats create `CRITICAL` incidents; non-qualifying create none; deduplication window logic. |
| **4. Evidence Bridge** | Separate endpoint ingests artifact linked to detection/incident. | `backend/tests/integration/test_ai_evidence_end_to_end.py` | Correct linking of `incident_id` and `source_detection_id` to the new evidence record. |
| **5. Cryptography & Storage** | Payload encrypted, wrapped key stored, MinIO upload verified. | `backend/tests/integration/test_ai_evidence_end_to_end.py` | RSA-OAEP-SHA256 key wrapping, successful MinIO fetch, and **decryption to original plaintext**. |
| **6. Custody & Audit** | Chain of custody record and audit log generated. | `backend/tests/integration/test_ai_evidence_end_to_end.py` | `CustodyRecord` (ACQUIRED) and `AuditLog` (EVIDENCE_INGESTED) are atomically created. |

## Failure Path Coverage

The test suite explicitly validates that the system fails safely and securely under adverse conditions:

- ✅ **Idempotency / Exact Retries**: Resubmitting the exact same payload returns HTTP 200 with `duplicate: true` and creates **zero** additional database rows.
- ✅ **Concurrency Race Conditions**: Concurrent identical uploads are resolved at the PostgreSQL level (via unique constraints/advisory locks), resulting in exactly **one** persisted Evidence/Incident record.
- ✅ **Artifact Conflicts**: Attempting to reuse an `artifact_id` with a *different* payload correctly returns HTTP 409 Conflict.
- ✅ **Invalid Resources**: Events referencing unknown or inactive cameras/models are rejected before any persistence occurs.
- ✅ **Schema Validation**: Malformed payloads (e.g., missing bounding box coordinates, invalid UUIDs) are rejected by Pydantic at the API boundary.

## Architectural Boundaries Enforced by Tests

The tests explicitly prove that the **AI Engine does NOT**:
- Classify the incident severity or priority.
- Generate cryptographic hashes for evidence.
- Encrypt evidence payloads.
- Create custody or audit records.

The **Backend DOES**:
- Authoritatively classify the incident based on detection metadata.
- Generate and wrap encryption keys.
- Secure the payload and manage the MinIO storage lifecycle.
- Maintain the authoritative chain of custody and audit trail.

This separation ensures that the AI acts strictly as an *observer*, while the Backend remains the authoritative *enforcer* of security and compliance.