.PHONY: up down build logs migrate

up:
# 	docker compose -f infra/compose/compose.local.yml up -d

down:
# 	docker compose -f infra/compose/compose.local.yml down

build:
# 	docker compose -f infra/compose/compose.local.yml build

logs:
# 	docker compose -f infra/compose/compose.local.yml logs -f

migrate:
# 	docker compose -f infra/compose/compose.local.yml exec backend python manage.py migrate
