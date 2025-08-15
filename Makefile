APP=ai-backend
DOCKERFILE=legent-ai/image/Dockerfile

# Default target shows help
.DEFAULT_GOAL := help

.PHONY: help build up down logs sh rebuild prod-up prod-down prod-logs

help: ## Show this help
	@echo "Available make targets:" && echo && \
	awk -F':.*##' '/^[a-zA-Z0-9_.-]+:.*##/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build backend image
	docker build -f $(DOCKERFILE) -t $(APP):latest .

rebuild: ## Build image without cache
	docker build --no-cache -f $(DOCKERFILE) -t $(APP):latest .

up: ## Start dev stack with .env (rebuild if needed)
	docker compose --env-file .env up --build

down: ## Stop dev stack
	docker compose --env-file .env down

logs: ## Tail dev logs
	docker compose --env-file .env logs -f --tail=200

sh: ## Shell into backend container (dev)
	docker compose exec backend bash || true

prod-up: build ## Start prod stack with .env.prod
	docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

prod-down: ## Stop prod stack
	docker compose --env-file .env.prod -f docker-compose.prod.yml down

prod-logs: ## Tail prod logs
	docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f --tail=200
