# Secure Surveillance Platform OpenAPI Contract

This package contains the initial monolithic OpenAPI contract:

- `documentation/api/openapi.yaml`

The contract uses OpenAPI 3.1.2 and the OpenAPI 3.1 JSON Schema dialect.
It defines 48 operations across 9 API groups.

## API groups

- Authentication: 5 operations
- Users: 8 operations
- Cameras: 6 operations
- Incidents: 9 operations
- Evidence: 7 operations
- Chain of Custody: 5 operations
- Reports: 4 operations
- Notifications: 2 operations
- Audit: 2 operations

## Contract conventions

- JWT bearer authentication for protected endpoints.
- `x-rbac-permissions` documents required application permissions.
- `x-audit` documents the audit event and captured context.
- `Idempotency-Key` is required on sensitive write operations.
- `X-Correlation-ID` supports request tracing.
- Standard reusable error responses are defined under `components.responses`.
- Evidence ingestion uses `multipart/form-data`.
- Evidence content uses a binary response.
- Report generation is asynchronous and returns HTTP 202.

The `schemas/` and `examples/` directories are placeholders for a future modular split.
