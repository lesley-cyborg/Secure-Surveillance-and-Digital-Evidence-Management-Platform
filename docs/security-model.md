# Security Model

## Security posture

This project treats security as part of the domain model. Surveillance data and digital evidence have different consequences from ordinary application data, so integrity, confidentiality, provenance, authorization, and auditability are first-class concerns.

## Authentication

The backend security model includes:

- Argon2id password hashing
- JWT access tokens
- access-token expiry
- issuer/audience validation
- refresh-token hashing
- refresh-token family identifiers
- refresh-token rotation/reuse controls
- MFA challenge infrastructure
- account lockout
- login auditing

Relevant implementation areas include `backend/app/core/security.py` and `backend/app/modules/auth/`.

## Authorization

Authorization uses explicit RBAC permissions.

The API contract and seed model define 36 permissions. Protected operations should enforce authorization at API/service boundaries rather than relying on UI visibility.

## HTTP security

Backend middleware includes:

- correlation IDs
- security headers
- trusted hosts
- CORS controls

These controls provide a baseline for request tracing and transport-layer hardening.

## Evidence confidentiality

Evidence content is protected using AES-256-GCM authenticated encryption.

The evidence cryptography flow tracks integrity metadata such as:

- original content size
- original SHA-256
- forensic manifest digest
- encrypted payload SHA-256

Key wrapping is kept separate from content encryption.

## Evidence authenticity

Evidence signing uses RSA-PSS with SHA-256.

A signature envelope records:

- algorithm
- key reference
- key version
- signature

Verification is treated as an explicit operation rather than assuming that successful storage implies authenticity.

## Forensic immutability

The database contains protections for audit and custody records, including immutable-record triggers and validation of chain-of-custody linkage.

The intended invariant is:

```text
new custody record
      │
      ├── links to the expected previous record
      │
      ├── passes integrity validation
      │
      └── becomes append-only history
```

## Secrets management

Never commit:

- `.env`
- `.env.backup`
- private keys
- certificates containing private material
- `.secrets/`
- model weights
- production credentials

The repository's `.gitignore` explicitly covers the relevant local artefacts.

If a secret has ever been committed to a repository, removing the file from the latest commit is not sufficient by itself. Credentials must be rotated/revoked and historical exposure assessed.

## Security invariants

Do not weaken the following simply to make a feature or test pass:

- authorization
- audit logging
- evidence hashing
- authenticated encryption
- signature verification
- custody immutability
- transaction boundaries
- idempotency guarantees

## Remaining hardening

The current roadmap calls for:

- completing custody lifecycle orchestration
- validating the OpenAPI contract against implementation
- end-to-end failure/recovery testing
- observability
- stronger production secret/key management
- load/resilience testing
- security testing and threat-model validation
- deployment hardening
