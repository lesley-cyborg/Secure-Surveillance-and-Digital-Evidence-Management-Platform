# Secure Surveillance & Digital Evidence Management Platform

> A security-first engineering project for turning live surveillance detections into traceable, protected, and auditable digital evidence.

[![Status](https://img.shields.io/badge/status-active%20development-orange)](#project-status)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688)](backend/README.md)
[![AI Engine](https://img.shields.io/badge/AI%20engine-Python%20%2B%20OpenCV-blue)](ai-engine/README.md)
[![Database](https://img.shields.io/badge/database-PostgreSQL-336791)](#technology-stack)

## Overview

This repository contains a production-oriented surveillance and digital-evidence platform designed around one core idea: **a detection should not become useful evidence unless the system can preserve its provenance, integrity, confidentiality, and audit history.**

The platform combines a dedicated AI detection engine with a modular FastAPI backend and a PostgreSQL-backed evidence domain. The current implementation includes camera/RTSP streaming, object detection, AI event ingestion, incident classification, evidence encryption and signing, evidence verification and transfer workflows, RBAC, authentication, audit logging, and chain-of-custody foundations.

The repository is intentionally developed as an engineering portfolio project, so the documentation distinguishes implemented capabilities from remaining production-hardening work.

## What the system does

```text
Camera / RTSP source
        │
        ▼
┌─────────────────────┐
│     AI Engine       │
│ frame processing    │
│ detection + models  │
│ streaming + events  │
└──────────┬──────────┘
           │ detection events
           ▼
┌─────────────────────┐
│     Backend API     │
│ auth / RBAC         │
│ AI ingestion        │
│ incidents           │
│ evidence lifecycle  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Evidence Security   │
│ hashing / manifests │
│ AES-GCM encryption  │
│ RSA-PSS signatures  │
│ verification        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Transfer / Custody  │
│ immutable records   │
│ audit / reporting   │
└─────────────────────┘
```

See the detailed [architecture overview](docs/architecture.md).

## Key engineering features

### AI surveillance pipeline
- RTSP camera/source integration
- Frame decoding, processing, sampling, and queueing
- Device selection and inference gating
- Model registry and lifecycle management
- Ultralytics detector adapter
- Structured detection-event serialization and dispatch
- Backend incident sink integration
- Image-analysis API with optional OCR, face observations, and evidence-only threat signals
- Production weight loading requires a configured SHA-256 digest; see [AI engine setup and integration](ai-engine/README.md)
- Optional stream add-ons use camera/sequence-aware box matching for pose
  observation confirmation, never synthetic person IDs. Add-on analysis is
  opt-in and emitted through event schema `1.1`; schema `1.0` remains the
  default. OCR placeholders are suppressed, and enabled model weights require
  local paths plus configured SHA-256 digests. See
  [AI engine setup and integration](ai-engine/README.md).
- Unit and integration test coverage

### Backend platform
- FastAPI application with modular feature boundaries
- Async SQLAlchemy/PostgreSQL persistence
- Alembic migrations
- Authentication and RBAC
- MFA challenge infrastructure and account lockout
- AI detection ingestion and incident classification
- Evidence lifecycle, transfer, and verification workflows
- Redis integration
- MinIO/object-storage integration
- Audit logging
- Health/readiness endpoints

### Evidence integrity and security
- SHA-256 content and manifest digests
- AES-256-GCM authenticated encryption
- RSA-PSS/SHA-256 evidence signatures
- Separated key-wrapping/content-encryption responsibilities
- Evidence verification workflows
- Database protections for audit and chain-of-custody records
- Idempotency and transaction-boundary work across sensitive workflows

## Technology stack

| Layer | Technologies |
|---|---|
| AI engine | Python, FastAPI, OpenCV, NumPy, Pydantic, Ultralytics |
| Backend | Python, FastAPI, SQLAlchemy 2.x, Alembic |
| Database | PostgreSQL |
| Cache / coordination | Redis |
| Object storage | MinIO / S3-compatible storage |
| API contract | OpenAPI 3.1 |
| Testing | Pytest, pytest-asyncio, coverage |
| Quality | Ruff, Mypy |
| Infrastructure | Docker / Docker Compose |

## Repository structure

```text
secure-surveillance-platform/
├── ai-engine/                 # AI detection and RTSP streaming service
│   ├── api/
│   ├── config/
│   ├── detection/
│   ├── models/
│   ├── streaming/
│   └── tests/
├── backend/                   # primary FastAPI application
│   ├── app/
│   │   ├── core/
│   │   ├── db/
│   │   └── modules/
│   ├── migrations/
│   └── tests/
├── Architecture Design/       # ERD, UML, activity and architecture diagrams
├── documentation/             # API and engineering documentation
├── database/                  # legacy/parallel database foundation
├── docker/                    # local integration/test infrastructure
├── scripts/                   # repository-level utility scripts
└── .ai/                       # engineering context, decisions and handoff docs
```

## Architecture & design documentation

- [Architecture overview](docs/architecture.md)
- [Security model](docs/security-model.md)
- [Local setup guide](docs/setup.md)
- [Project roadmap](docs/roadmap.md)
- [Screenshot checklist](docs/screenshots.md)
- [Architecture Design directory](Architecture%20Design/)
- [OpenAPI contract](documentation/api/openapi.yaml)
- [ERD](Architecture%20Design/01-surveillance-platform-erd.mmd)

The repository already contains a substantial set of activity, sequence, ERD, and other architecture diagrams. The portfolio documentation links the most important design artefacts without pretending that a diagram is proof of implementation.

## Security model

Security is treated as a domain invariant rather than a final checklist.

| Concern | Current direction |
|---|---|
| Password storage | Argon2id |
| Access authentication | JWT with issuer/audience validation and expiry |
| Refresh tokens | Hashed storage, token families, rotation/reuse controls |
| Authorization | Explicit RBAC permissions at API/service boundaries |
| MFA | Redis-backed challenge infrastructure |
| Evidence confidentiality | AES-256-GCM |
| Evidence integrity | SHA-256 digests and authenticated encryption |
| Evidence signatures | RSA-PSS with SHA-256 |
| Audit/custody | Append-only database protections and audit events |
| HTTP hardening | Correlation IDs, security headers, trusted hosts, CORS |

See the [security model](docs/security-model.md) for the threat-oriented view and remaining hardening work.

## Local development

The backend has a Windows PowerShell setup path documented in [`backend/README.md`](backend/README.md). At a high level:

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d postgres redis minio
alembic upgrade head
uvicorn app.main:app --reload
```

For the AI engine:

```powershell
cd ai-engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pip install -e ".[dev,model]"
```

Do not commit local `.env`, private keys, model weights, or `.secrets` material. Use the tracked `.env.example` files as configuration templates.

## Project status

**Status: active development / portfolio engineering project.**

The current codebase is beyond a simple proof of concept, but it is not presented as a finished production deployment. The most important known gap is the remaining custody lifecycle orchestration. Other work includes closing OpenAPI-to-implementation gaps, completing the AI quality gate, validating the complete end-to-end surveillance-to-custody flow, and production hardening.

For the authoritative engineering state, see [`.ai/01_CURRENT_STATE.md`](.ai/01_CURRENT_STATE.md).

## Roadmap

### Phase 1 — Core platform foundations
- [x] Architecture and domain modelling
- [x] FastAPI backend foundation
- [x] PostgreSQL persistence and migrations
- [x] Authentication/RBAC foundations

### Phase 2 — AI surveillance pipeline
- [x] Detection contracts and model abstraction
- [x] RTSP streaming primitives
- [x] Detection event dispatch
- [x] Backend AI ingestion foundations

### Phase 3 — Evidence security
- [x] Evidence lifecycle foundations
- [x] Encryption and signing components
- [x] Evidence verification and transfer foundations
- [ ] Complete custody lifecycle orchestration

### Phase 4 — End-to-end validation
- [ ] RTSP → detection → ingestion → incident → evidence
- [ ] Evidence → verification → transfer → custody → audit
- [ ] Cross-service failure/recovery testing

### Phase 5 — Production hardening
- [ ] Observability and operational telemetry
- [ ] Key/secret management hardening
- [ ] Load and resilience testing
- [ ] Security testing and threat-model validation
- [ ] Deployment hardening and operational runbooks

See the detailed [roadmap](docs/roadmap.md).

## Screenshots & visual documentation

The repository already contains rendered activity and architecture diagrams under `Architecture Design/`. A dedicated visual gallery can be added as the application UI becomes stable enough to capture representative screens.

Recommended portfolio screenshots:

1. Surveillance dashboard / camera grid
2. Live AI detection overlay
3. Incident details and classification
4. Evidence detail + integrity/verification status
5. Chain-of-custody timeline
6. Audit/reporting view
7. System architecture diagram

See [docs/screenshots.md](docs/screenshots.md) for the capture checklist.

## Engineering principles

- **Security by design:** security-sensitive operations are explicit in the domain model.
- **Evidence before convenience:** integrity, provenance, and auditability take precedence over shortcuts.
- **Contract-driven APIs:** OpenAPI is treated as a design contract, not a substitute for implementation tests.
- **Modular boundaries:** routers remain thin; domain/security logic belongs in services and supporting modules.
- **Testable infrastructure:** unit, integration, and RTSP-oriented tests are part of the architecture.
- **Honest status reporting:** documentation separates implemented behaviour from planned or partially implemented work.

## Contributing

This is currently a personal portfolio project. Contributions, architecture feedback, security review, and engineering discussion are welcome through GitHub issues and pull requests.

Before opening a PR:

1. Keep secrets and local runtime artefacts out of commits.
2. Preserve security invariants.
3. Add or update tests for behavioural changes.
4. Update the relevant architecture/API documentation.
5. Explain migrations and data-model changes clearly.

## License

No open-source license has been declared yet. Until a license is added to the repository, treat the code as **all rights reserved**.
