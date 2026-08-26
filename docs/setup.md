# Local Setup Guide

This guide is intended for local development and portfolio demonstration. It is not a production deployment runbook.

## Prerequisites

Recommended tooling:

- Python 3.12–3.13 for the AI engine
- Docker Desktop
- Git
- PowerShell on Windows

The AI engine declares Python compatibility as `>=3.12,<3.14`.

## 1. Backend

```powershell
cd backend

Copy-Item .env.example .env

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Set local secrets in `backend/.env`. Do not commit that file.

Start supporting infrastructure:

```powershell
docker compose up -d postgres redis minio
```

Run migrations:

```powershell
alembic upgrade head
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

Development API documentation:

```text
http://localhost:8000/docs
```

Health endpoints:

```text
GET /api/v1/health/live
GET /api/v1/health/ready
```

## 2. First administrator

After migrations:

```powershell
python -m scripts.create_admin `
  --email admin@example.com `
  --username administrator `
  --first-name System `
  --last-name Administrator
```

The password is requested interactively and should not be passed as a command-line argument.

## 3. AI engine

```powershell
cd ..\ai-engine

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install the model extra when using the Ultralytics detector:

```powershell
python -m pip install -e ".[dev,model]"
```

The AI engine expects its runtime configuration through environment variables. Use `.env.example` as the starting point and keep local `.env` files untracked.

## 4. Testing

Backend:

```powershell
cd backend
pytest
```

AI engine:

```powershell
cd ..\ai-engine
pytest
```

The AI engine also defines integration and RTSP-oriented test markers. Some tests require the synthetic RTSP environment or additional services.

## 5. Quality checks

AI engine:

```powershell
ruff check .
mypy .
pytest
```

The AI engine project configuration sets a coverage target of 85%.

Backend migrations:

```powershell
alembic check
```

When generating a migration:

```powershell
alembic revision --autogenerate -m "describe change"
```

Always inspect generated migrations manually, especially changes involving PostgreSQL triggers, forensic immutability, partial indexes, and sensitive evidence records.

## 6. Local security checklist

Before committing:

```powershell
git status
git ls-files | Select-String "\.env$|\.key$|\.pem$|\.p12$|\.pfx$|__pycache__|\.pyc$"
```

Expected result: only safe templates such as `.env.example` should be tracked.

Also verify:

```powershell
git check-ignore -v -- backend/.env
git check-ignore -v -- ai-engine/.env
```

## 7. Troubleshooting

### Docker services

```powershell
docker compose ps
docker compose logs postgres
docker compose logs redis
docker compose logs minio
```

### Database

```powershell
alembic current
alembic history
```

### API

Check:

```text
http://localhost:8000/docs
```

and:

```text
GET /api/v1/health/live
GET /api/v1/health/ready
```

### AI engine

Verify the configured model path, Python version, and whether the model extra has been installed.

## Important

This setup is intended to reproduce the development environment. Production deployment requires additional controls for secrets, keys, TLS, observability, network policy, backup/restore, access management, and resilience.
