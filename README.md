# Secure Surveillance & Digital Evidence Management Platform

> A security-first engineering project for turning live surveillance detections into traceable, protected, and auditable digital evidence.

[![Status](https://img.shields.io/badge/status-active%20development-orange)](#project-status)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688)](backend/README.md)
[![AI Engine](https://img.shields.io/badge/AI%20engine-Python%20%2B%20OpenCV-blue)](ai-engine/README.md)
[![Database](https://img.shields.io/badge/database-PostgreSQL-336791)](#technology-stack)
[![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-lightgrey)](#license)

## Overview

This repository contains a production-oriented surveillance and digital-evidence platform designed around one core idea:

**A detection should not become useful evidence unless the system can preserve its provenance, integrity, confidentiality, and audit history.**

The platform combines a dedicated AI detection engine with a modular FastAPI backend and a PostgreSQL-backed evidence domain. The current implementation includes:

- Camera / RTSP streaming
- Object detection (Ultralytics / YOLO)
- AI event ingestion and incident classification
- Evidence encryption, signing, verification, and transfer workflows
- Role-based access control (RBAC) and authentication
- Audit logging and chain-of-custody foundations

The repository is intentionally developed as an engineering portfolio project. Documentation distinguishes **implemented** capabilities from remaining production-hardening work.

## What the system does

```text
Camera / RTSP source
        │
        ▼
┌─────────────────────┐
│     AI Engine       │
│  frame processing   │
│  detection + models │
│  streaming + events │
└──────────┬──────────┘
           │ detection events
           ▼
┌─────────────────────┐
│    Backend API      │
│  auth / RBAC        │
│  AI ingestion       │
│  incidents          │
│  evidence lifecycle │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Evidence Security  │
│  hashing / manifests│
│  AES-GCM encryption │
│  RSA-PSS signatures │
│  verification       │
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
- Production weight loading requires a configured SHA-256 digest (see [AI engine setup](ai-engine/README.md))
- Optional stream add-ons use camera/sequence-aware box matching for pose observation confirmation (never synthetic person IDs)
- Add-on analysis is opt-in and emitted through event schema `1.1`; schema `1.0` remains the default
- OCR placeholders are suppressed; enabled model weights require local paths plus configured SHA-256 digests
- Unit and integration test coverage

### Backend platform
- FastAPI application with modular feature boundaries
- Async SQLAlchemy / PostgreSQL persistence
- Alembic migrations
- Authentication and RBAC
- MFA challenge infrastructure and account lockout
- AI detection ingestion and incident classification
- Evidence lifecycle, transfer, and verification workflows
- Redis integration
- MinIO / object-storage integration
- Audit logging
- Health / readiness endpoints

### Evidence integrity and security
- SHA-256 content and manifest digests
- AES-256-GCM authenticated encryption
- RSA-PSS / SHA-256 evidence signatures
- Separated key-wrapping / content-encryption responsibilities
- Evidence verification workflows
- Database protections for audit and chain-of-custody records
- Idempotency and transaction-boundary work across sensitive workflows

## Technology stack

| Layer                | Technologies                                            |
| -------------------- | ------------------------------------------------------- |
| AI engine            | Python, FastAPI, OpenCV, NumPy, Pydantic, Ultralytics   |
| Backend              | Python, FastAPI, SQLAlchemy 2.x, Alembic                |
| Database             | PostgreSQL                                              |
| Cache / coordination | Redis                                                   |
| Object storage       | MinIO / S3-compatible storage                           |
| API contract         | OpenAPI 3.1                                             |
| Testing              | Pytest, pytest-asyncio, coverage                        |
| Quality              | Ruff, Mypy                                              |
| Infrastructure       | Docker / Docker Compose                                 |

## Required executable programs & runtime dependencies

To run the full system locally you need the following installed on the host machine.

### Core runtime

| Program / Package     | Purpose                                      | Typical install command                          |
| --------------------- | -------------------------------------------- | ------------------------------------------------ |
| **Python 3.11+**      | Backend + AI engine runtime                  | `python --version` (install from python.org)     |
| **pip**               | Python package installer                     | Bundled with Python                              |
| **Docker**            | Runs PostgreSQL, Redis, MinIO containers     | [docker.com](https://www.docker.com/get-started) |
| **Docker Compose**    | Orchestrates local infrastructure services   | Included with modern Docker Desktop              |
| **Git**               | Clone and manage the repository              | `git --version`                                  |

### Database & supporting services (via Docker)

| Service        | Image / Notes                          | Port (default) |
| -------------- | -------------------------------------- | -------------- |
| **PostgreSQL** | Official `postgres:16` (or compatible) | 5432           |
| **Redis**      | Official `redis:7`                     | 6379           |
| **MinIO**      | S3-compatible object storage           | 9000 / 9001    |

These are started with:

```bash
docker compose up -d postgres redis minio
```

### Python tools (installed inside virtual environments)

| Tool              | Purpose                                      |
| ----------------- | -------------------------------------------- |
| **uvicorn**       | ASGI server for FastAPI applications         |
| **alembic**       | Database schema migrations                   |
| **pytest**        | Unit & integration testing                   |
| **ruff**          | Linting / formatting                         |
| **mypy**          | Static type checking                         |
| **OpenCV**        | Frame decoding & image processing (AI engine)|
| **Ultralytics**   | YOLO detection models                        |
| **NumPy**         | Numerical processing                         |
| **Pydantic**      | Data validation & settings                   |
| **SQLAlchemy 2.x**| Async ORM                                    |
| **cryptography**  | AES-GCM, RSA-PSS, hashing primitives         |
| **argon2-cffi**   | Password hashing                             |
| **python-jose** / **PyJWT** | JWT handling                    |
| **redis-py**      | Redis client                                 |
| **boto3** / **minio** | Object storage client                     |

### Optional but recommended

| Program           | Purpose                                      |
| ----------------- | -------------------------------------------- |
| **Make**          | Convenience targets (if a Makefile is present)|
| **curl** / **httpie** | Quick API smoke tests                     |
| **psql**          | Direct PostgreSQL inspection                 |
| **redis-cli**     | Redis inspection                             |

> **Note:** Model weights (YOLO checkpoints) are **not** committed. They must be downloaded separately and referenced by path + SHA-256 digest in configuration. See [ai-engine/README.md](ai-engine/README.md).

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
├── backend/                   # Primary FastAPI application
│   ├── app/
│   │   ├── core/
│   │   ├── db/
│   │   └── modules/
│   ├── migrations/
│   └── tests/
├── Architecture Design/       # ERD, UML, activity and architecture diagrams
├── documentation/             # API and engineering documentation
├── database/                  # Legacy / parallel database foundation
├── docker/                    # Local integration / test infrastructure
├── scripts/                   # Repository-level utility scripts
└── .ai/                       # Engineering context, decisions and handoff docs
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

The repository already contains a substantial set of activity, sequence, ERD, and other architecture diagrams. Portfolio documentation links the most important design artefacts without treating a diagram as proof of implementation.

## Security model

Security is treated as a domain invariant rather than a final checklist.

| Concern                  | Current direction                                         |
| ------------------------ | --------------------------------------------------------- |
| Password storage         | Argon2id                                                  |
| Access authentication    | JWT with issuer/audience validation and expiry            |
| Refresh tokens           | Hashed storage, token families, rotation/reuse controls   |
| Authorization            | Explicit RBAC permissions at API/service boundaries       |
| MFA                      | Redis-backed challenge infrastructure                     |
| Evidence confidentiality | AES-256-GCM                                               |
| Evidence integrity       | SHA-256 digests and authenticated encryption              |
| Evidence signatures      | RSA-PSS with SHA-256                                      |
| Audit / custody          | Append-only database protections and audit events         |
| HTTP hardening           | Correlation IDs, security headers, trusted hosts, CORS    |

See the [security model](docs/security-model.md) for the threat-oriented view and remaining hardening work.

## Local development

### Backend

```powershell
# Windows PowerShell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d postgres redis minio
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
# Linux / macOS
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
docker compose up -d postgres redis minio
alembic upgrade head
uvicorn app.main:app --reload
```

### AI engine

```powershell
# Windows PowerShell
cd ai-engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pip install -e ".[dev,model]"   # includes Ultralytics + OpenCV extras
```

```bash
# Linux / macOS
cd ai-engine
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pip install -e ".[dev,model]"
```

> **Important:** Do **not** commit local `.env` files, private keys, model weights, or `.secrets` material. Use the tracked `.env.example` files as configuration templates.

### Quick health check

Once both services and infrastructure are running:

```bash
# Backend readiness
curl http://localhost:8000/health

# AI engine readiness (port may vary — check ai-engine config)
curl http://localhost:8001/health
```

## Project status

**Status: active development / portfolio engineering project.**

The current codebase is beyond a simple proof of concept, but it is **not** presented as a finished production deployment. The most important known gap is the remaining custody lifecycle orchestration. Other open work includes:

- Closing OpenAPI-to-implementation gaps
- Completing the AI quality gate
- Validating the complete end-to-end surveillance-to-custody flow
- Production hardening (observability, key management, load testing, etc.)

For the authoritative engineering state, see [`.ai/01_CURRENT_STATE.md`](.ai/01_CURRENT_STATE.md).

## Roadmap

### Phase 1 — Core platform foundations
- [x] Architecture and domain modelling
- [x] FastAPI backend foundation
- [x] PostgreSQL persistence and migrations
- [x] Authentication / RBAC foundations

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
- [ ] Cross-service failure / recovery testing

### Phase 5 — Production hardening
- [ ] Observability and operational telemetry
- [ ] Key / secret management hardening
- [ ] Load and resilience testing
- [ ] Security testing and threat-model validation
- [ ] Deployment hardening and operational runbooks

See the detailed [roadmap](docs/roadmap.md).

## Screenshots & visual documentation

The repository already contains rendered activity and architecture diagrams under `Architecture Design/`. A dedicated visual gallery can be added as the application UI becomes stable enough to capture representative screens.

**Recommended portfolio screenshots:**

1. Surveillance dashboard / camera grid
2. Live AI detection overlay
3. Incident details and classification
4. Evidence detail + integrity / verification status
5. Chain-of-custody timeline
6. Audit / reporting view
7. System architecture diagram

See [docs/screenshots.md](docs/screenshots.md) for the capture checklist.

## Engineering principles

- **Security by design** — security-sensitive operations are explicit in the domain model.
- **Evidence before convenience** — integrity, provenance, and auditability take precedence over shortcuts.
- **Contract-driven APIs** — OpenAPI is treated as a design contract, not a substitute for implementation tests.
- **Modular boundaries** — routers remain thin; domain / security logic belongs in services and supporting modules.
- **Testable infrastructure** — unit, integration, and RTSP-oriented tests are part of the architecture.
- **Honest status reporting** — documentation separates implemented behaviour from planned or partially implemented work.

## Contributing

This is currently a personal portfolio project. Contributions, architecture feedback, security review, and engineering discussion are welcome through GitHub issues and pull requests.

Before opening a PR:

1. Keep secrets and local runtime artefacts out of commits.
2. Preserve security invariants.
3. Add or update tests for behavioural changes.
4. Update the relevant architecture / API documentation.
5. Explain migrations and data-model changes clearly.

## License

No open-source license has been declared yet. Until a license is added to the repository, treat the code as **all rights reserved**.
