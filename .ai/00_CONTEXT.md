# Project Context

## Identity

**Project:** Secure Surveillance Platform

**Repository state inspected:** uploaded repository archive supplied on 2026-08-20.

**Primary backend:** `backend/`

**AI/CV service:** `ai-engine/`

**Database design/legacy parallel tree:** `database/`

**Architecture/documentation:** `documentation/` and `Architecture Design/`

## Purpose

The platform is designed as a security-sensitive surveillance system combining:

- camera/video sources
- AI/computer-vision detection
- incident management
- evidence ingestion and storage
- evidence verification
- chain of custody
- auditability
- authentication and RBAC
- reporting
- notifications

The architecture and API contract were designed before implementation.

## Current implementation reality

The repository is beyond the original "Phase 3 foundation" README wording.

The actual backend contains implemented authentication, users/RBAC, evidence, AI ingestion, security middleware, and related tests. The AI engine contains production-model, streaming, and backend-event delivery code.

Several routers remain intentionally empty/thin, including custody and some other domains.

## Technology

Verified from repository structure/configuration:

- Python
- FastAPI
- async SQLAlchemy 2.x
- PostgreSQL
- Alembic
- Redis
- MinIO / S3-compatible object storage direction
- PyJWT
- Argon2 password hashing
- cryptography
- Ultralytics/YOLO production detector
- OpenCV/RTSP streaming
- Docker / Docker Compose
- Ruff
- Mypy
- Pytest

## Source-of-truth hierarchy

1. Current implementation and tests
2. Alembic migrations
3. OpenAPI contract when implementation is intended to conform to it
4. Architecture/design documentation
5. AI memory documents
6. Conversation history

If an older document conflicts with current code, flag the discrepancy.

## Important project philosophy

Evidence and custody are forensic/security domains. Integrity, provenance, immutability, authorization, auditability, and deterministic verification are first-class requirements.
