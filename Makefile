.PHONY: help test test-lib test-ha lint format type cli dev-build dev-up dev-down dev-logs dev-restart regen-reading-types clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

test: ## Run all tests
	uv run pytest -x

test-lib: ## Run library tests only
	uv run pytest tests/lib -x

test-ha: ## Run HA integration tests only
	uv run pytest tests/ha -x -m ha

lint: ## Run ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply ruff format
	uv run ruff format .

type: ## Run mypy + pyright
	uv run mypy
	uv run pyright

cli: ## Run the Moj Elektro CLI (pass ARGS="info 4-xxx")
	uv run python -m cli $(ARGS)

dev-build: ## Rebuild the HA dev image (rarely needed)
	docker compose -f docker/compose.yaml build homeassistant

dev-up: ## Start docker compose dev stack (HA at :8123, InfluxDB at :8086)
	docker compose -f docker/compose.yaml up -d

dev-down: ## Stop docker compose dev stack
	docker compose -f docker/compose.yaml down

dev-logs: ## Tail HA logs
	docker compose -f docker/compose.yaml logs -f homeassistant

dev-restart: ## Restart HA (picks up custom_components edits without a rebuild)
	docker compose -f docker/compose.yaml restart homeassistant

regen-reading-types: ## Regenerate reading_types.py from the catalog cassette
	uv run python scripts/regen-reading-types.py
	uv run ruff format custom_components/mojelektro_stats/lib/mojelektro_api/reading_types.py

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build *.egg-info
