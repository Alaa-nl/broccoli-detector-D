# Reproducible entrypoints for the BroccoliDetect course project (team B4).
#
# Everything that needs a toolchain runs inside Docker on purpose: the dev
# machines have neither Python 3.11 nor Node installed, so the containers ARE
# the toolchain. The same commands behave identically on any machine with
# Docker and the az CLI.
#
# Run `make` (or `make help`) to list the targets.

# Load the developer's Azure resource names if they created one from
# deploy/azure/azure.env.example. The leading '-' means "skip silently when
# the file doesn't exist", so a fresh clone still works with the defaults.
-include deploy/azure/azure.env

# ?= only assigns when the variable isn't already set, so azure.env (above)
# and the command line (e.g. `make TAG=v2 build`) both win over these.
ACR_NAME       ?= teamb4broccoliacr
RESOURCE_GROUP ?=
CONTAINER_APP  ?= teamb4-broccoli-api
IMAGE          ?= broccoli-detect
TAG            ?= latest
LOCATION       ?= westeurope

# Where the drift script reaches the running app's detect endpoint. It must
# be host.docker.internal because the script runs inside a container, where
# "localhost" would be the script's own container — not the app published on
# the host's port 8080.
DRIFT_API_URL  ?= http://host.docker.internal:8080/api/detect

.DEFAULT_GOAL := help

.PHONY: help test test-backend test-frontend build run acr-login push deploy \
        monitor-up monitor-down drift check-retrain

help: ## Show this help (the default target)
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-15s %s\n", $$1, $$2}'

# ----- tests (run these BEFORE building or deploying anything) ----------------

test: test-backend test-frontend ## Run all tests (backend + frontend)

# Slow (pip resolves torch on every run) but hermetic: the host has no
# Python 3.11, and the container guarantees the same interpreter and wheels
# as the production image and the CI runner.
test-backend: ## Run the backend pytest suite in a python:3.11-slim container
	docker run --rm -v "$(PWD)/backend":/app -w /app python:3.11-slim \
		sh -c "pip install -q -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-dev.txt && python -m pytest -q"

# Same idea for the frontend: the host has no Node, the container does.
test-frontend: ## Run the frontend Vitest suite in a node:20-alpine container
	docker run --rm -v "$(PWD)/frontend":/app -w /app node:20-alpine \
		sh -c "npm ci && npm run test"

# ----- build & run the deployment image ---------------------------------------

# GIT_SHA is baked into the image so /api/metadata and the broccoli_app_info
# metric can report exactly which commit a running container was built from.
build: ## Build the Azure deployment image from Dockerfile.azure
	docker build -f Dockerfile.azure -t $(IMAGE):$(TAG) \
		--build-arg GIT_SHA=$$(git rev-parse --short HEAD) .

# One container serves both halves: nginx delivers the UI on port 80 and
# proxies /api/ to the FastAPI process inside the same container, so a single
# published port covers UI + API.
run: ## Run the deployment image locally; UI + API on http://localhost:8080
	docker run --rm -p 8080:80 --env-file .env $(IMAGE):$(TAG)

# ----- Azure -------------------------------------------------------------------

acr-login: ## Log the local Docker daemon into the team's container registry
	az acr login --name $(ACR_NAME)

push: ## Tag the local image for ACR and push it (run `make acr-login` first)
	docker tag $(IMAGE):$(TAG) $(ACR_NAME).azurecr.io/$(IMAGE):$(TAG)
	docker push $(ACR_NAME).azurecr.io/$(IMAGE):$(TAG)

# Kept as a Make target rather than a CI job on purpose: the course tenant
# does not allow a service principal with rights on the resource group, so
# this last hop is manual. CI pushes the image; a team member runs this.
deploy: ## Point the Azure Container App at the pushed image (manual step)
	@test -n "$(RESOURCE_GROUP)" || { echo "RESOURCE_GROUP is empty - copy deploy/azure/azure.env.example to deploy/azure/azure.env and fill it in"; exit 1; }
	az containerapp update --name $(CONTAINER_APP) --resource-group $(RESOURCE_GROUP) \
		--image $(ACR_NAME).azurecr.io/$(IMAGE):$(TAG)

# ----- monitoring & retraining loop --------------------------------------------

monitor-up: ## Start the local Prometheus + Grafana monitoring stack
	docker compose -f monitoring/docker-compose.monitoring.yml up -d

monitor-down: ## Stop the monitoring stack
	docker compose -f monitoring/docker-compose.monitoring.yml down

# Runs in a container because the host has no Python with Pillow. The
# --add-host flag makes host.docker.internal resolve on plain Linux engines
# too (Docker Desktop on Mac/Windows provides it natively). The app must be
# running on :8080 first (`make run` or `docker compose up`).
drift: ## Send synthetically drifted images at the running app on :8080
	docker run --rm --add-host=host.docker.internal:host-gateway \
		-v "$(PWD)":/repo -w /repo python:3.11-slim \
		sh -c "pip install -q pillow && python scripts/retraining/simulate_drift.py --url $(DRIFT_API_URL)"

# Stdlib-only script, so the host's python3 is enough — no container needed.
# Expects the monitoring stack to be up (`make monitor-up`).
check-retrain: ## Evaluate the retraining triggers against local Prometheus
	python3 scripts/retraining/check_triggers.py --prom-url http://localhost:9090
