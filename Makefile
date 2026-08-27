.PHONY: install test lint typecheck verify run pipeline migrate

install:
	python3.12 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'

test:
	.venv/bin/pytest --cov=src/revenue_agent --cov-report=term-missing

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy src

verify: lint typecheck test

run:
	.venv/bin/uvicorn revenue_agent.main:app --reload

pipeline:
	AUTO_CREATE_SCHEMA=true DATABASE_URL=sqlite:///./revenue_agent.db .venv/bin/revenue-agent pipeline

migrate:
	.venv/bin/alembic upgrade head
