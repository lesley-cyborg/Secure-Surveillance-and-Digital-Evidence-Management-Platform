.PHONY: install dev up down migrate migration check test lint format typecheck

install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d postgres redis minio

down:
	docker compose down

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(name)"

check:
	alembic check

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy app
