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

# -- IACS Tracker -------------------------------------------------------------

iacs-bootstrap: ## Bootstrap IACS tracker: import all 3 available weekly files
	docker compose --profile batch run --rm iacs-tracker --bootstrap

iacs-update: ## Run IACS tracker: download and import latest weekly file
	docker compose --profile batch run --rm iacs-tracker

iacs-check: ## Check IACS status for a vessel (usage: make iacs-check IMO=9123456)
	docker compose --profile batch run --rm iacs-tracker --check-vessel $(IMO)

iacs-risk: ## List all vessels with Withdrawn/Suspended IACS class
	docker compose --profile batch run --rm iacs-tracker --risk-vessels

iacs-changes: ## Show IACS changes in last 7 days
	docker compose --profile batch run --rm iacs-tracker --recent-changes

# -- Testing ------------------------------------------------------------------

test: ## Run the test suite inside the api-server container
	docker compose exec api-server pytest

# -- Utilities ----------------------------------------------------------------

shell-api: ## Open a bash shell in the api-server container
	docker compose exec api-server bash

# -- Local Dev (with prod data) ------------------------------------------------

dev-up: ## Start local dev stack (no AIS fetcher — use sync-data first)
	docker compose -f docker-compose.dev.yml up -d

dev-rebuild: ## Rebuild and restart only the api-server (preserves DB)
	docker compose -f docker-compose.dev.yml up -d --build --no-deps api-server

dev-down: ## Stop local dev stack
	docker compose -f docker-compose.dev.yml down

sync-data: ## Sync raw AIS data from production (default: last 3 days)
	bash scripts/sync-data.sh $(DAYS)

dev-load: ## Run batch pipeline locally to load synced data
	docker compose -f docker-compose.dev.yml --profile batch run --rm batch-pipeline

dev-logs: ## Tail local dev logs
	docker compose -f docker-compose.dev.yml logs -f

DAYS ?= 3

# -- Oracle Cloud (OCI) -------------------------------------------------------

OCI_STATE := .oci-state.json
OCI_IP = $(shell python3 -c "import json; print(json.load(open('$(OCI_STATE)')).get('public_ip',''))" 2>/dev/null)
OCI_USER ?= root

oci-check: ## Verify OCI CLI is configured and authenticated
	@oci iam region list --output table --query 'data[?name==`eu-stockholm-1`]' && echo "OCI CLI: OK"

oci-provision: ## Provision Oracle Free Tier ARM VM (VCN, subnet, instance)
	bash scripts/oci-provision.sh

oci-setup: ## Install Docker & deps on the Oracle VM (run once after provision)
	ssh -o StrictHostKeyChecking=no $(OCI_USER)@$(OCI_IP) 'bash -s' < scripts/setup-oracle.sh

oci-deploy: ## Deploy AIS fetcher to Oracle VM
	bash scripts/oci-deploy.sh

oci-deploy-full: ## Deploy all services (postgres + ais-fetcher + api-server)
	ssh -o StrictHostKeyChecking=no $(OCI_USER)@$(OCI_IP) \
		"cd ~/Heimdal && git pull origin main && docker compose up -d --build"

oci-ssh: ## SSH into the Oracle VM
	ssh $(OCI_USER)@$(OCI_IP)

oci-logs: ## Tail AIS fetcher logs on Oracle VM
	ssh -o StrictHostKeyChecking=no $(OCI_USER)@$(OCI_IP) \
		"cd ~/Heimdal && docker compose logs -f ais-fetcher"

oci-status: ## Show running containers on Oracle VM
	ssh -o StrictHostKeyChecking=no $(OCI_USER)@$(OCI_IP) \
		"cd ~/Heimdal && docker compose ps"

oci-ip: ## Print the Oracle VM public IP
	@echo $(OCI_IP)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: up down reset logs logs-ingest logs-scoring migrate shell-db fetch-sanctions test shell-api help \
        iacs-bootstrap iacs-update iacs-check iacs-risk iacs-changes \
        dev-up dev-down sync-data dev-load dev-logs \
        oci-check oci-provision oci-setup oci-deploy oci-deploy-full oci-ssh oci-logs oci-status oci-ip
