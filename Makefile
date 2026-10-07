# Voice Slide Presenter - single entry point.
# Relative paths only: the workspace path contains '&', which breaks absolute-path recipes.

BACKEND  := backend
FRONTEND := frontend
UV       := uv
NPM      := npm
HOST     ?= 127.0.0.1
PORT     ?= 8000
IMAGE    ?= voice-slide-presenter

.DEFAULT_GOAL := help
.PHONY: help install install-ci dev backend frontend build serve test lint fmt check \
        smoke eval sample-pptx check-deps docker-build docker-run clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (uv sync) and frontend (npm ci) dependencies
	cd $(BACKEND) && $(UV) sync
	cd $(FRONTEND) && $(NPM) ci

install-ci: ## Install from lockfiles without updating them (what CI runs)
	cd $(BACKEND) && $(UV) sync --frozen
	cd $(FRONTEND) && $(NPM) ci

dev: ## Run backend (:8000) and Vite dev server (:5173) together
	$(MAKE) -j2 backend frontend

backend: ## Run the FastAPI backend with auto-reload
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

frontend: ## Run the Vite dev server (proxies /api and /ws to :8000)
	cd $(FRONTEND) && $(NPM) run dev

build: ## Build the frontend into frontend/dist
	cd $(FRONTEND) && $(NPM) run build

serve: build ## Build the frontend and serve everything from one port (:8000)
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --host $(HOST) --port $(PORT)

test: ## Run the backend pytest suite
	cd $(BACKEND) && $(UV) run pytest -q

lint: ## ruff check + ruff format --check, then tsc + eslint
	cd $(BACKEND) && $(UV) run ruff check . && $(UV) run ruff format --check .
	cd $(FRONTEND) && $(NPM) run typecheck && $(NPM) run lint

fmt: ## Auto-format backend code and apply safe ruff fixes
	cd $(BACKEND) && $(UV) run ruff check --fix . && $(UV) run ruff format .

check: ## Lint, format check, pytest, and the frontend production build
	@fail=0; \
	$(MAKE) lint || fail=1; \
	$(MAKE) test || fail=1; \
	$(MAKE) build || fail=1; \
	exit $$fail

smoke: ## Connect to the configured realtime provider and wait for the first audio event
	cd $(BACKEND) && $(UV) run python scripts/smoke_realtime.py

eval: ## Run scenario evals against the realtime provider (ARGS="--mode single --case nav-")
	cd $(BACKEND) && $(UV) run python -m evals.run $(ARGS)

sample-pptx: ## Generate backend/samples/sample_deck.pptx for upload testing
	cd $(BACKEND) && $(UV) run python scripts/make_sample_pptx.py

check-deps: ## Check for uv, node/npm and LibreOffice (soffice)
	@command -v $(UV) >/dev/null && echo "ok   uv: $$($(UV) --version)" || echo "MISSING uv (https://docs.astral.sh/uv/)"
	@command -v node >/dev/null && echo "ok   node: $$(node --version)" || echo "MISSING node (>= 20)"
	@command -v $(NPM) >/dev/null && echo "ok   npm: $$($(NPM) --version)" || echo "MISSING npm"
	@if command -v soffice >/dev/null; then \
		if soffice --version >/dev/null 2>&1; then echo "ok   soffice: $$(soffice --version | head -1)"; \
		else echo "WARN soffice is on PATH but fails to run; PPTX uploads will use text-only slides"; fi; \
	else echo "WARN soffice (LibreOffice) not found; PPTX uploads will use text-only slides"; fi
	@test -f .env && echo "ok   .env present" || echo "WARN .env missing: cp .env.example .env and fill in keys"

docker-build: ## Build the Docker image (includes LibreOffice)
	docker build -t $(IMAGE) .

docker-run: ## Run the Docker image on :8000 using .env
	docker run --rm -p $(PORT):8000 --env-file .env $(IMAGE)

clean: ## Remove build output, caches and uploaded decks
	rm -rf $(FRONTEND)/dist $(BACKEND)/storage $(BACKEND)/samples $(BACKEND)/evals/results
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -name __pycache__ -type d -prune -not -path '*/.venv/*' -exec rm -rf {} +
