#!/usr/bin/env bash
set -euo pipefail

[[ -f .env ]] || cp .env.example .env
[[ -d .venv ]] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
docker compose up -d postgres redis minio
alembic upgrade head

echo 'Foundation ready. Start with: uvicorn app.main:app --reload'
