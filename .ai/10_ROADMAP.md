# Roadmap

## Priority 1 — Complete Custody

1. Implement custody service.
2. Define custody request/response schemas.
3. Integrate authorization.
4. Define custody signature generation/verification.
5. Implement stable-row concurrency locking.
6. Implement idempotency.
7. Implement audit events.
8. Add lifecycle integration tests.
9. Add chain verification tests.
10. Implement thin custody router against OpenAPI.

## Priority 2 — Close contract/implementation gaps

Compare each OpenAPI operation against actual routers/services/tests.

Do not implement endpoints blindly; preserve existing architecture.

## Priority 3 — AI engine quality gate

Complete/verify Phase 5.2:

- CPU Docker hardening
- lifecycle verification
- model provisioning strategy
- final Ruff/Mypy/Pytest quality gate
- real container inference verification

## Priority 4 — End-to-end surveillance flow

Validate:

```text
RTSP camera
 -> AI detection
 -> backend ingestion
 -> incident classification
 -> evidence creation
 -> evidence encryption/storage
 -> evidence verification
 -> transfer
 -> custody
 -> audit/report
```

## Priority 5 — Production hardening

- observability
- failure recovery
- background jobs where justified
- secret/key management
- deployment hardening
- integration/load testing
- security testing
- operational documentation
