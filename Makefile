.PHONY: up down logs ps build clean migrate revision seed reset-db shell test

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

build:
	docker compose build

clean:
	docker compose down -v
	docker system prune -f

reset-db:
	docker compose down -v
	docker compose up -d
	sleep 8
	$(MAKE) migrate
	$(MAKE) seed

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision -m "$(m)"

seed:
	docker compose exec api python -m app.scripts.seed

shell:
	docker compose exec api /bin/bash

test:
	docker compose exec api python -m pytest tests -v
