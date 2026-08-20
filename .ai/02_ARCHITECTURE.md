# Architecture

## Conceptual system

```text
Cameras / RTSP Sources
        |
        v
AI Engine
  - frame ingestion
  - detection
  - streaming
  - model lifecycle
        |
        v
AI event delivery
        |
        v
Backend AI Ingestion
        |
        v
Incident / Classification
        |
        v
Evidence
  - forensic manifest
  - encryption
  - object storage
  - signing
  - verification
        |
        v
Evidence Transfer / Custody
        |
        v
Audit / Reporting
```

## Backend layering

The repository uses feature modules under:

`backend/app/modules/`

Examples:

- `auth`
- `users`
- `rbac`
- `ai_ingestion`
- `incidents`
- `incident_classification`
- `evidence`
- `custody`
- `audit`
- `health`
- `cameras`
- `reports`
- `notifications`

Many features use a router/service/repository style.

Security/domain logic should remain outside routers.

## AI engine architecture

The AI engine is a separate FastAPI service with:

- detection contracts
- model registry
- detector adapters
- model lifecycle
- streaming manager
- RTSP source
- frame queue/sampling
- event dispatcher
- backend event sink

The production detector is in:

`ai-engine/models/ultralytics_detector.py`

The project also contains streaming code under:

`ai-engine/streaming/`

## Deployment direction

Docker files and Compose files exist for:

- backend
- frontend
- AI engine
- PostgreSQL
- Redis
- MinIO
- RTSP test environment

The exact active Compose topology must be inspected before assuming every service is currently wired together.

## Architectural documents

Key design references:

- `Architecture Design/`
- `documentation/ai-engine-architecture.md`
- `documentation/api/openapi.yaml`
- `documentation/erd/01-surveillance-platform-erd.mmd`
- `documentation/uml/sequence/08-chain-of-custody.mmd`
- `documentation/detector-contract.md`
- `documentation/model-registration.md`

## Legacy/parallel database tree

`database/` contains a second/older implementation of database models, migrations, and routers.

Do not modify `database/` merely because it exists.

The current active backend implementation is under `backend/`. Treat `database/` as a legacy/parallel foundation until repository evidence establishes otherwise.
