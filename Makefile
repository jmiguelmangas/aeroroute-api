.PHONY: bootstrap format lint typecheck test build contract-verify check
bootstrap:
	uv sync --all-groups
format:
	uv run ruff format src tests scripts
lint:
	uv run ruff check src tests scripts
typecheck:
	uv run mypy
test:
	uv run pytest
build:
	uv build
contract-verify:
	uv run python scripts/validate_openapi_contract.py
check: lint typecheck test build contract-verify
