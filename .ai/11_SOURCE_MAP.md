# Source Map

## Start here

### Backend application

- `backend/app/main.py`
- `backend/app/api/v1/router.py`
- `backend/app/core/`
- `backend/app/db/`

### Authentication/RBAC

- `backend/app/core/security.py`
- `backend/app/modules/auth/`
- `backend/app/modules/rbac/`
- `backend/app/modules/users/`

### AI ingestion

- `backend/app/modules/ai_ingestion/`
- `backend/tests/integration/test_ai_ingestion_api.py`
- `backend/tests/integration/test_ai_ingestion_persistence.py`

### Evidence

- `backend/app/modules/evidence/`
- `backend/app/db/models/evidence.py`
- `backend/tests/unit/test_evidence_*.py`
- `backend/tests/integration/test_evidence_*.py`

### Custody

- `backend/app/modules/custody/integrity.py`
- `backend/app/modules/custody/repository.py`
- `backend/app/modules/custody/service.py`
- `backend/app/modules/custody/router.py`
- `backend/tests/unit/test_custody_integrity.py`
- `backend/tests/integration/test_custody_lifecycle.py`
- `backend/migrations/versions/bf2b79caa708_add_custody_lifecycle_idempotency.py`

### Database

- `backend/app/db/models/`
- `backend/migrations/versions/`

### API contract

- `documentation/api/openapi.yaml`
- `documentation/api/validation-report.json`

### AI engine

- `ai-engine/detection/`
- `ai-engine/models/`
- `ai-engine/streaming/`
- `ai-engine/api/`
- `ai-engine/integrations/backend/`
- `ai-engine/tests/`

### Architecture

- `Architecture Design/`
- `documentation/erd/`
- `documentation/uml/`
- `documentation/ai-engine-architecture.md`

## Avoid accidental edits

Do not assume these are current implementation sources:

- `database/`
- historical `Architecture Design/secure-surveillance-platform-phase3/`
- generated coverage reports
- `.venv/`
- caches
- compiled bytecode
- local `.env`
- `.secrets`
