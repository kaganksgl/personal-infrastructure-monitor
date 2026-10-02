# InfraWatch developer tasks. Run `make help` for a list.
SHELL := /bin/bash
VENV ?= .venv
PY := $(VENV)/bin/python
# Docker by default; `make COMPOSE="podman-compose" up` works too.
COMPOSE ?= docker compose
CONTAINER ?= docker
TEST_DB_NAME := infrawatch-test-db
export TEST_DATABASE_URL ?= postgresql+asyncpg://infrawatch:testpass@127.0.0.1:5433/infrawatch_test

.PHONY: help install dev dev-backend dev-frontend dev-agent test test-db test-db-stop \
        test-backend test-agent test-frontend lint format typecheck build up down logs demo clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Create the virtualenv and install all dependencies
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "backend[dev]" -e "agent[dev]" pre-commit
	cd frontend && npm ci

dev: test-db ## Run backend (:8000) and dashboard (:5173) with hot reload
	@echo "Backend on http://localhost:8000/api/docs, dashboard on http://localhost:5173"
	@trap 'kill 0' EXIT; $(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend:
	cd backend && DATABASE_URL=$${DATABASE_URL:-$(TEST_DATABASE_URL:infrawatch_test=infrawatch_dev)} \
		COOKIE_SECURE=false ENVIRONMENT=development \
		../$(VENV)/bin/alembic upgrade head && \
		DATABASE_URL=$${DATABASE_URL:-$(TEST_DATABASE_URL:infrawatch_test=infrawatch_dev)} \
		COOKIE_SECURE=false ENVIRONMENT=development \
		../$(VENV)/bin/uvicorn --factory app.main:create_app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

dev-agent: ## Run the agent against the local backend (needs API_KEY and AGENT_ID)
	cd agent && SERVER_URL=$${SERVER_URL:-http://localhost:8000} LOG_FORMAT=text ../$(PY) -m infrawatch_agent start

test-db: ## Start a disposable PostgreSQL for tests/dev on 127.0.0.1:5433
	@$(CONTAINER) ps --format '{{.Names}}' | grep -qx $(TEST_DB_NAME) || \
		$(CONTAINER) run -d --rm --name $(TEST_DB_NAME) -p 127.0.0.1:5433:5432 \
		-e POSTGRES_USER=infrawatch -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=infrawatch_test \
		docker.io/library/postgres:16-alpine >/dev/null
	@# TCP check: the image's init phase runs a temporary socket-only server.
	@until $(CONTAINER) exec $(TEST_DB_NAME) pg_isready -h 127.0.0.1 -U infrawatch -d infrawatch_test >/dev/null 2>&1; do sleep 1; done
	@$(CONTAINER) exec $(TEST_DB_NAME) psql -U infrawatch -d infrawatch_test -tc \
		"SELECT 1 FROM pg_database WHERE datname='infrawatch_dev'" | grep -q 1 || \
		$(CONTAINER) exec $(TEST_DB_NAME) psql -U infrawatch -d infrawatch_test -qc "CREATE DATABASE infrawatch_dev"

test-db-stop: ## Stop the disposable test database
	-$(CONTAINER) stop $(TEST_DB_NAME)

test: test-db test-backend test-agent test-frontend ## Run every test suite

test-backend:
	cd backend && ../$(VENV)/bin/pytest

test-agent:
	cd agent && ../$(VENV)/bin/pytest

test-frontend:
	cd frontend && npm test

lint: ## Lint Python (ruff) and TypeScript (eslint)
	$(VENV)/bin/ruff check backend agent scripts
	$(VENV)/bin/ruff format --check backend agent
	cd frontend && npm run lint

typecheck: ## Static type checks (mypy + tsc)
	cd backend && ../$(VENV)/bin/mypy app
	cd agent && ../$(VENV)/bin/mypy infrawatch_agent
	cd frontend && npm run typecheck

format: ## Auto-format Python code
	$(VENV)/bin/ruff check --fix backend agent
	$(VENV)/bin/ruff format backend agent

build: ## Build the Docker images
	$(COMPOSE) build

up: ## Start the server stack (docker compose up -d)
	@test -f .env || { echo "Create .env first: cp .env.example .env (and set POSTGRES_PASSWORD)"; exit 1; }
	$(COMPOSE) up -d --build

down: ## Stop the server stack
	$(COMPOSE) down

logs: ## Follow server logs
	$(COMPOSE) logs -f backend

demo: ## Stream a simulated 4-machine fleet (needs INFRAWATCH_USER/PASSWORD)
	$(PY) scripts/demo_fleet.py --server $${SERVER:-http://localhost:8080} --backfill-minutes 120

clean: ## Remove caches and build output
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf frontend/dist .pytest_cache backend/.pytest_cache agent/.pytest_cache .mypy_cache .ruff_cache
