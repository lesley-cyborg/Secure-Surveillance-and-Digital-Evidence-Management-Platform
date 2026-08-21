# Project Roadmap

## Current position

The project has progressed from architecture and modelling into implementation of the backend, AI engine, evidence security, and cross-service integration foundations.

The roadmap intentionally distinguishes **implemented foundations** from **production-complete workflows**.

## Priority 1 — Complete chain of custody

- [ ] Implement custody service orchestration
- [ ] Define custody request/response schemas
- [ ] Integrate authorization
- [ ] Define custody signature generation/verification
- [ ] Add stable-row concurrency locking
- [ ] Complete custody idempotency handling
- [ ] Add custody audit events
- [ ] Add lifecycle integration tests
- [ ] Add chain verification tests
- [ ] Implement the thin custody router against the OpenAPI contract

## Priority 2 — Close contract/implementation gaps

Perform an operation-by-operation comparison:

```text
OpenAPI operation
      ↓
Router
      ↓
Service
      ↓
Repository
      ↓
Tests
```

For each operation, record:

- contract exists
- route exists
- authorization exists
- validation exists
- persistence exists
- audit metadata exists
- idempotency is enforced where required
- happy-path test exists
- failure-path test exists

## Priority 3 — AI engine quality gate

- [ ] CPU Docker hardening
- [ ] Model lifecycle verification
- [ ] Model provisioning strategy
- [ ] Final Ruff/Mypy/Pytest gate
- [ ] Real container inference verification
- [ ] RTSP reconnect/failure testing
- [ ] Backpressure and inference concurrency validation

## Priority 4 — End-to-end surveillance flow

The target demonstrable workflow is:

```text
RTSP camera
  ↓
AI frame processing
  ↓
Object detection
  ↓
Detection event
  ↓
Backend ingestion
  ↓
Incident classification
  ↓
Evidence creation
  ↓
Evidence hashing
  ↓
Evidence encryption/storage
  ↓
Evidence verification
  ↓
Evidence transfer
  ↓
Chain of custody
  ↓
Audit/report
```

Each transition should have both success and failure-path tests.

## Priority 5 — Production hardening

- [ ] Structured observability
- [ ] Metrics and tracing
- [ ] Failure recovery/runbooks
- [ ] Background jobs where justified
- [ ] Production secret/key management
- [ ] Deployment hardening
- [ ] Load testing
- [ ] Resilience testing
- [ ] Security testing
- [ ] Backup/restore verification
- [ ] Operational documentation

## Portfolio milestones

### Milestone A — Engineering foundation
Architecture, data model, API contract, backend and AI engine foundations.

### Milestone B — Secure evidence pipeline
Encryption, signatures, verification, evidence transfers, audit controls.

### Milestone C — Demonstrable end-to-end system
Live/synthetic RTSP → AI detection → backend ingestion → incident → evidence → verification → custody.

### Milestone D — Production-readiness study
Threat model, observability, resilience, load testing, deployment and operational controls.

## Definition of done for the portfolio

The project should be considered portfolio-complete when a reviewer can:

1. Clone the repository.
2. Follow the setup guide.
3. Start the required local infrastructure.
4. Run automated tests.
5. Understand the architecture from the diagrams.
6. Trace one detection through the evidence lifecycle.
7. Inspect how evidence integrity is protected.
8. See authorization and audit controls.
9. Reproduce failure-path behaviour.
10. Clearly distinguish implemented functionality from future work.
