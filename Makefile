.PHONY: install test lint typecheck verify run pipeline migrate demo

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

demo:
	rm -rf .pages-preview
	mkdir -p .pages-preview/data
	cp -R demo/. .pages-preview/
	cp data/real/openfda_snapshot.json .pages-preview/data/openfda_snapshot.json
	cp data/real/live_ingestion_receipt_2026-08-27.json .pages-preview/data/live_ingestion_receipt.json
	cp data/simulated/sample_account_brief.json .pages-preview/data/sample_account_brief.json
	python3 -m http.server 4173 --directory .pages-preview
