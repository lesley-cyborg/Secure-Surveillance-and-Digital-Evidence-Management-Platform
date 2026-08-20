# Security Model

## Authentication

Verified implementation direction includes:

- Argon2id password hashing
- JWT access tokens
- refresh-token hashing
- refresh-token family identifiers
- token expiry
- issuer/audience validation
- MFA challenge support
- account lockout
- login auditing

Relevant source:

- `backend/app/core/security.py`
- `backend/app/modules/auth/`
- `backend/tests/core/test_security.py`
- authentication integration tests

## Authorization

RBAC is implemented under:

`backend/app/modules/rbac/`

The contract/seed contains 36 permissions.

Authorization should remain explicit at API/service boundaries.

## HTTP security

Backend middleware includes:

- correlation IDs
- security headers
- trusted hosts
- CORS

## Evidence confidentiality

Evidence encryption uses AES-256-GCM.

The encryption module validates:
- original content size
- original SHA-256
- forensic manifest digest
- encrypted payload SHA-256
- authenticated decryption

Key wrapping is separated from content encryption.

## Evidence signatures

Evidence signing uses RSA-PSS with SHA-256 according to the signing module's declared algorithm.

Signature envelopes include:
- algorithm
- key reference
- key version
- signature

Private cryptographic material is stored outside source-controlled application code in the local `.secrets` area.

## Forensic immutability

Initial database migration creates:

- `trg_audit_logs_immutable`
- `trg_chain_of_custody_immutable`
- `trg_chain_of_custody_validate_link`

The chain-of-custody table is protected against UPDATE/DELETE and has a database trigger validating that a new record links to the latest record.

## Security invariant

Never weaken:
- authorization
- audit logging
- evidence hashing
- evidence encryption/authentication
- signature verification
- custody immutability
- transaction boundaries

just to make a feature or test pass.

## Secrets

The supplied repository archive contained local `.env` files and private evidence cryptographic material.

The `.ai` package intentionally does not copy any secret values.

Before publishing the repository or sending it to third-party AI services:
- remove/rotate exposed credentials and private keys
- ensure `.env` and `.secrets` are ignored
- avoid uploading secret files
