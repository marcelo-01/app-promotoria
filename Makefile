.PHONY: up down logs ps build clean migrate revision seed reset-db shell test \
        prod-up prod-down prod-logs prod-ps prod-seed prod-shell prod-migrate \
        prod-backup prod-restore

# ── Desenvolvimento ────────────────────────────────────────────────────

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

# ── Produção ───────────────────────────────────────────────────────────
# Todo alvo daqui para baixo carrega o docker-compose.prod.yml. Rodar um `make
# migrate` (sem prefixo) no servidor não faz nada de útil: ele fala com o
# compose de desenvolvimento, que lá não existe.

PROD := docker compose -f docker-compose.prod.yml

prod-up:
	$(PROD) up -d --build

prod-down:
	$(PROD) down

prod-logs:
	$(PROD) logs -f

prod-ps:
	$(PROD) ps

# As migrações já rodam sozinhas quando a API sobe; este alvo é para aplicá-las
# sem reiniciar o contêiner.
prod-migrate:
	$(PROD) exec api alembic upgrade head

# Só na primeira subida: cria o tenant e o usuário `admin`. Troque a senha pelo
# menu do próprio app logo depois de entrar.
prod-seed:
	$(PROD) exec api python -m app.scripts.seed

prod-shell:
	$(PROD) exec api /bin/bash

# Banco e fotos, os dois num tar só. O volume do Postgres não é backup: ele mora
# no mesmo disco do servidor e some junto com ele.
# As credenciais são lidas de dentro do contêiner, onde o compose já as colocou —
# o `.env` não chega até aqui, e chutar `estoque` daria um backup vazio no dia em
# que alguém trocar o usuário do banco.
BACKUP_DIR ?= ./backups
prod-backup:
	@mkdir -p $(BACKUP_DIR)
	@STAMP=$$(date +%Y%m%d_%H%M%S); \
	$(PROD) exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' \
	    | gzip > $(BACKUP_DIR)/banco_$$STAMP.sql.gz; \
	$(PROD) exec -T api tar czf - -C /app/uploads . \
	    > $(BACKUP_DIR)/fotos_$$STAMP.tar.gz; \
	echo "Backup gravado em $(BACKUP_DIR)/*_$$STAMP.*"

# Restaura um dump: make prod-restore f=backups/banco_20260810_140000.sql.gz
prod-restore:
	@test -n "$(f)" || (echo "Uso: make prod-restore f=backups/banco_AAAAMMDD_HHMMSS.sql.gz" && exit 1)
	gunzip -c $(f) | $(PROD) exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
