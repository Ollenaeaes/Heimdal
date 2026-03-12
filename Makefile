# =============================================================================
# Heimdal Platform — Developer Interface
# =============================================================================
# Run `make help` to see all available targets.
# =============================================================================

.DEFAULT_GOAL := help

# -- Services -----------------------------------------------------------------

up: ## Start all services in the background
	docker compose up -d

down: ## Stop all services
	docker compose down

reset: ## Destroy volumes and rebuild all containers from scratch
	docker compose down -v
	docker compose up -d --build

logs: ## Tail logs for all services
	docker compose logs -f

logs-ingest: ## Tail logs for the AIS ingest service
	docker compose logs -f ais-ingest

logs-scoring: ## Tail logs for the scoring engine
	docker compose logs -f scoring

# -- Database -----------------------------------------------------------------

migrate: ## Run all SQL migrations against the database
	docker compose exec postgres bash -c 'for f in /docker-entrypoint-initdb.d/migrations/*.sql; do psql -U heimdal -d heimdal -f "$$f"; done'

shell-db: ## Open a psql shell to the database
	docker compose exec postgres psql -U heimdal -d heimdal

# -- Enrichment ---------------------------------------------------------------

fetch-sanctions: ## Download/update OpenSanctions data
	docker compose exec enrichment python -m scripts.fetch_sanctions

# -- Testing ------------------------------------------------------------------

test: ## Run the test suite inside the api-server container
	docker compose exec api-server pytest

# -- Utilities ----------------------------------------------------------------

shell-api: ## Open a bash shell in the api-server container
	docker compose exec api-server bash

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: up down reset logs logs-ingest logs-scoring migrate shell-db fetch-sanctions test shell-api help
