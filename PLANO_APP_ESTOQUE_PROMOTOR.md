# App de Coleta de Estoque do Promotor — Plano de Arquitetura e Código

> Documento de referência para construir o app **standalone** de coleta de estoque
> (`fv-estoque`), projetado para ser incorporado ao ERP `fv-laticinios` no futuro
> com o menor custo possível de fusão.
>
> Gerado a partir da análise completa do código do ERP em desenvolvimento.
> Data: 2026-08-05.

---

## Índice

1. [Contexto e decisão de arquitetura](#1-contexto-e-decisão-de-arquitetura)
2. [Topologia dos dois projetos](#2-topologia-dos-dois-projetos)
3. [As 6 âncoras que tornam a fusão barata](#3-as-6-âncoras-que-tornam-a-fusão-barata)
4. [Estrutura de pastas do novo repo](#4-estrutura-de-pastas-do-novo-repo)
5. [Arquivos copiados verbatim do ERP](#5-arquivos-copiados-verbatim-do-erp)
6. [Infraestrutura: Docker, env, Makefile](#6-infraestrutura-docker-env-makefile)
7. [Backend — núcleo](#7-backend--núcleo)
8. [Backend — models](#8-backend--models)
9. [Backend — migração inicial (Alembic)](#9-backend--migração-inicial-alembic)
10. [Backend — autenticação](#10-backend--autenticação)
11. [Backend — módulo merchandising](#11-backend--módulo-merchandising)
12. [Backend — cadastros de clientes e produtos](#12-backend--cadastros-de-clientes-e-produtos)
13. [Backend — main.py e seed](#13-backend--mainpy-e-seed)
14. [Frontend — configuração](#14-frontend--configuração)
15. [Frontend — API, stores e fila offline](#15-frontend--api-stores-e-fila-offline)
16. [Frontend — rotas e layouts](#16-frontend--rotas-e-layouts)
17. [Frontend — telas do promotor](#17-frontend--telas-do-promotor)
18. [Frontend — telas do administrador](#18-frontend--telas-do-administrador)
19. [Contrato completo da API](#19-contrato-completo-da-api)
20. [Playbook da fusão com o ERP](#20-playbook-da-fusão-com-o-erp)
21. [Roadmap de execução](#21-roadmap-de-execução)
22. [Riscos e divergências deliberadas](#22-riscos-e-divergências-deliberadas)

---

## 1. Contexto e decisão de arquitetura

### O problema

O ERP `fv-laticinios` está em desenvolvimento e ainda não entrou em produção. A coleta
de estoque em ponto de venda (feita por promotores) precisa entrar em uso **antes**
disso. Esperar o ERP ficar pronto é o maior risco de cronograma do projeto.

### A decisão

Construir um aplicativo **completamente separado** — repositório, banco de dados,
containers e deploy próprios — mas usando **exatamente a mesma stack e as mesmas
convenções** do ERP.

Isso não é contradição. O que torna uma fusão cara não é o app ser separado: é ele
inventar identidade própria (outra stack, outro schema, outro formato de token, outras
convenções). Mantendo a stack idêntica, o dia da fusão vira "copiar duas pastas +
migrar dados", e não uma reescrita.

### O que muda por ser standalone

A mudança central: **o app precisa do cadastro próprio de clientes e produtos**. No ERP,
esses dados viriam do Firebird via o gateway de integração. Aqui, entram pelo
**cadastro manual** feito pelo administrador, na tela de Cadastros. Não há importação
de cadastros por planilha: a planilha do ERP que o app lê é a de faturamento, e ela
só casa com clientes e produtos que já existem aqui.

### Stack — idêntica ao ERP

| Camada | Tecnologia | Observação |
|---|---|---|
| API | FastAPI | mesmo padrão `routes → service → repository` |
| ORM | SQLAlchemy 2.0 async + asyncpg | mesmas `base.py` / `session.py` |
| Migrações | Alembic | numeração própria, começa em `001` |
| Banco | PostgreSQL 16 | instância própria, porta 5434 |
| Validação | Pydantic v2 + pydantic-settings | `model_config = {"from_attributes": True}` |
| Auth | JWT (python-jose) + bcrypt | **mesmo formato de claims** do ERP |
| App | Vue 3 + Quasar 2 + Pinia + Vite | PWA instalável, sem loja de apps |
| Excel | **openpyxl** | única dependência nova (lê e escreve) |

### O que foi deliberadamente cortado do MVP

Nada disto entra no app standalone: **Redis, Celery, Firebird, gateway de integração,
tabelas de preço, pedidos, roteirização, filiais, SMTP por tenant, dashboard**. São
3 containers apenas (`db`, `api`, `web`) e o `Dockerfile` do backend não precisa do
`libfbclient2`.

---

## 2. Topologia dos dois projetos

```
PROJETOS/
├── fv-laticinios/          ← ERP em desenvolvimento (NÃO TOCAR)
└── fv-estoque/             ← NOVO: repo, banco, containers e deploy próprios
```

Portas separadas para os dois subirem na mesma máquina sem conflito:

| Serviço | ERP (`fv-laticinios`) | Novo app (`fv-estoque`) |
|---|---|---|
| PostgreSQL | 5433 | **5434** |
| API | 8001 | **8002** |
| Web (dev) | 5173 | **5174** |
| Redis | 6380 | — (não usa) |
| Firebird | 3050 | — (não usa) |

Os dois projetos **não se comunicam**. Nenhuma chamada de rede, nenhum banco
compartilhado, nenhuma dependência de código em tempo de execução. O único vínculo é
de convenção — e é esse vínculo que a seção 3 protege.

---

## 3. As 6 âncoras que tornam a fusão barata

Estas seis regras são o coração do documento. Cada uma custa pouco agora e economiza
semanas depois. Se algo tiver que ser sacrificado por prazo, **não seja uma destas**.

### Âncora 1 — Copie a fundação verbatim

Os arquivos de infraestrutura (base do ORM, sessão, segurança, dependências, auth,
client HTTP, stores de auth) vão do ERP para o novo repo **sem uma linha alterada**.
É o que garante que o código do módulo seja literalmente colável depois. Lista completa
na [seção 5](#5-arquivos-copiados-verbatim-do-erp).

### Âncora 2 — `tenant_id` em toda tabela, desde o primeiro dia

Sim, é uma empresa só. Faça um seed com um tenant fixo e filtre em toda query mesmo
assim.

- **Custo agora:** uma coluna por tabela e um `where` por query.
- **Custo de adicionar depois:** migração + backfill + revisar **toda** query, todo
  service e toda assinatura de repository.

É o item de melhor custo-benefício da lista. O ERP inteiro é multi-tenant; um app que
não é não se encaixa nele.

### Âncora 3 — UUID como PK, sempre

```python
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
```

IDs sequenciais colidem na fusão (o cliente `42` do app é outro cliente `42` no ERP).
UUIDs não colidem — os registros entram no banco do ERP mantendo o mesmo ID que já
tinham, o que preserva todas as referências.

### Âncora 4 — Chave de negócio natural em cliente e produto

É isto que vai casar os dois cadastros no dia da integração:

| Entidade | Chave natural | Regra |
|---|---|---|
| Cliente | `document` | CNPJ/CPF **só dígitos**, normalizado na entrada |
| Produto | `sku` e `barcode` | SKU do fabricante e EAN-13 |
| Usuário | `email` | minúsculo, normalizado |

Além disso, ambas as tabelas nascem com `external_id String(255) nullable`, vazio agora.
Quando o ERP entrar no ar, esse campo recebe o ID do Firebird e o casamento fica
explícito, não inferido.

**Sem isso, a fusão vira reconciliação manual, cliente por cliente. Com isso, é um
`UPDATE ... FROM` com `JOIN ON document`.**

### Âncora 5 — Nomes e tipos idênticos aos do ERP

Tabelas `tenants`, `users`, `customers`, `products` com as mesmas colunas essenciais e
os mesmos tipos:

- `Numeric(15, 3)` para quantidade/estoque
- `Numeric(15, 2)` para valores monetários
- `FlexibleJSON` para `address`, com as chaves
  `zip_code, street, number, complement, neighborhood, city, state`
- `String(20)` para `document`, `String(50)` para `sku`, `String(30)` para `barcode`

**Não "melhore" o schema.** Divergência aqui é dívida que se paga na fusão. Colunas
*extras* são aceitáveis (não quebram nada); colunas *faltantes* ou *renomeadas* quebram.

### Âncora 6 — Prefixo `/merchandising` na API desde já

Mesmo sendo um app só, use o prefixo em todas as rotas do domínio de coleta. No dia da
fusão, o frontend não muda uma linha de URL, e não há colisão com nenhuma rota existente
do ERP (`/customers`, `/products`, `/sales-routes`, `/sellers`, `/auth`...).

---

## 4. Estrutura de pastas do novo repo

```
fv-estoque/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.prod.yml
├── Makefile
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial.py
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py            # adaptado (sem redis/celery/firebird)
│       │   ├── security.py          # ← VERBATIM do ERP
│       │   └── dependencies.py      # ← VERBATIM do ERP
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── routes.py            # adaptado (sem forgot/reset no MVP)
│       │   ├── schemas.py           # ← VERBATIM do ERP
│       │   └── service.py           # adaptado (sem EmailService)
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   └── persistence/
│       │       ├── __init__.py
│       │       ├── base.py          # ← VERBATIM do ERP
│       │       ├── session.py       # ← VERBATIM do ERP
│       │       ├── types.py         # ← VERBATIM do ERP
│       │       └── models/
│       │           ├── __init__.py
│       │           ├── tenant.py
│       │           ├── user.py
│       │           ├── customer.py
│       │           ├── product.py
│       │           ├── promoter_customer.py
│       │           ├── customer_product.py
│       │           └── stock_visit.py
│       ├── customers/               # cadastro temporário (morre na fusão)
│       │   ├── __init__.py
│       │   ├── routes.py
│       │   ├── service.py
│       │   ├── repository.py
│       │   └── schemas.py
│       ├── products/                # cadastro temporário (morre na fusão)
│       │   └── (mesma estrutura)
│       ├── merchandising/           # ← O CORAÇÃO. Migra inteiro para o ERP.
│       │   ├── __init__.py
│       │   ├── routes.py
│       │   ├── service.py
│       │   ├── repository.py
│       │   ├── schemas.py
│       │   └── excel.py             # exportação .xlsx
│       └── scripts/
│           ├── __init__.py
│           └── seed.py
└── frontend/
    ├── Dockerfile
    ├── Dockerfile.prod
    ├── nginx.prod.conf
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js
        ├── App.vue
        ├── api/
        │   ├── client.js            # ← VERBATIM do ERP (só muda a porta)
        │   ├── merchandising.js
        │   ├── customers.js
        │   └── products.js
        ├── stores/
        │   ├── auth.js              # ← VERBATIM do ERP
        │   ├── user.js              # ← VERBATIM do ERP
        │   └── visita.js            # rascunho da contagem + fila offline
        ├── composables/
        │   └── useOfflineQueue.js
        ├── router/
        │   └── index.js
        ├── layouts/
        │   ├── PromotorLayout.vue   # mobile, bottom nav, sem sidebar
        │   └── AdminLayout.vue
        └── pages/
            ├── LoginPage.vue
            ├── promotor/
            │   ├── PromotorClientesPage.vue
            │   ├── PromotorProdutosPage.vue
            │   ├── PromotorContagemPage.vue
            │   └── PromotorEnviosPage.vue
            └── admin/
                ├── AdminVisitasPage.vue
                ├── AdminVinculosPage.vue
                └── AdminCadastrosPage.vue
```

### A regra de ouro da organização

**Toda lógica de coleta de estoque vive em `app/merchandising/` e `pages/promotor/`.**

Nada de regra de negócio do promotor espalhada em `customers/` ou `products/` — esses
dois são cadastros temporários que morrem na fusão. Se a fronteira estiver limpa, o dia
da fusão é copiar duas pastas.

---

## 5. Arquivos copiados verbatim do ERP

Copie estes arquivos **sem alterar uma linha**. O caminho de origem é relativo a
`fv-laticinios/`, o de destino a `fv-estoque/`.

| Origem (ERP) | Destino (novo app) | Alteração |
|---|---|---|
| `backend/app/infrastructure/persistence/base.py` | idem | nenhuma |
| `backend/app/infrastructure/persistence/session.py` | idem | nenhuma |
| `backend/app/infrastructure/persistence/types.py` | idem | nenhuma |
| `backend/app/core/security.py` | idem | nenhuma |
| `backend/app/core/dependencies.py` | idem | nenhuma |
| `backend/app/auth/schemas.py` | idem | nenhuma |
| `backend/alembic/env.py` | idem | trocar defaults de `sfauser`/`sfa_db` |
| `frontend/src/api/client.js` | idem | trocar porta `8001` → `8002` |
| `frontend/src/stores/auth.js` | idem | nenhuma |
| `frontend/src/stores/user.js` | idem | nenhuma |
| `frontend/src/App.vue` | idem | nenhuma |

Comando prático (ajuste os caminhos):

```bash
cd ~/"Área de trabalho"/PROJETOS
SRC=fv-laticinios
DST=fv-estoque

mkdir -p $DST/backend/app/{core,auth,scripts,customers,products,merchandising}
mkdir -p $DST/backend/app/infrastructure/persistence/models
mkdir -p $DST/backend/alembic/versions
mkdir -p $DST/frontend/src/{api,stores,composables,router,layouts}
mkdir -p $DST/frontend/src/pages/{promotor,admin}

cp $SRC/backend/app/infrastructure/persistence/{base,session,types}.py \
   $DST/backend/app/infrastructure/persistence/
cp $SRC/backend/app/core/{security,dependencies}.py $DST/backend/app/core/
cp $SRC/backend/app/auth/schemas.py                 $DST/backend/app/auth/
cp $SRC/backend/alembic/env.py                      $DST/backend/alembic/
cp $SRC/frontend/src/api/client.js                  $DST/frontend/src/api/
cp $SRC/frontend/src/stores/{auth,user}.js          $DST/frontend/src/stores/
cp $SRC/frontend/src/App.vue                        $DST/frontend/src/

# arquivos __init__.py vazios
find $DST/backend/app -type d -exec touch {}/__init__.py \;
```

> **Por que `dependencies.py` vai verbatim mesmo dependendo de `Tenant`?**
> Porque o novo app terá a tabela `tenants` com o mesmo schema (Âncora 2/5). O arquivo
> funciona sem adaptação, e no dia da fusão não há divergência para reconciliar.

---

## 6. Infraestrutura: Docker, env, Makefile

### `fv-estoque/.env.example`

```bash
# ── Banco ──────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://estoque:estoque@db:5432/estoque_db
DATABASE_USER=estoque
DATABASE_PASSWORD=estoque
DATABASE_NAME=estoque_db
DATABASE_HOST=db
DATABASE_PORT=5432

POSTGRES_USER=estoque
POSTGRES_PASSWORD=estoque
POSTGRES_DB=estoque_db

# ── API ────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
API_ENV=development

# Em produção, gere com: openssl rand -hex 32
SECRET_KEY=dev-secret-key-change-in-production
ALGORITHM=HS256
# 8 horas — cobre uma jornada de campo inteira sem reautenticar
ACCESS_TOKEN_EXPIRE_MINUTES=480
REFRESH_TOKEN_EXPIRE_DAYS=30

FRONTEND_URL=http://localhost:5174
```

### `fv-estoque/.gitignore`

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
.env
node_modules/
dist/
dev-dist/
.DS_Store
*.log
htmlcov/
.pytest_cache/
.coverage
```

### `fv-estoque/docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    container_name: estoque_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5434:5432"          # 5433 é do ERP — não colidir
    volumes:
      - estoque_pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - estoque_network

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: estoque_api
    environment:
      DATABASE_URL: ${DATABASE_URL}
      DATABASE_HOST: ${DATABASE_HOST}
      DATABASE_PORT: ${DATABASE_PORT}
      DATABASE_USER: ${DATABASE_USER}
      DATABASE_PASSWORD: ${DATABASE_PASSWORD}
      DATABASE_NAME: ${DATABASE_NAME}
      API_HOST: ${API_HOST}
      API_PORT: ${API_PORT}
      API_ENV: ${API_ENV}
      SECRET_KEY: ${SECRET_KEY}
      ACCESS_TOKEN_EXPIRE_MINUTES: ${ACCESS_TOKEN_EXPIRE_MINUTES}
      REFRESH_TOKEN_EXPIRE_DAYS: ${REFRESH_TOKEN_EXPIRE_DAYS}
      FRONTEND_URL: ${FRONTEND_URL}
    ports:
      - "8002:8000"          # 8001 é do ERP
    volumes:
      - ./backend:/app
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - estoque_network
    command: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: estoque_web
    ports:
      - "5174:5174"          # 5173 é do ERP
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      api:
        condition: service_healthy
    networks:
      - estoque_network

volumes:
  estoque_pg_data:
    driver: local

networks:
  estoque_network:
    driver: bridge
```

### `fv-estoque/backend/Dockerfile`

Enxuto — sem `libfbclient2`, que só existe no ERP por causa do Firebird:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `fv-estoque/backend/requirements.txt`

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
pydantic[email]>=2.0.0
pydantic-settings>=2.0.0
sqlalchemy>=2.0.0
alembic>=1.12.0
asyncpg>=0.29.0
psycopg2-binary>=2.9.0
bcrypt>=4.1.0
python-jose[cryptography]>=3.3.0
python-multipart>=0.0.6
python-dotenv>=1.0.0
# Leitura e escrita de planilhas .xlsx — única dependência nova em relação ao ERP
openpyxl>=3.1.0
# Testes
pytest>=7.4.0
pytest-asyncio>=0.21.0
httpx>=0.25.0
aiosqlite>=0.19.0
```

### `fv-estoque/Makefile`

```makefile
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
```

### `fv-estoque/backend/alembic.ini`

```ini
[alembic]
script_location = alembic
# a URL real é montada em alembic/env.py a partir das variáveis de ambiente
sqlalchemy.url = postgresql+psycopg2://estoque:estoque@db:5432/estoque_db

[loggers]
keys = root,sqlalchemy.engine

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy.engine]
level = WARN
handlers =
qualname = sqlalchemy.engine

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

### `fv-estoque/backend/alembic/env.py`

Copiado do ERP, mudando apenas os *defaults*. **Importante:** o `import` do pacote de
models no final é o que faz o `--autogenerate` enxergar as tabelas.

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.append(str(Path(__file__).resolve().parents[1]))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_sqlalchemy_url():
    user = os.getenv("DATABASE_USER", "estoque")
    password = os.getenv("DATABASE_PASSWORD", "estoque")
    host = os.getenv("DATABASE_HOST", "db")
    port = os.getenv("DATABASE_PORT", "5432")
    db = os.getenv("DATABASE_NAME", "estoque_db")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


config.set_main_option("sqlalchemy.url", get_sqlalchemy_url())

from app.infrastructure.persistence.base import DeclarativeBase
from app.infrastructure.persistence import models  # noqa: F401  (registra as tabelas)

target_metadata = DeclarativeBase.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_sqlalchemy_url()

    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## 7. Backend — núcleo

### `backend/app/core/config.py`

Adaptado: sem Redis, Celery, Firebird e SMTP.

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    database_host: str = "db"
    database_port: int = 5432
    database_user: str = "estoque"
    database_password: str = "estoque"
    database_name: str = "estoque_db"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_env: str = "development"

    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    # 8h: o promotor passa o dia em campo e não pode ser deslogado no meio da rota
    access_token_expire_minutes: int = 480
    refresh_token_expire_days: int = 30

    frontend_url: str = "http://localhost:5174"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

### `backend/app/core/security.py` — VERBATIM

Copiado sem alteração de `fv-laticinios/backend/app/core/security.py`. Exporta
`hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`,
`verify_token`.

### `backend/app/core/dependencies.py` — VERBATIM

Copiado sem alteração de `fv-laticinios/backend/app/core/dependencies.py`. Exporta
`get_current_user`, `get_current_user_and_tenant` e a factory `require_roles(*roles)`.

Uso nas rotas — exatamente como no ERP:

```python
context: dict = Depends(require_roles("admin"))          # só admin
context: dict = Depends(require_roles("promoter", "admin"))
current_user: User = Depends(get_current_user)           # qualquer autenticado
```

---

## 8. Backend — models

Sete tabelas. As quatro primeiras são espelhos do schema do ERP (Âncora 5); as três
últimas são novas e migram inteiras na fusão.

### `models/__init__.py`

```python
"""Importa todos os models para que o Alembic e o SQLAlchemy os registrem."""
from app.infrastructure.persistence.models.tenant import Tenant, TenantStatus  # noqa: F401
from app.infrastructure.persistence.models.user import User, UserRole  # noqa: F401
from app.infrastructure.persistence.models.customer import Customer, CustomerStatus  # noqa: F401
from app.infrastructure.persistence.models.product import Product  # noqa: F401
from app.infrastructure.persistence.models.promoter_customer import PromoterCustomer  # noqa: F401
from app.infrastructure.persistence.models.customer_product import CustomerProduct  # noqa: F401
from app.infrastructure.persistence.models.stock_visit import (  # noqa: F401
    StockVisit,
    StockVisitItem,
    StockVisitStatus,
)
```

### `models/tenant.py`

Cópia reduzida do ERP — mesmas colunas essenciais.

```python
import enum
from uuid import uuid4

from sqlalchemy import Column, String, Enum as SQLEnum
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Tenant(DeclarativeBase, TimestampMixin):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(
        SQLEnum(TenantStatus, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        default=TenantStatus.ACTIVE,
        nullable=False,
    )
    slug = Column(String(100), nullable=True, unique=True, index=True)
```

### `models/user.py`

O enum `UserRole` nasce com **os mesmos valores do ERP + `promoter`**. Assim, no dia da
fusão, a única mudança do lado do ERP é um `ALTER TYPE userrole ADD VALUE 'promoter'`,
e todos os usuários migrados encaixam.

```python
import enum
from uuid import uuid4

from sqlalchemy import Column, String, Text, Boolean, Enum as SQLEnum, ForeignKey, Index, func, text
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"   # não usado no MVP; mantido por compatibilidade com o ERP
    SELLER = "seller"           # não usado no MVP; mantido por compatibilidade com o ERP
    PROMOTER = "promoter"       # NOVO — o papel deste app


class User(DeclarativeBase, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    role = Column(
        SQLEnum(UserRole, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        default=UserRole.PROMOTER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    avatar_url = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_users_tenant_email", "tenant_id", "email"),
        Index("idx_users_email_lower", func.lower(text("email"))),
    )
```

> **Atenção Postgres:** um valor recém-adicionado a um `ENUM` não pode ser *usado* na
> mesma migração que o adiciona. Como aqui o enum nasce completo em `001_initial`, o
> problema não existe. Ele só aparece do lado do ERP, na fusão — por isso o playbook
> separa a migração de enum da migração de dados.

### `models/customer.py`

Subconjunto do `Customer` do ERP, mantendo nomes e tipos idênticos, **mais**
`external_id` (Âncora 4).

```python
import enum
from uuid import uuid4

from sqlalchemy import Column, String, ForeignKey, Index, Enum as SQLEnum, Text
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin
from app.infrastructure.persistence.types import FlexibleJSON


class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Customer(DeclarativeBase, TimestampMixin):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # ── Chave de casamento com o ERP (Âncora 4) ───────────────────────────
    # CNPJ/CPF somente dígitos. É por aqui que os cadastros serão unificados.
    document = Column(String(20), nullable=True)
    # Preenchido apenas no dia da integração, com o ID vindo do Firebird.
    external_id = Column(String(255), nullable=True)

    name = Column(String(255), nullable=False)            # nome fantasia
    corporate_name = Column(String(255), nullable=True)   # razão social
    state_registration = Column(String(50), nullable=True)

    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)

    status = Column(
        SQLEnum(CustomerStatus, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        default=CustomerStatus.ACTIVE,
        nullable=False,
    )

    # Mesmas chaves do ERP:
    # zip_code, street, number, complement, neighborhood, city, state
    address = Column(FlexibleJSON, nullable=True)

    # varejo | food_service | industria | atacado
    customer_type = Column(String(30), nullable=True)
    logistics_notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_customers_tenant_id", "tenant_id"),
        Index("idx_customers_tenant_document", "tenant_id", "document"),
        Index("idx_customers_tenant_external", "tenant_id", "external_id"),
    )
```

### `models/product.py`

```python
from uuid import uuid4

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Index, Numeric
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class Product(DeclarativeBase, TimestampMixin):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # ── Chaves de casamento com o ERP (Âncora 4) ──────────────────────────
    sku = Column(String(50), nullable=False)
    barcode = Column(String(30), nullable=True)           # EAN-13
    external_id = Column(String(255), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    category = Column(String(50), nullable=True)

    unit = Column(String(10), default="UN", nullable=False)
    price = Column(Numeric(15, 2), nullable=False, default=0)
    # quantas unidades por caixa/fardo — o promotor às vezes conta em caixas
    package_size = Column(Numeric(10, 3), nullable=True, default=1)

    is_perishable = Column(Boolean, default=True, nullable=False)
    shelf_life_days = Column(Integer, nullable=True)

    image_url = Column(String(512), nullable=True)

    # DIVERGÊNCIA DELIBERADA: o ERP não tem esta coluna (ver seção 22).
    is_active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("idx_products_tenant_id", "tenant_id"),
        Index("idx_products_tenant_sku", "tenant_id", "sku"),
        Index("idx_products_tenant_barcode", "tenant_id", "barcode"),
    )
```

### `models/promoter_customer.py`

O vínculo "quais clientes cada promotor atende". No ERP isso é `seller_customers`
(via `sellers`); aqui aponta direto para `users`, porque não existe tabela `sellers`.
A conversão está no playbook da fusão (seção 20).

```python
from uuid import uuid4

from sqlalchemy import Boolean, Column, ForeignKey, Index, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class PromoterCustomer(DeclarativeBase, TimestampMixin):
    """Quais clientes cada promotor atende. Definido pelo administrador."""

    __tablename__ = "promoter_customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "customer_id", name="uq_promoter_customers"),
        Index("idx_promoter_customers_user", "tenant_id", "user_id"),
        Index("idx_promoter_customers_customer", "tenant_id", "customer_id"),
    )
```

### `models/customer_product.py`

O **mix de gôndola**: quais produtos o promotor conta naquele cliente, e em que ordem.
É o que faz a tela ser rápida de usar — o promotor vê os 15 itens daquele ponto de
venda, não os 400 do catálogo. Sem vínculo cadastrado, o app cai no catálogo completo.

```python
from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class CustomerProduct(DeclarativeBase, TimestampMixin):
    """Mix de produtos contados em um cliente ('planograma' simplificado)."""

    __tablename__ = "customer_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    # ordem de contagem na gôndola — o promotor conta de cima para baixo
    position = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", "product_id", name="uq_customer_products"),
        Index("idx_customer_products_customer", "tenant_id", "customer_id"),
    )
```

### `models/stock_visit.py`

O modelo central do app.

```python
import enum
from uuid import uuid4

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class StockVisitStatus(str, enum.Enum):
    DRAFT = "draft"           # rascunho, ainda em digitação
    SUBMITTED = "submitted"   # enviado pelo promotor
    EXPORTED = "exported"     # já baixado em planilha pelo administrador


class StockVisit(DeclarativeBase, TimestampMixin):
    """Contagem de estoque feita por um promotor em um cliente."""

    __tablename__ = "stock_visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    promoter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # String e não Enum nativo: mesmo padrão de `orders.order_status` no ERP,
    # que evita ALTER TYPE a cada novo status.
    status = Column(String(20), nullable=False, default=StockVisitStatus.DRAFT.value)

    visited_at = Column(DateTime(timezone=True), nullable=True)    # data real da contagem
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    exported_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    # UUID gerado no celular (crypto.randomUUID()). Torna o reenvio idempotente:
    # se o app enviar duas vezes por falha de rede, faz UPDATE em vez de duplicar.
    client_uuid = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "client_uuid", name="uq_stock_visits_client_uuid"),
        Index("idx_stock_visits_tenant_id", "tenant_id"),
        Index("idx_stock_visits_tenant_customer", "tenant_id", "customer_id"),
        Index("idx_stock_visits_tenant_promoter", "tenant_id", "promoter_id"),
        Index("idx_stock_visits_tenant_status", "tenant_id", "status"),
        Index("idx_stock_visits_submitted_at", "tenant_id", "submitted_at"),
    )


class StockVisitItem(DeclarativeBase, TimestampMixin):
    """Uma linha de contagem: produto + quantidade encontrada."""

    __tablename__ = "stock_visit_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("stock_visits.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)

    # Numeric(15,3): mesmo tipo de products.stock e order_items.quantity no ERP
    quantity = Column(Numeric(15, 3), nullable=False, default=0)
    # Laticínio é perecível — validade é informação de negócio, não detalhe
    expires_at = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("visit_id", "product_id", name="uq_stock_visit_item"),
        Index("idx_stock_visit_items_visit_id", "visit_id"),
        Index("idx_stock_visit_items_tenant_product", "tenant_id", "product_id"),
    )
```

**Por que `client_uuid` importa tanto:** o promotor conta 40 produtos numa gôndola de
supermercado com sinal ruim. Ele aperta "Enviar", o POST expira, o app reenvia. Sem a
constraint de unicidade, isso vira duas visitas duplicadas na planilha do administrador.

---

## 9. Backend — migração inicial (Alembic)

### `backend/alembic/versions/001_initial.py`

```python
"""Schema inicial do app de coleta de estoque.

Revision ID: 001_initial
Revises:
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tenants ────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.Enum("active", "inactive", name="tenantstatus"),
                  nullable=False, server_default="active"),
        sa.Column("slug", sa.String(100), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"])

    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        # enum nasce completo — inclui os papéis do ERP + promoter
        sa.Column("role",
                  sa.Enum("admin", "supervisor", "seller", "promoter", name="userrole"),
                  nullable=False, server_default="promoter"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_tenant_email", "users", ["tenant_id", "email"])
    op.execute("CREATE INDEX idx_users_email_lower ON users (lower(email))")

    # ── customers ──────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document", sa.String(20), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("corporate_name", sa.String(255), nullable=True),
        sa.Column("state_registration", sa.String(50), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("active", "inactive", name="customerstatus"),
                  nullable=False, server_default="active"),
        sa.Column("address", sa.JSON(), nullable=True),
        sa.Column("customer_type", sa.String(30), nullable=True),
        sa.Column("logistics_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_customers_tenant_id", "customers", ["tenant_id"])
    op.create_index("idx_customers_tenant_document", "customers", ["tenant_id", "document"])
    op.create_index("idx_customers_tenant_external", "customers", ["tenant_id", "external_id"])

    # ── products ───────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sku", sa.String(50), nullable=False),
        sa.Column("barcode", sa.String(30), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("unit", sa.String(10), nullable=False, server_default="UN"),
        sa.Column("price", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("package_size", sa.Numeric(10, 3), nullable=True, server_default="1"),
        sa.Column("is_perishable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("shelf_life_days", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_products_tenant_id", "products", ["tenant_id"])
    op.create_index("idx_products_tenant_sku", "products", ["tenant_id", "sku"])
    op.create_index("idx_products_tenant_barcode", "products", ["tenant_id", "barcode"])

    # ── promoter_customers ─────────────────────────────────────────────────
    op.create_table(
        "promoter_customers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "user_id", "customer_id", name="uq_promoter_customers"),
    )
    op.create_index("idx_promoter_customers_user", "promoter_customers", ["tenant_id", "user_id"])
    op.create_index("idx_promoter_customers_customer", "promoter_customers", ["tenant_id", "customer_id"])

    # ── customer_products ──────────────────────────────────────────────────
    op.create_table(
        "customer_products",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "customer_id", "product_id", name="uq_customer_products"),
    )
    op.create_index("idx_customer_products_customer", "customer_products", ["tenant_id", "customer_id"])

    # ── stock_visits ───────────────────────────────────────────────────────
    op.create_table(
        "stock_visits",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("promoter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("visited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("client_uuid", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "client_uuid", name="uq_stock_visits_client_uuid"),
    )
    op.create_index("idx_stock_visits_tenant_id", "stock_visits", ["tenant_id"])
    op.create_index("idx_stock_visits_tenant_customer", "stock_visits", ["tenant_id", "customer_id"])
    op.create_index("idx_stock_visits_tenant_promoter", "stock_visits", ["tenant_id", "promoter_id"])
    op.create_index("idx_stock_visits_tenant_status", "stock_visits", ["tenant_id", "status"])
    op.create_index("idx_stock_visits_submitted_at", "stock_visits", ["tenant_id", "submitted_at"])

    # ── stock_visit_items ──────────────────────────────────────────────────
    op.create_table(
        "stock_visit_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("visit_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stock_visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("visit_id", "product_id", name="uq_stock_visit_item"),
    )
    op.create_index("idx_stock_visit_items_visit_id", "stock_visit_items", ["visit_id"])
    op.create_index("idx_stock_visit_items_tenant_product", "stock_visit_items", ["tenant_id", "product_id"])


def downgrade() -> None:
    op.drop_table("stock_visit_items")
    op.drop_table("stock_visits")
    op.drop_table("customer_products")
    op.drop_table("promoter_customers")
    op.drop_table("products")
    op.drop_table("customers")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS customerstatus")
    op.execute("DROP TYPE IF EXISTS tenantstatus")
```

---

## 10. Backend — autenticação

Reaproveita integralmente o desenho do ERP. **O formato do token é sagrado** (Âncora 1):
mesmas claims, mesmo algoritmo. É o que permite que `dependencies.py` funcione sem
adaptação nos dois lados.

### `backend/app/auth/schemas.py` — VERBATIM

Copiado de `fv-laticinios/backend/app/auth/schemas.py`. No MVP você usará apenas
`LoginRequest`, `TokenResponse`, `RefreshRequest`, `AccessTokenResponse`, `UserResponse`
e `ChangePasswordRequest` — o resto pode ficar sem uso, não atrapalha.

> `UserResponse` tem o campo `tenant_id`, `role`, `profile`. Como o novo `User` não tem
> `profile`, ou você adiciona a coluna, ou remove o campo do schema. **Recomendo remover
> o campo do schema** e deixar o model igual ao do ERP menos `profile`/`preferences`.

### `backend/app/auth/service.py`

Adaptado: sem `EmailService`, sem `PasswordResetToken` (recuperação de senha fica para
depois — no MVP o admin redefine a senha do promotor pela tela de usuários).

```python
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, verify_token,
)
from app.core.config import settings
from app.infrastructure.persistence.models.user import User

logger = logging.getLogger(__name__)


class AuthService:
    @staticmethod
    async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
        # Atalho de desenvolvimento — mesmo comportamento do ERP
        if settings.api_env == "development" and email.lower() == "admin" and password == "admin":
            result = await session.execute(select(User).where(User.email == "admin"))
            user = result.scalars().first()
            if user and user.is_active:
                return user

        result = await session.execute(select(User).where(User.email == email.lower().strip()))
        user = result.scalars().first()

        if not user or not verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

    @staticmethod
    def _token_data(user: User) -> dict:
        """FORMATO SAGRADO: idêntico ao do ERP (app/auth/service.py:44).
        Não altere sem alterar o ERP junto."""
        return {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "role": user.role.value,
            "profile": None,
            "email": user.email,
        }

    @staticmethod
    def create_tokens_for_user(user: User) -> tuple[str, str]:
        data = AuthService._token_data(user)
        return create_access_token(data), create_refresh_token(data)

    @staticmethod
    async def refresh_access_token(session: AsyncSession, refresh_token: str) -> str | None:
        payload = verify_token(refresh_token, token_type="refresh")
        if payload is None:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user or not user.is_active:
            return None
        return create_access_token(AuthService._token_data(user))

    @staticmethod
    def hash_password(password: str) -> str:
        return hash_password(password)
```

### `backend/app/auth/routes.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    LoginRequest, TokenResponse, UserResponse,
    RefreshRequest, AccessTokenResponse, ChangePasswordRequest,
)
from app.auth.service import AuthService
from app.core.dependencies import get_current_user
from app.core.security import hash_password, verify_password
from app.infrastructure.persistence.session import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    user = await AuthService.authenticate_user(session, request.email, request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Email ou senha inválidos")
    access_token, refresh_token = AuthService.create_tokens_for_user(user)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(body: RefreshRequest, session: AsyncSession = Depends(get_db_session)):
    access_token = await AuthService.refresh_access_token(session, body.refresh_token)
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Refresh token inválido ou expirado")
    return AccessTokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user=Depends(get_current_user)):
    return current_user


@router.put("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    current_user.password_hash = hash_password(body.new_password)
    session.add(current_user)
    await session.commit()
```

---

## 11. Backend — módulo merchandising

**Esta é a pasta que migra inteira para o ERP na fusão.** Tudo que é regra de negócio de
coleta de estoque mora aqui. Segue o padrão do ERP: `routes → service → repository`,
com `schemas` Pydantic no meio.

### `backend/app/merchandising/schemas.py`

```python
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ─── Clientes do promotor ─────────────────────────────────────────────────────


class PromoterCustomerResponse(BaseModel):
    id: UUID
    name: str
    corporate_name: Optional[str] = None
    document: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[dict] = None
    customer_type: Optional[str] = None
    # Para o promotor saber onde já passou
    last_visited_at: Optional[datetime] = None
    has_draft: bool = False

    model_config = {"from_attributes": True}


# ─── Produtos para contagem ───────────────────────────────────────────────────


class CountProductResponse(BaseModel):
    id: UUID
    sku: str
    barcode: Optional[str] = None
    name: str
    unit: str
    package_size: Optional[Decimal] = None
    image_url: Optional[str] = None
    position: int = 0
    # Contagem da visita anterior nesse cliente — âncora mental para o promotor
    last_quantity: Optional[Decimal] = None

    model_config = {"from_attributes": True}


# ─── Visita / contagem ────────────────────────────────────────────────────────


class StockVisitItemInput(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(ge=0)
    expires_at: Optional[date] = None
    notes: Optional[str] = None


class StockVisitCreate(BaseModel):
    customer_id: UUID
    # UUID gerado no aparelho — chave de idempotência do reenvio offline
    client_uuid: Optional[str] = Field(default=None, max_length=64)
    visited_at: Optional[datetime] = None
    notes: Optional[str] = None
    items: List[StockVisitItemInput] = []
    # true = já envia fechada; false = salva rascunho no servidor
    submit: bool = False


class StockVisitItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    product_unit: Optional[str] = None
    quantity: Decimal
    expires_at: Optional[date] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class StockVisitResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    customer_document: Optional[str] = None
    promoter_id: UUID
    promoter_name: Optional[str] = None
    status: str
    visited_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None
    notes: Optional[str] = None
    client_uuid: Optional[str] = None
    items: List[StockVisitItemResponse] = []
    items_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StockVisitListResponse(BaseModel):
    items: List[StockVisitResponse]
    total: int
    limit: int
    offset: int


# ─── Administração ────────────────────────────────────────────────────────────


class AssignmentUpdate(BaseModel):
    """Define o conjunto completo de clientes de um promotor (substitui o anterior)."""
    customer_ids: List[UUID]


class CustomerMixUpdate(BaseModel):
    """Define o mix de produtos contados em um cliente, na ordem informada."""
    product_ids: List[UUID]
```

### `backend/app/merchandising/repository.py`

Todas as queries filtram por `tenant_id` (Âncora 2), sem exceção.

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.customer import Customer, CustomerStatus
from app.infrastructure.persistence.models.customer_product import CustomerProduct
from app.infrastructure.persistence.models.product import Product
from app.infrastructure.persistence.models.promoter_customer import PromoterCustomer
from app.infrastructure.persistence.models.stock_visit import StockVisit, StockVisitItem
from app.infrastructure.persistence.models.user import User


class MerchandisingRepository:

    # ── Clientes do promotor ──────────────────────────────────────────────

    @staticmethod
    async def list_customers_for_promoter(
        session: AsyncSession,
        tenant_id: UUID,
        user_id: Optional[UUID],
        search: Optional[str] = None,
    ) -> Sequence[tuple[Customer, Optional[datetime]]]:
        """Clientes do promotor + data da última visita enviada.
        `user_id=None` retorna todos os clientes do tenant (visão do admin)."""

        last_visit = (
            select(
                StockVisit.customer_id.label("customer_id"),
                func.max(StockVisit.submitted_at).label("last_visited_at"),
            )
            .where(
                StockVisit.tenant_id == tenant_id,
                StockVisit.status != "draft",
            )
            .group_by(StockVisit.customer_id)
            .subquery()
        )

        query = (
            select(Customer, last_visit.c.last_visited_at)
            .outerjoin(last_visit, last_visit.c.customer_id == Customer.id)
            .where(
                Customer.tenant_id == tenant_id,
                Customer.status == CustomerStatus.ACTIVE,
            )
        )

        if user_id is not None:
            query = query.join(
                PromoterCustomer,
                and_(
                    PromoterCustomer.customer_id == Customer.id,
                    PromoterCustomer.tenant_id == tenant_id,
                    PromoterCustomer.user_id == user_id,
                    PromoterCustomer.is_active.is_(True),
                ),
            )

        if search:
            like = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Customer.name.ilike(like),
                    Customer.corporate_name.ilike(like),
                    Customer.document.ilike(like),
                )
            )

        query = query.order_by(Customer.name)
        result = await session.execute(query)
        return result.all()

    @staticmethod
    async def is_customer_assigned(
        session: AsyncSession, tenant_id: UUID, user_id: UUID, customer_id: UUID
    ) -> bool:
        query = select(func.count()).select_from(PromoterCustomer).where(
            PromoterCustomer.tenant_id == tenant_id,
            PromoterCustomer.user_id == user_id,
            PromoterCustomer.customer_id == customer_id,
            PromoterCustomer.is_active.is_(True),
        )
        return bool((await session.execute(query)).scalar_one())

    # ── Produtos para contagem ────────────────────────────────────────────

    @staticmethod
    async def list_mix_products(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID
    ) -> Sequence[tuple[Product, int]]:
        query = (
            select(Product, CustomerProduct.position)
            .join(
                CustomerProduct,
                and_(
                    CustomerProduct.product_id == Product.id,
                    CustomerProduct.tenant_id == tenant_id,
                    CustomerProduct.customer_id == customer_id,
                ),
            )
            .where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .order_by(CustomerProduct.position, Product.name)
        )
        return (await session.execute(query)).all()

    @staticmethod
    async def list_all_products(
        session: AsyncSession, tenant_id: UUID, search: Optional[str] = None
    ) -> Sequence[Product]:
        query = select(Product).where(
            Product.tenant_id == tenant_id, Product.is_active.is_(True)
        )
        if search:
            like = f"%{search.strip()}%"
            query = query.where(
                or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode.ilike(like))
            )
        query = query.order_by(Product.name)
        return (await session.execute(query)).scalars().all()

    @staticmethod
    async def last_quantities_for_customer(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID
    ) -> dict[UUID, object]:
        """Quantidades da última visita enviada nesse cliente: {product_id: quantity}."""
        last_visit_id = (
            select(StockVisit.id)
            .where(
                StockVisit.tenant_id == tenant_id,
                StockVisit.customer_id == customer_id,
                StockVisit.status != "draft",
            )
            .order_by(StockVisit.submitted_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        query = select(StockVisitItem.product_id, StockVisitItem.quantity).where(
            StockVisitItem.tenant_id == tenant_id,
            StockVisitItem.visit_id == last_visit_id,
        )
        return {row[0]: row[1] for row in (await session.execute(query)).all()}

    # ── Visitas ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_visit(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> Optional[StockVisit]:
        query = select(StockVisit).where(
            StockVisit.tenant_id == tenant_id, StockVisit.id == visit_id
        )
        return (await session.execute(query)).scalars().first()

    @staticmethod
    async def get_visit_by_client_uuid(
        session: AsyncSession, tenant_id: UUID, client_uuid: str
    ) -> Optional[StockVisit]:
        query = select(StockVisit).where(
            StockVisit.tenant_id == tenant_id, StockVisit.client_uuid == client_uuid
        )
        return (await session.execute(query)).scalars().first()

    @staticmethod
    async def save_visit(session: AsyncSession, visit: StockVisit) -> StockVisit:
        session.add(visit)
        await session.commit()
        await session.refresh(visit)
        return visit

    @staticmethod
    async def replace_items(
        session: AsyncSession, visit_id: UUID, items: list[StockVisitItem]
    ) -> None:
        await session.execute(
            delete(StockVisitItem).where(StockVisitItem.visit_id == visit_id)
        )
        for item in items:
            session.add(item)
        await session.commit()

    @staticmethod
    async def list_items(
        session: AsyncSession, visit_id: UUID
    ) -> Sequence[tuple[StockVisitItem, str, str, str]]:
        query = (
            select(StockVisitItem, Product.sku, Product.name, Product.unit)
            .join(Product, Product.id == StockVisitItem.product_id, isouter=True)
            .where(StockVisitItem.visit_id == visit_id)
            .order_by(Product.name)
        )
        return (await session.execute(query)).all()

    @staticmethod
    async def list_visits(
        session: AsyncSession,
        tenant_id: UUID,
        promoter_id: Optional[UUID] = None,
        customer_id: Optional[UUID] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[tuple[StockVisit, str, str]], int]:
        base = (
            select(StockVisit, Customer.name, User.full_name)
            .join(Customer, Customer.id == StockVisit.customer_id, isouter=True)
            .join(User, User.id == StockVisit.promoter_id, isouter=True)
            .where(StockVisit.tenant_id == tenant_id)
        )

        if promoter_id:
            base = base.where(StockVisit.promoter_id == promoter_id)
        if customer_id:
            base = base.where(StockVisit.customer_id == customer_id)
        if status:
            base = base.where(StockVisit.status == status)
        if date_from:
            base = base.where(StockVisit.visited_at >= date_from)
        if date_to:
            base = base.where(StockVisit.visited_at <= date_to)

        total = (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()

        rows = (
            await session.execute(
                base.order_by(StockVisit.visited_at.desc().nullslast(),
                              StockVisit.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        return rows, total

    @staticmethod
    async def export_rows(
        session: AsyncSession,
        tenant_id: UUID,
        visit_ids: Optional[list[UUID]] = None,
        promoter_id: Optional[UUID] = None,
        customer_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Sequence:
        """Linhas achatadas (uma por item) prontas para a planilha."""
        query = (
            select(
                StockVisit.visited_at,
                StockVisit.submitted_at,
                Customer.document,
                Customer.name.label("customer_name"),
                User.full_name.label("promoter_name"),
                Product.sku,
                Product.barcode,
                Product.name.label("product_name"),
                Product.unit,
                StockVisitItem.quantity,
                StockVisitItem.expires_at,
                StockVisitItem.notes,
                StockVisit.notes.label("visit_notes"),
            )
            .select_from(StockVisitItem)
            .join(StockVisit, StockVisit.id == StockVisitItem.visit_id)
            .join(Customer, Customer.id == StockVisit.customer_id, isouter=True)
            .join(User, User.id == StockVisit.promoter_id, isouter=True)
            .join(Product, Product.id == StockVisitItem.product_id, isouter=True)
            .where(
                StockVisit.tenant_id == tenant_id,
                StockVisit.status != "draft",
            )
        )

        if visit_ids:
            query = query.where(StockVisit.id.in_(visit_ids))
        if promoter_id:
            query = query.where(StockVisit.promoter_id == promoter_id)
        if customer_id:
            query = query.where(StockVisit.customer_id == customer_id)
        if date_from:
            query = query.where(StockVisit.visited_at >= date_from)
        if date_to:
            query = query.where(StockVisit.visited_at <= date_to)

        query = query.order_by(StockVisit.visited_at, Customer.name, Product.name)
        return (await session.execute(query)).all()

    # ── Vínculos e mix (admin) ────────────────────────────────────────────

    @staticmethod
    async def replace_assignments(
        session: AsyncSession, tenant_id: UUID, user_id: UUID, customer_ids: list[UUID]
    ) -> None:
        await session.execute(
            delete(PromoterCustomer).where(
                PromoterCustomer.tenant_id == tenant_id,
                PromoterCustomer.user_id == user_id,
            )
        )
        for customer_id in customer_ids:
            session.add(
                PromoterCustomer(
                    tenant_id=tenant_id, user_id=user_id,
                    customer_id=customer_id, is_active=True,
                )
            )
        await session.commit()

    @staticmethod
    async def replace_mix(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, product_ids: list[UUID]
    ) -> None:
        await session.execute(
            delete(CustomerProduct).where(
                CustomerProduct.tenant_id == tenant_id,
                CustomerProduct.customer_id == customer_id,
            )
        )
        for position, product_id in enumerate(product_ids):
            session.add(
                CustomerProduct(
                    tenant_id=tenant_id, customer_id=customer_id,
                    product_id=product_id, position=position,
                )
            )
        await session.commit()

    @staticmethod
    async def list_assigned_customer_ids(
        session: AsyncSession, tenant_id: UUID, user_id: UUID
    ) -> list[UUID]:
        query = select(PromoterCustomer.customer_id).where(
            PromoterCustomer.tenant_id == tenant_id,
            PromoterCustomer.user_id == user_id,
        )
        return list((await session.execute(query)).scalars().all())
```

### `backend/app/merchandising/service.py`

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.stock_visit import (
    StockVisit, StockVisitItem, StockVisitStatus,
)
from app.infrastructure.persistence.models.user import User, UserRole
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    CountProductResponse, PromoterCustomerResponse, StockVisitCreate,
    StockVisitItemResponse, StockVisitResponse,
)


def _is_admin(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.SUPERVISOR)


class MerchandisingService:

    # ── Promotor: clientes ────────────────────────────────────────────────

    @staticmethod
    async def list_my_customers(
        session: AsyncSession, tenant_id: UUID, user: User, search: Optional[str] = None
    ) -> list[PromoterCustomerResponse]:
        # Admin enxerga todos; promotor só os seus
        scope_user_id = None if _is_admin(user) else user.id
        rows = await Repo.list_customers_for_promoter(session, tenant_id, scope_user_id, search)

        return [
            PromoterCustomerResponse(
                id=customer.id,
                name=customer.name,
                corporate_name=customer.corporate_name,
                document=customer.document,
                phone=customer.phone,
                address=customer.address,
                customer_type=customer.customer_type,
                last_visited_at=last_visited_at,
            )
            for customer, last_visited_at in rows
        ]

    # ── Promotor: produtos para contar ────────────────────────────────────

    @staticmethod
    async def list_products_for_customer(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
        search: Optional[str] = None,
    ) -> list[CountProductResponse]:
        await MerchandisingService._assert_can_access_customer(session, tenant_id, user, customer_id)

        last_qty = await Repo.last_quantities_for_customer(session, tenant_id, customer_id)

        mix = await Repo.list_mix_products(session, tenant_id, customer_id)
        if mix:
            products = [(p, position) for p, position in mix]
        else:
            # Sem mix cadastrado: cai no catálogo completo
            products = [(p, 0) for p in await Repo.list_all_products(session, tenant_id, search)]

        if search and mix:
            term = search.strip().lower()
            products = [
                (p, pos) for p, pos in products
                if term in p.name.lower()
                or term in (p.sku or "").lower()
                or term in (p.barcode or "").lower()
            ]

        return [
            CountProductResponse(
                id=p.id, sku=p.sku, barcode=p.barcode, name=p.name, unit=p.unit,
                package_size=p.package_size, image_url=p.image_url,
                position=position, last_quantity=last_qty.get(p.id),
            )
            for p, position in products
        ]

    # ── Promotor: gravar contagem ─────────────────────────────────────────

    @staticmethod
    async def upsert_visit(
        session: AsyncSession, tenant_id: UUID, user: User, payload: StockVisitCreate
    ) -> StockVisitResponse:
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, payload.customer_id
        )

        visit = None
        if payload.client_uuid:
            # Idempotência: reenvio da mesma contagem atualiza em vez de duplicar
            visit = await Repo.get_visit_by_client_uuid(session, tenant_id, payload.client_uuid)

        now = datetime.now(timezone.utc)

        if visit is None:
            visit = StockVisit(
                id=uuid4(),
                tenant_id=tenant_id,
                customer_id=payload.customer_id,
                promoter_id=user.id,
                client_uuid=payload.client_uuid,
                status=StockVisitStatus.DRAFT.value,
                visited_at=payload.visited_at or now,
            )
        else:
            if visit.status == StockVisitStatus.EXPORTED.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Esta contagem já foi exportada e não pode mais ser alterada.",
                )
            if visit.promoter_id != user.id and not _is_admin(user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Esta contagem pertence a outro promotor.",
                )
            visit.visited_at = payload.visited_at or visit.visited_at or now

        visit.notes = payload.notes

        if payload.submit:
            visit.status = StockVisitStatus.SUBMITTED.value
            visit.submitted_at = now

        visit = await Repo.save_visit(session, visit)

        items = [
            StockVisitItem(
                id=uuid4(),
                tenant_id=tenant_id,
                visit_id=visit.id,
                product_id=item.product_id,
                quantity=item.quantity,
                expires_at=item.expires_at,
                notes=item.notes,
            )
            for item in payload.items
        ]
        await Repo.replace_items(session, visit.id, items)

        return await MerchandisingService.get_visit(session, tenant_id, visit.id)

    @staticmethod
    async def submit_visit(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID
    ) -> StockVisitResponse:
        visit = await Repo.get_visit(session, tenant_id, visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")
        if visit.promoter_id != user.id and not _is_admin(user):
            raise HTTPException(status_code=403, detail="Contagem de outro promotor")

        visit.status = StockVisitStatus.SUBMITTED.value
        visit.submitted_at = datetime.now(timezone.utc)
        await Repo.save_visit(session, visit)
        return await MerchandisingService.get_visit(session, tenant_id, visit_id)

    # ── Leitura ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_visit(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> StockVisitResponse:
        visit = await Repo.get_visit(session, tenant_id, visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")

        item_rows = await Repo.list_items(session, visit.id)
        items = [
            StockVisitItemResponse(
                id=item.id, product_id=item.product_id, product_sku=sku,
                product_name=name, product_unit=unit, quantity=item.quantity,
                expires_at=item.expires_at, notes=item.notes,
            )
            for item, sku, name, unit in item_rows
        ]

        rows, _ = await Repo.list_visits(session, tenant_id, limit=1, offset=0)
        customer_name = promoter_name = None
        detail_rows, _ = await Repo.list_visits(
            session, tenant_id, customer_id=visit.customer_id, limit=200
        )
        for v, c_name, p_name in detail_rows:
            if v.id == visit.id:
                customer_name, promoter_name = c_name, p_name
                break

        return StockVisitResponse(
            id=visit.id, tenant_id=visit.tenant_id, customer_id=visit.customer_id,
            customer_name=customer_name, promoter_id=visit.promoter_id,
            promoter_name=promoter_name, status=visit.status,
            visited_at=visit.visited_at, submitted_at=visit.submitted_at,
            exported_at=visit.exported_at, notes=visit.notes,
            client_uuid=visit.client_uuid, items=items, items_count=len(items),
            created_at=visit.created_at, updated_at=visit.updated_at,
        )

    @staticmethod
    async def list_visits(
        session: AsyncSession, tenant_id: UUID, **filters
    ) -> tuple[list[StockVisitResponse], int]:
        rows, total = await Repo.list_visits(session, tenant_id, **filters)
        visits = [
            StockVisitResponse(
                id=v.id, tenant_id=v.tenant_id, customer_id=v.customer_id,
                customer_name=c_name, promoter_id=v.promoter_id, promoter_name=p_name,
                status=v.status, visited_at=v.visited_at, submitted_at=v.submitted_at,
                exported_at=v.exported_at, notes=v.notes, client_uuid=v.client_uuid,
                items=[], items_count=0,
                created_at=v.created_at, updated_at=v.updated_at,
            )
            for v, c_name, p_name in rows
        ]
        return visits, total

    # ── Guarda de acesso ──────────────────────────────────────────────────

    @staticmethod
    async def _assert_can_access_customer(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID
    ) -> None:
        if _is_admin(user):
            return
        if not await Repo.is_customer_assigned(session, tenant_id, user.id, customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este cliente não está atribuído a você.",
            )
```

> **Nota de implementação:** o `get_visit` acima resolve `customer_name`/`promoter_name`
> de forma preguiçosa para manter o exemplo curto. Na implementação real, troque por um
> `select` direto com `join` em `Customer` e `User` filtrando por `StockVisit.id` — uma
> query, não duas.

### `backend/app/merchandising/excel.py`

```python
"""Geração das planilhas .xlsx entregues ao administrador."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Sequence

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_HEADERS = [
    ("Data da visita", 18),
    ("CNPJ/CPF", 20),
    ("Cliente", 36),
    ("Promotor", 24),
    ("SKU", 14),
    ("Cód. barras", 16),
    ("Produto", 40),
    ("Un.", 8),
    ("Qtd. em estoque", 16),
    ("Validade", 12),
    ("Obs. do item", 28),
    ("Obs. da visita", 28),
]

_HEADER_FILL = PatternFill("solid", fgColor="1A237E")   # mesma cor primária do ERP
_HEADER_FONT = Font(color="FFFFFF", bold=True)


def build_workbook(rows: Sequence, sheet_title: str = "Estoque") -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title

    ws.append([h for h, _ in _HEADERS])
    for idx, (_, width) in enumerate(_HEADERS, start=1):
        cell = ws.cell(row=1, column=idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(idx)].width = width

    for r in rows:
        ws.append([
            r.visited_at.strftime("%d/%m/%Y %H:%M") if r.visited_at else "",
            r.document or "",
            r.customer_name or "",
            r.promoter_name or "",
            r.sku or "",
            r.barcode or "",
            r.product_name or "",
            r.unit or "",
            float(r.quantity) if r.quantity is not None else 0.0,
            r.expires_at.strftime("%d/%m/%Y") if r.expires_at else "",
            r.notes or "",
            r.visit_notes or "",
        ])

    # Congela o cabeçalho e liga o autofiltro — o administrador vai filtrar muito
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(_HEADERS))}{ws.max_row}"

    for row in ws.iter_rows(min_row=2, min_col=9, max_col=9):
        for cell in row:
            cell.number_format = "#,##0.000"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def xlsx_response(buf: BytesIO, filename: str) -> StreamingResponse:
    return StreamingResponse(
        buf,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def default_filename(prefix: str = "estoque") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
```

> **CORS:** o middleware do ERP (`backend/app/main.py:41`) já expõe
> `Access-Control-Expose-Headers: *`, então o `Content-Disposition` chega ao navegador.
> Replique esse middleware no novo app — o `main.py` da seção 13 já faz isso.

### `backend/app/merchandising/routes.py`

```python
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_and_tenant, require_roles
from app.infrastructure.persistence.session import get_db_session
from app.merchandising import excel
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    AssignmentUpdate, CountProductResponse, CustomerMixUpdate,
    PromoterCustomerResponse, StockVisitCreate, StockVisitListResponse, StockVisitResponse,
)
from app.merchandising.service import MerchandisingService

router = APIRouter(prefix="/merchandising", tags=["merchandising"])

_ADMIN = ("admin", "supervisor")
_FIELD = ("promoter", "admin", "supervisor")


# ─── Promotor ─────────────────────────────────────────────────────────────────

@router.get("/my-customers", response_model=list[PromoterCustomerResponse])
async def list_my_customers(
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await MerchandisingService.list_my_customers(
        session, context["tenant_id"], context["user"], search
    )


@router.get("/customers/{customer_id}/products", response_model=list[CountProductResponse])
async def list_products_for_customer(
    customer_id: UUID,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await MerchandisingService.list_products_for_customer(
        session, context["tenant_id"], context["user"], customer_id, search
    )


@router.post("/visits", response_model=StockVisitResponse, status_code=status.HTTP_201_CREATED)
async def upsert_visit(
    payload: StockVisitCreate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    """Cria ou atualiza uma contagem. Idempotente via `client_uuid`."""
    return await MerchandisingService.upsert_visit(
        session, context["tenant_id"], context["user"], payload
    )


@router.post("/visits/{visit_id}/submit", response_model=StockVisitResponse)
async def submit_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await MerchandisingService.submit_visit(
        session, context["tenant_id"], context["user"], visit_id
    )


@router.get("/visits/mine", response_model=StockVisitListResponse)
async def list_my_visits(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    items, total = await MerchandisingService.list_visits(
        session, context["tenant_id"],
        promoter_id=context["user"].id, status=status_filter,
        limit=limit, offset=offset,
    )
    return StockVisitListResponse(items=items, total=total, limit=limit, offset=offset)


# ─── Administrador: visitas e planilhas ───────────────────────────────────────

@router.get("/visits", response_model=StockVisitListResponse)
async def list_visits(
    promoter_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    items, total = await MerchandisingService.list_visits(
        session, context["tenant_id"],
        promoter_id=promoter_id, customer_id=customer_id, status=status_filter,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )
    return StockVisitListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/visits/{visit_id}", response_model=StockVisitResponse)
async def get_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await MerchandisingService.get_visit(session, context["tenant_id"], visit_id)


@router.get("/visits/{visit_id}/export.xlsx")
async def export_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    rows = await Repo.export_rows(session, context["tenant_id"], visit_ids=[visit_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Contagem sem itens ou inexistente")
    buf = excel.build_workbook(rows)
    return excel.xlsx_response(buf, excel.default_filename("contagem"))


@router.get("/exports.xlsx")
async def export_consolidated(
    promoter_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    rows = await Repo.export_rows(
        session, context["tenant_id"],
        promoter_id=promoter_id, customer_id=customer_id,
        date_from=date_from, date_to=date_to,
    )
    buf = excel.build_workbook(rows, sheet_title="Consolidado")
    return excel.xlsx_response(buf, excel.default_filename("estoque_consolidado"))


# ─── Administrador: vínculos e mix ────────────────────────────────────────────

@router.get("/assignments/{promoter_id}", response_model=list[UUID])
async def get_assignments(
    promoter_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await Repo.list_assigned_customer_ids(session, context["tenant_id"], promoter_id)


@router.put("/assignments/{promoter_id}", status_code=204)
async def set_assignments(
    promoter_id: UUID,
    payload: AssignmentUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    await Repo.replace_assignments(
        session, context["tenant_id"], promoter_id, payload.customer_ids
    )


@router.put("/customers/{customer_id}/mix", status_code=204)
async def set_customer_mix(
    customer_id: UUID,
    payload: CustomerMixUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    await Repo.replace_mix(session, context["tenant_id"], customer_id, payload.product_ids)
```

---

## 12. Backend — cadastros de clientes e produtos

Sem ERP, alguém precisa cadastrar clientes e produtos — e aqui isso é feito **à mão,
pelo administrador**, na tela de Cadastros. Não há importação de cadastros por planilha.

A chave natural continua valendo (Âncora 4): `document` (CNPJ/CPF) para cliente e
`sku` (código do item no ERP) para produto. É por esses dois campos que a planilha de
faturamento encontra o cliente e o produto de cada linha — e é por eles que, no dia da
integração, os cadastros do ERP serão casados com os daqui para preencher `external_id`.

### Módulos `customers/` e `products/`

CRUD mínimo, seguindo o mesmo padrão `routes → service → repository → schemas` dos
módulos homônimos do ERP (`fv-laticinios/backend/app/customers/`). Use aqueles arquivos
como base, removendo o que depende de tabelas inexistentes (`companies`,
`payment_methods`, `customer_credits`, `customer_purchase_history`).

Endpoints necessários no MVP — nada além disso:

```
GET    /customers?search=          POST   /customers
GET    /customers/{id}             PUT    /customers/{id}
GET    /products?search=           POST   /products
GET    /products/{id}              PUT    /products/{id}
GET    /users?role=promoter        POST   /users        (admin cria promotores)
                                   PUT    /users/{id}/password
```

---

## 13. Backend — main.py e seed

### `backend/app/main.py`

O middleware de CORS é uma cópia do ERP (`fv-laticinios/backend/app/main.py:41`) — ele
aceita `localhost` e IPs de rede local, o que é essencial para testar o PWA no celular
pela Wi-Fi durante o desenvolvimento.

```python
import logging
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.auth.routes import router as auth_router
from app.core.config import settings
from app.customers.routes import router as customers_router
from app.merchandising.routes import router as merchandising_router
from app.products.routes import router as products_router
from app.users.routes import router as users_router
from app.infrastructure.persistence import models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Coleta de Estoque API",
    description="App de coleta de estoque em ponto de venda — promotores",
    version="0.1.0",
)

# Aceita localhost, 127.x.x.x e IPs de rede local (essencial para testar no celular)
_DEV_ORIGIN_RE = re.compile(
    r"^https?://(localhost|127\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
)

_PROD_ORIGINS = [settings.frontend_url]

_CORS_HEADERS = {
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    # Necessário para o navegador ler o nome do arquivo .xlsx no download
    "Access-Control-Expose-Headers": "*",
    "Access-Control-Max-Age": "600",
}


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")
    is_dev = settings.api_env != "production"

    allowed = (
        (is_dev and bool(_DEV_ORIGIN_RE.match(origin)))
        or origin in _PROD_ORIGINS
    )

    if request.method == "OPTIONS" and allowed:
        return Response(
            status_code=204,
            headers={**_CORS_HEADERS, "Access-Control-Allow-Origin": origin},
        )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
        response = JSONResponse(status_code=500, content={"detail": "Erro interno do servidor"})

    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        for key, value in _CORS_HEADERS.items():
            response.headers[key] = value

    return response


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.api_env}


app.include_router(auth_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(users_router)
app.include_router(merchandising_router)
```

### `backend/app/scripts/seed.py`

Cria o tenant único, o administrador e um promotor de teste.

```python
import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.auth.service import AuthService
from app.infrastructure.persistence.models.tenant import Tenant, TenantStatus
from app.infrastructure.persistence.models.user import User, UserRole
from app.infrastructure.persistence.session import AsyncSessionLocal

TENANT_NAME = "fv-laticinios"


async def seed():
    async with AsyncSessionLocal() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.name == TENANT_NAME))
        ).scalars().first()

        if not tenant:
            tenant = Tenant(
                id=uuid4(), name=TENANT_NAME, slug=TENANT_NAME, status=TenantStatus.ACTIVE
            )
            session.add(tenant)
            await session.flush()
            print(f"Tenant criado: {tenant.id}")

        seeds = [
            ("admin", "admin", "Administrador", UserRole.ADMIN),
            ("promotor", "promotor", "Promotor de Teste", UserRole.PROMOTER),
        ]

        for email, password, full_name, role in seeds:
            existing = (
                await session.execute(
                    select(User).where(User.tenant_id == tenant.id, User.email == email)
                )
            ).scalars().first()
            if existing:
                continue
            session.add(
                User(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    email=email,
                    password_hash=AuthService.hash_password(password),
                    full_name=full_name,
                    role=role,
                    is_active=True,
                )
            )
            print(f"Usuário criado: {email} / {password}")

        await session.commit()
        print("Seed concluído.")


if __name__ == "__main__":
    asyncio.run(seed())
```

Subir o ambiente pela primeira vez:

```bash
cd fv-estoque
cp .env.example .env
docker compose up -d --build
make migrate
make seed
# API:  http://localhost:8002/docs
# Web:  http://localhost:5174
```

---

## 14. Frontend — configuração

### `frontend/package.json`

```json
{
  "name": "estoque-promotor",
  "version": "0.1.0",
  "description": "Coleta de estoque em ponto de venda - PWA do promotor",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.6.0",
    "date-fns": "^2.30.0",
    "pinia": "^2.1.0",
    "quasar": "^2.14.0",
    "vue": "^3.3.0",
    "vue-router": "^4.6.4"
  },
  "devDependencies": {
    "@quasar/extras": "^1.17.0",
    "@quasar/vite-plugin": "^1.7.0",
    "@vitejs/plugin-vue": "^4.5.0",
    "sass": "^1.69.0",
    "vite": "^5.0.0",
    "vite-plugin-pwa": "^1.3.0"
  }
}
```

### `frontend/vite.config.js`

Diferenças em relação ao ERP: porta 5174, `base: '/'` (app na raiz do domínio) e
`registerType: 'prompt'`.

> **Por que `prompt` e não `autoUpdate`:** o ERP usa `autoUpdate`, que recarrega a página
> sozinho quando há versão nova. Num app de digitação em campo, isso pode descartar uma
> contagem em andamento. Com `prompt`, o promotor decide quando atualizar.

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { quasar, transformAssetUrls } from '@quasar/vite-plugin'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: '/',
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({ sassVariables: false }),
    VitePWA({
      registerType: 'prompt',
      devOptions: { enabled: true },
      includeAssets: ['favicon-32.png', 'apple-touch-icon.png'],
      manifest: {
        name: 'Coleta de Estoque',
        short_name: 'Estoque',
        description: 'Coleta de estoque em ponto de venda',
        theme_color: '#1a237e',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        lang: 'pt-BR',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          {
            // Clientes e produtos podem vir do cache quando não há sinal
            urlPattern: ({ url }) => url.pathname.startsWith('/merchandising/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'merch-cache',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 },
              networkTimeoutSeconds: 5,
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: { '@': new URL('./src', import.meta.url).pathname },
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    allowedHosts: 'all',
    proxy: {
      '/api-proxy': {
        target: 'http://estoque_api:8000',
        rewrite: (path) => path.replace(/^\/api-proxy/, ''),
        changeOrigin: true,
      },
    },
    watch: { usePolling: true, interval: 500 },
  },
  build: { outDir: 'dist', sourcemap: false },
})
```

### `frontend/src/main.js`

Mesmas cores de marca do ERP — quando as telas migrarem, a identidade visual já bate.

```js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { Quasar, Notify, Loading, Dialog } from 'quasar'
import quasarIconSet from 'quasar/icon-set/material-icons'
import '@quasar/extras/roboto-font/roboto-font.css'
import '@quasar/extras/material-icons/material-icons.css'
import 'quasar/dist/quasar.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Quasar, {
  plugins: { Notify, Loading, Dialog },
  iconSet: quasarIconSet,
  config: {
    dark: false,
    brand: {
      primary: '#1a237e',
      secondary: '#fbc02d',
      accent: '#283593',
      dark: '#0d1442',
      positive: '#2e7d32',
      negative: '#c62828',
      info: '#0288d1',
      warning: '#f57c00',
    },
  },
})

app.mount('#app')
```

### `frontend/src/api/client.js` — VERBATIM (uma linha alterada)

Copiado de `fv-laticinios/frontend/src/api/client.js`. A única mudança é a porta no
fallback de desenvolvimento:

```js
// linha ~12 — trocar 8001 por 8002
: `http://${devHost}:8002`
```

Vale destacar dois comportamentos que já vêm de graça e são importantes aqui:
o refresh automático de token em `401` e o redirecionamento para `/login` quando o
refresh falha.

---

## 15. Frontend — API, stores e fila offline

### `frontend/src/api/merchandising.js`

Segue o padrão de `fv-laticinios/frontend/src/api/salesRoutes.js`.

```js
import apiClient from '@/api/client'

const normalizeParams = (params = {}) => {
  const clean = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') clean[key] = value
  })
  return clean
}

export const merchandisingApi = {
  // ── Promotor ──────────────────────────────────────────────────────────
  async myCustomers(params = {}) {
    const { data } = await apiClient.get('/merchandising/my-customers', {
      params: normalizeParams(params),
    })
    return data
  },

  async productsForCustomer(customerId, params = {}) {
    const { data } = await apiClient.get(
      `/merchandising/customers/${customerId}/products`,
      { params: normalizeParams(params) }
    )
    return data
  },

  async saveVisit(payload) {
    // Timeout maior: o promotor pode ter 40 itens e sinal ruim de supermercado.
    // O default do apiClient (10s) é curto demais para este envio.
    const { data } = await apiClient.post('/merchandising/visits', payload, {
      timeout: 30000,
    })
    return data
  },

  async submitVisit(visitId) {
    const { data } = await apiClient.post(`/merchandising/visits/${visitId}/submit`)
    return data
  },

  async myVisits(params = {}) {
    const { data } = await apiClient.get('/merchandising/visits/mine', {
      params: normalizeParams(params),
    })
    return data
  },

  // ── Administrador ─────────────────────────────────────────────────────
  async visits(params = {}) {
    const { data } = await apiClient.get('/merchandising/visits', {
      params: normalizeParams(params),
    })
    return data
  },

  async visit(visitId) {
    const { data } = await apiClient.get(`/merchandising/visits/${visitId}`)
    return data
  },

  async exportVisit(visitId) {
    const response = await apiClient.get(
      `/merchandising/visits/${visitId}/export.xlsx`,
      { responseType: 'blob' }
    )
    downloadBlob(response)
  },

  async exportConsolidated(params = {}) {
    const response = await apiClient.get('/merchandising/exports.xlsx', {
      params: normalizeParams(params),
      responseType: 'blob',
      timeout: 60000,
    })
    downloadBlob(response)
  },

  async getAssignments(promoterId) {
    const { data } = await apiClient.get(`/merchandising/assignments/${promoterId}`)
    return data
  },

  async setAssignments(promoterId, customerIds) {
    await apiClient.put(`/merchandising/assignments/${promoterId}`, {
      customer_ids: customerIds,
    })
  },

  async setCustomerMix(customerId, productIds) {
    await apiClient.put(`/merchandising/customers/${customerId}/mix`, {
      product_ids: productIds,
    })
  },
}

/** Extrai o nome do arquivo do Content-Disposition e dispara o download. */
function downloadBlob(response) {
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const filename = match ? match[1] : 'planilha.xlsx'

  const url = window.URL.createObjectURL(new Blob([response.data]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}
```

### `frontend/src/stores/visita.js`

O rascunho da contagem vive aqui e é **persistido a cada tecla digitada**. Se o app
fechar, o celular travar ou a bateria acabar, nada se perde.

```js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { merchandisingApi } from '@/api/merchandising'

const DRAFTS_KEY = 'estoque_drafts'
const QUEUE_KEY = 'estoque_queue'

const load = (key) => JSON.parse(localStorage.getItem(key) || '{}')
const save = (key, value) => localStorage.setItem(key, JSON.stringify(value))

export const useVisitaStore = defineStore('visita', () => {
  // { [customerId]: { client_uuid, visited_at, notes, items: { [productId]: {...} } } }
  const drafts = ref(load(DRAFTS_KEY))
  // Contagens fechadas que ainda não subiram
  const queue = ref(JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'))
  const sending = ref(false)

  const persist = () => {
    save(DRAFTS_KEY, drafts.value)
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.value))
  }

  const pendingCount = computed(() => queue.value.length)

  function getDraft(customerId) {
    if (!drafts.value[customerId]) {
      drafts.value[customerId] = {
        client_uuid: crypto.randomUUID(),
        visited_at: new Date().toISOString(),
        notes: '',
        items: {},
      }
      persist()
    }
    return drafts.value[customerId]
  }

  function setItem(customerId, productId, { quantity, expires_at, notes }) {
    const draft = getDraft(customerId)
    if (quantity === null || quantity === undefined || quantity === '') {
      delete draft.items[productId]
    } else {
      draft.items[productId] = {
        product_id: productId,
        quantity: Number(quantity),
        expires_at: expires_at || null,
        notes: notes || null,
      }
    }
    persist()
  }

  function itemsCount(customerId) {
    return Object.keys(drafts.value[customerId]?.items || {}).length
  }

  function clearDraft(customerId) {
    delete drafts.value[customerId]
    persist()
  }

  /** Fecha a contagem: tenta enviar; se falhar, enfileira para reenvio. */
  async function submit(customerId) {
    const draft = getDraft(customerId)
    const payload = {
      customer_id: customerId,
      client_uuid: draft.client_uuid,
      visited_at: draft.visited_at,
      notes: draft.notes || null,
      items: Object.values(draft.items),
      submit: true,
    }

    try {
      await merchandisingApi.saveVisit(payload)
      clearDraft(customerId)
      return { sent: true }
    } catch (error) {
      queue.value.push(payload)
      clearDraft(customerId)
      persist()
      return { sent: false, error }
    }
  }

  /** Reenvia tudo que está na fila. Seguro rodar quantas vezes quiser:
   *  o backend deduplica pelo client_uuid. */
  async function flushQueue() {
    if (sending.value || queue.value.length === 0) return { sent: 0, failed: 0 }
    sending.value = true

    let sent = 0
    const remaining = []

    for (const payload of queue.value) {
      try {
        await merchandisingApi.saveVisit(payload)
        sent += 1
      } catch {
        remaining.push(payload)
      }
    }

    queue.value = remaining
    persist()
    sending.value = false
    return { sent, failed: remaining.length }
  }

  return {
    drafts, queue, sending, pendingCount,
    getDraft, setItem, itemsCount, clearDraft, submit, flushQueue,
  }
})
```

### `frontend/src/composables/useOfflineQueue.js`

Dispara o reenvio quando a conexão volta e quando o app é reaberto.

```js
import { onMounted, onUnmounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useVisitaStore } from '@/stores/visita'

export function useOfflineQueue() {
  const $q = useQuasar()
  const visita = useVisitaStore()
  const online = ref(navigator.onLine)

  async function tryFlush() {
    if (!navigator.onLine) return
    const { sent } = await visita.flushQueue()
    if (sent > 0) {
      $q.notify({
        type: 'positive',
        message: `${sent} contagem(ns) enviada(s) com sucesso.`,
        position: 'top',
      })
    }
  }

  const handleOnline = () => {
    online.value = true
    tryFlush()
  }
  const handleOffline = () => {
    online.value = false
  }
  const handleVisibility = () => {
    if (document.visibilityState === 'visible') tryFlush()
  }

  onMounted(() => {
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    document.addEventListener('visibilitychange', handleVisibility)
    tryFlush()
  })

  onUnmounted(() => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    document.removeEventListener('visibilitychange', handleVisibility)
  })

  return { online, tryFlush }
}
```

---

## 16. Frontend — rotas e layouts

### `frontend/src/router/index.js`

As rotas do promotor ficam em um **array exportado separadamente**. Na fusão, basta
espalhá-lo (`...promotorRoutes`) dentro do `routes` do ERP — uma linha.

```js
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUserStore } from '@/stores/user'

// ── Rotas do promotor: migram para o ERP como um bloco ────────────────────
export const promotorRoutes = [
  {
    path: '/promotor',
    component: () => import('@/layouts/PromotorLayout.vue'),
    meta: { requiresAuth: true, requiresRoles: ['promoter', 'admin', 'supervisor'] },
    children: [
      {
        path: '',
        name: 'PromotorClientes',
        component: () => import('@/pages/promotor/PromotorClientesPage.vue'),
      },
      {
        path: 'clientes/:customerId/produtos',
        name: 'PromotorProdutos',
        component: () => import('@/pages/promotor/PromotorProdutosPage.vue'),
        props: true,
      },
      {
        path: 'clientes/:customerId/produtos/:productId',
        name: 'PromotorContagem',
        component: () => import('@/pages/promotor/PromotorContagemPage.vue'),
        props: true,
      },
      {
        path: 'envios',
        name: 'PromotorEnvios',
        component: () => import('@/pages/promotor/PromotorEnviosPage.vue'),
      },
    ],
  },
]

// ── Rotas do administrador: viram filhas do MainLayout do ERP ─────────────
export const adminRoutes = [
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresRoles: ['admin', 'supervisor'] },
    children: [
      { path: '', redirect: { name: 'AdminVisitas' } },
      {
        path: 'visitas',
        name: 'AdminVisitas',
        component: () => import('@/pages/admin/AdminVisitasPage.vue'),
      },
      {
        path: 'vinculos',
        name: 'AdminVinculos',
        component: () => import('@/pages/admin/AdminVinculosPage.vue'),
      },
      {
        path: 'cadastros',
        name: 'AdminCadastros',
        component: () => import('@/pages/admin/AdminCadastrosPage.vue'),
      },
    ],
  },
]

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { requiresAuth: false },
  },
  ...promotorRoutes,
  ...adminRoutes,
  // A raiz redireciona conforme o papel — ver guard abaixo
  { path: '/', redirect: () => (roleOf() === 'promoter' ? '/promotor' : '/admin') },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

function roleOf() {
  return JSON.parse(localStorage.getItem('user') || 'null')?.role
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Guard idêntico em espírito ao do ERP (router/index.js:117)
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const userStore = useUserStore()

  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth !== false)
  const requiredRoles = to.matched.flatMap((r) => r.meta.requiresRoles || [])
  const role = userStore.user?.role || roleOf()

  if (requiresAuth && !authStore.isAuthenticated) {
    next('/login')
  } else if (requiredRoles.length > 0 && !requiredRoles.includes(role)) {
    next(role === 'promoter' ? '/promotor' : '/admin')
  } else if (to.path === '/login' && authStore.isAuthenticated) {
    next('/')
  } else {
    next()
  }
})

export default router
```

### `frontend/src/layouts/PromotorLayout.vue`

Layout **mobile-first**: sem sidebar, navegação inferior com alvos de toque grandes e
um indicador de pendências offline sempre visível.

```vue
<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-btn
          v-if="canGoBack"
          flat dense round icon="arrow_back"
          aria-label="Voltar"
          @click="$router.back()"
        />
        <q-toolbar-title class="text-subtitle1 text-weight-medium ellipsis">
          {{ title }}
        </q-toolbar-title>

        <!-- Estado da conexão: o promotor precisa saber, sem precisar perguntar -->
        <q-chip
          v-if="!online"
          dense square color="warning" text-color="dark" icon="cloud_off"
          class="q-mr-sm"
        >
          Offline
        </q-chip>

        <q-btn flat dense round icon="more_vert" aria-label="Menu">
          <q-menu>
            <q-list style="min-width: 180px">
              <q-item clickable v-close-popup @click="sync">
                <q-item-section avatar><q-icon name="sync" /></q-item-section>
                <q-item-section>Sincronizar agora</q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable v-close-popup @click="logout">
                <q-item-section avatar><q-icon name="logout" /></q-item-section>
                <q-item-section>Sair</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-page-container>
      <router-view />
    </q-page-container>

    <q-footer elevated class="bg-white text-primary">
      <q-tabs
        v-model="tab" dense no-caps active-color="primary"
        indicator-color="primary" class="text-grey-7"
      >
        <q-tab name="clientes" icon="store" label="Clientes" :to="{ name: 'PromotorClientes' }" />
        <q-tab name="envios" icon="cloud_upload" :to="{ name: 'PromotorEnvios' }">
          <q-badge v-if="visita.pendingCount" color="negative" floating>
            {{ visita.pendingCount }}
          </q-badge>
          <div class="q-tab__label">Envios</div>
        </q-tab>
      </q-tabs>
    </q-footer>
  </q-layout>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useAuthStore } from '@/stores/auth'
import { useVisitaStore } from '@/stores/visita'
import { useOfflineQueue } from '@/composables/useOfflineQueue'

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const auth = useAuthStore()
const visita = useVisitaStore()
const { online, tryFlush } = useOfflineQueue()

const tab = ref('clientes')

const canGoBack = computed(() => route.name !== 'PromotorClientes')
const title = computed(() => {
  const titles = {
    PromotorClientes: 'Meus Clientes',
    PromotorProdutos: 'Contagem',
    PromotorContagem: 'Digitar estoque',
    PromotorEnvios: 'Envios',
  }
  return titles[route.name] || 'Coleta de Estoque'
})

async function sync() {
  const { sent, failed } = await visita.flushQueue()
  $q.notify({
    type: failed ? 'warning' : 'positive',
    message: failed
      ? `${sent} enviada(s), ${failed} pendente(s).`
      : sent ? `${sent} contagem(ns) enviada(s).` : 'Nada pendente.',
    position: 'top',
  })
}

function logout() {
  if (visita.pendingCount > 0) {
    $q.dialog({
      title: 'Há contagens não enviadas',
      message: `${visita.pendingCount} contagem(ns) ainda não subiram. Se sair agora, elas continuam salvas neste aparelho. Deseja sair?`,
      cancel: true,
      persistent: true,
    }).onOk(() => {
      auth.logout()
      router.push('/login')
    })
    return
  }
  auth.logout()
  router.push('/login')
}
</script>
```

---

## 17. Frontend — telas do promotor

O fluxo pedido: **clientes → produtos → digitar estoque → enviar**.

### `pages/promotor/PromotorClientesPage.vue`

```vue
<template>
  <q-page class="q-pa-md">
    <q-input
      v-model="search" outlined dense clearable
      placeholder="Buscar cliente..." class="q-mb-md"
      @update:model-value="onSearch"
    >
      <template #prepend><q-icon name="search" /></template>
    </q-input>

    <div v-if="loading" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner v-else-if="!customers.length" class="bg-grey-2 text-grey-8 rounded-borders">
      <template #avatar><q-icon name="store" color="grey-6" /></template>
      Nenhum cliente atribuído a você. Fale com o administrador.
    </q-banner>

    <q-list v-else separator class="rounded-borders bg-white">
      <q-item
        v-for="customer in customers" :key="customer.id"
        clickable v-ripple class="q-py-md"
        @click="abrir(customer)"
      >
        <q-item-section avatar>
          <q-avatar color="primary" text-color="white" icon="store" />
        </q-item-section>

        <q-item-section>
          <q-item-label class="text-weight-medium">{{ customer.name }}</q-item-label>
          <q-item-label caption lines="1">
            {{ formatCidade(customer.address) }}
          </q-item-label>
          <q-item-label caption class="text-grey-6">
            {{ customer.last_visited_at
              ? `Última contagem: ${formatData(customer.last_visited_at)}`
              : 'Nunca contado' }}
          </q-item-label>
        </q-item-section>

        <q-item-section side>
          <!-- Rascunho em andamento neste aparelho -->
          <q-badge v-if="rascunho(customer.id)" color="warning" text-color="dark">
            {{ rascunho(customer.id) }} itens
          </q-badge>
          <q-icon v-else name="chevron_right" color="grey-5" />
        </q-item-section>
      </q-item>
    </q-list>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const customers = ref([])
const loading = ref(false)
const search = ref('')
let debounce = null

async function carregar() {
  loading.value = true
  try {
    customers.value = await merchandisingApi.myCustomers({ search: search.value })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar clientes',
    })
  } finally {
    loading.value = false
  }
}

function onSearch() {
  clearTimeout(debounce)
  debounce = setTimeout(carregar, 350)
}

const rascunho = (customerId) => visita.itemsCount(customerId)

function abrir(customer) {
  router.push({ name: 'PromotorProdutos', params: { customerId: customer.id } })
}

const formatCidade = (address) =>
  address?.city ? `${address.city}${address.state ? ' - ' + address.state : ''}` : '—'

const formatData = (iso) => new Date(iso).toLocaleDateString('pt-BR')

onMounted(carregar)
</script>
```

### `pages/promotor/PromotorProdutosPage.vue`

Lista os produtos do cliente e concentra o botão **Enviar contagem**.

```vue
<template>
  <q-page class="q-pa-md" style="padding-bottom: 88px">
    <q-input
      v-model="search" outlined dense clearable
      placeholder="Buscar produto..." class="q-mb-md"
    >
      <template #prepend><q-icon name="search" /></template>
    </q-input>

    <div v-if="loading" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-list v-else separator class="rounded-borders bg-white">
      <q-item
        v-for="product in filtrados" :key="product.id"
        clickable v-ripple class="q-py-md"
        @click="contar(product)"
      >
        <q-item-section>
          <q-item-label class="text-weight-medium">{{ product.name }}</q-item-label>
          <q-item-label caption>
            {{ product.sku }} · {{ product.unit }}
            <span v-if="product.last_quantity !== null && product.last_quantity !== undefined">
              · anterior: {{ formatQtd(product.last_quantity) }}
            </span>
          </q-item-label>
        </q-item-section>

        <q-item-section side>
          <q-chip
            v-if="digitado(product.id) !== null"
            square color="primary" text-color="white" class="text-weight-bold"
          >
            {{ formatQtd(digitado(product.id)) }}
          </q-chip>
          <q-icon v-else name="edit" color="grey-5" />
        </q-item-section>
      </q-item>
    </q-list>

    <!-- Barra fixa de envio -->
    <q-footer class="bg-transparent q-pa-md" style="bottom: 50px">
      <q-btn
        :label="`Enviar contagem (${totalDigitado})`"
        color="positive" size="lg" class="full-width"
        icon="cloud_upload" unelevated no-caps
        :disable="totalDigitado === 0" :loading="enviando"
        @click="enviar"
      />
    </q-footer>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({ customerId: { type: String, required: true } })

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const products = ref([])
const loading = ref(false)
const enviando = ref(false)
const search = ref('')

const filtrados = computed(() => {
  const term = search.value.trim().toLowerCase()
  if (!term) return products.value
  return products.value.filter(
    (p) =>
      p.name.toLowerCase().includes(term) ||
      (p.sku || '').toLowerCase().includes(term) ||
      (p.barcode || '').includes(term)
  )
})

const draft = computed(() => visita.getDraft(props.customerId))
const totalDigitado = computed(() => Object.keys(draft.value.items).length)

const digitado = (productId) => {
  const item = draft.value.items[productId]
  return item ? item.quantity : null
}

const formatQtd = (value) =>
  Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

function contar(product) {
  router.push({
    name: 'PromotorContagem',
    params: { customerId: props.customerId, productId: product.id },
  })
}

async function enviar() {
  enviando.value = true
  const { sent } = await visita.submit(props.customerId)
  enviando.value = false

  $q.notify({
    type: sent ? 'positive' : 'warning',
    message: sent
      ? 'Contagem enviada com sucesso.'
      : 'Sem conexão. A contagem foi salva e será enviada automaticamente.',
    position: 'top',
    timeout: 4000,
  })
  router.push({ name: 'PromotorClientes' })
}

onMounted(async () => {
  loading.value = true
  try {
    products.value = await merchandisingApi.productsForCustomer(props.customerId)
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar produtos',
    })
  } finally {
    loading.value = false
  }
})
</script>
```

### `pages/promotor/PromotorContagemPage.vue`

A tela de digitação. Detalhes que importam em campo: teclado numérico
(`inputmode="decimal"`), foco automático e botões grandes de +/−.

```vue
<template>
  <q-page class="q-pa-md">
    <q-card flat bordered class="q-mb-md">
      <q-card-section>
        <div class="text-h6">{{ product?.name || '...' }}</div>
        <div class="text-caption text-grey-7">
          {{ product?.sku }} · unidade: {{ product?.unit }}
          <span v-if="product?.package_size > 1">
            · caixa com {{ product.package_size }}
          </span>
        </div>
        <div
          v-if="product?.last_quantity !== null && product?.last_quantity !== undefined"
          class="text-caption text-grey-7 q-mt-xs"
        >
          Contagem anterior: <b>{{ product.last_quantity }}</b>
        </div>
      </q-card-section>
    </q-card>

    <div class="row items-center q-col-gutter-sm q-mb-md">
      <div class="col-auto">
        <q-btn
          round color="grey-4" text-color="dark" icon="remove" size="lg"
          aria-label="Diminuir" @click="ajustar(-1)"
        />
      </div>
      <div class="col">
        <q-input
          ref="inputRef" v-model="quantidade" outlined
          type="number" inputmode="decimal" min="0"
          input-class="text-center text-h4 text-weight-bold"
          placeholder="0"
        />
      </div>
      <div class="col-auto">
        <q-btn
          round color="primary" icon="add" size="lg"
          aria-label="Aumentar" @click="ajustar(1)"
        />
      </div>
    </div>

    <q-input
      v-model="validade" outlined label="Validade (opcional)"
      mask="##/##/####" class="q-mb-md"
    >
      <template #append>
        <q-icon name="event" class="cursor-pointer">
          <q-popup-proxy cover transition-show="scale">
            <q-date v-model="validade" mask="DD/MM/YYYY" minimal />
          </q-popup-proxy>
        </q-icon>
      </template>
    </q-input>

    <q-input
      v-model="observacao" outlined label="Observação (opcional)"
      type="textarea" autogrow class="q-mb-lg"
    />

    <q-btn
      label="Salvar e voltar" color="primary" size="lg"
      class="full-width" unelevated no-caps icon="check"
      @click="salvar"
    />
  </q-page>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({
  customerId: { type: String, required: true },
  productId: { type: String, required: true },
})

const router = useRouter()
const visita = useVisitaStore()

const product = ref(null)
const quantidade = ref('')
const validade = ref('')
const observacao = ref('')
const inputRef = ref(null)

function ajustar(delta) {
  const atual = Number(quantidade.value || 0)
  quantidade.value = String(Math.max(0, atual + delta))
}

/** dd/mm/aaaa → aaaa-mm-dd (formato aceito pela API) */
function toISODate(value) {
  if (!value || value.length !== 10) return null
  const [dia, mes, ano] = value.split('/')
  return `${ano}-${mes}-${dia}`
}

function salvar() {
  visita.setItem(props.customerId, props.productId, {
    quantity: quantidade.value === '' ? null : quantidade.value,
    expires_at: toISODate(validade.value),
    notes: observacao.value || null,
  })
  router.back()
}

onMounted(async () => {
  // Recupera o que já foi digitado antes, se houver
  const existente = visita.getDraft(props.customerId).items[props.productId]
  if (existente) {
    quantidade.value = String(existente.quantity)
    observacao.value = existente.notes || ''
    if (existente.expires_at) {
      const [ano, mes, dia] = existente.expires_at.split('-')
      validade.value = `${dia}/${mes}/${ano}`
    }
  }

  const lista = await merchandisingApi.productsForCustomer(props.customerId)
  product.value = lista.find((p) => p.id === props.productId) || null

  await nextTick()
  inputRef.value?.focus()
})
</script>
```

### `pages/promotor/PromotorEnviosPage.vue`

Transparência sobre o que subiu e o que ainda está no aparelho — é o que sustenta a
confiança do promotor no app.

```vue
<template>
  <q-page class="q-pa-md">
    <q-banner
      v-if="visita.pendingCount" class="bg-warning text-dark rounded-borders q-mb-md"
    >
      <template #avatar><q-icon name="cloud_off" /></template>
      {{ visita.pendingCount }} contagem(ns) aguardando envio neste aparelho.
      <template #action>
        <q-btn flat dense no-caps label="Enviar agora" :loading="visita.sending" @click="tryFlush" />
      </template>
    </q-banner>

    <div class="text-subtitle2 text-grey-7 q-mb-sm">Enviadas</div>

    <q-list separator class="rounded-borders bg-white">
      <q-item v-for="v in enviadas" :key="v.id">
        <q-item-section>
          <q-item-label>{{ v.customer_name }}</q-item-label>
          <q-item-label caption>
            {{ formatData(v.visited_at) }} · {{ v.items_count }} itens
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-icon
            :name="v.status === 'exported' ? 'task_alt' : 'check_circle'"
            :color="v.status === 'exported' ? 'positive' : 'primary'"
          />
        </q-item-section>
      </q-item>
    </q-list>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'
import { useOfflineQueue } from '@/composables/useOfflineQueue'

const visita = useVisitaStore()
const { tryFlush } = useOfflineQueue()
const enviadas = ref([])

const formatData = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR') : '—')

onMounted(async () => {
  const { items } = await merchandisingApi.myVisits({ limit: 50 })
  enviadas.value = items
})
</script>
```

---

## 18. Frontend — telas do administrador

Quatro telas, todas desktop-first. Elas **não migram** para o ERP na mesma forma — lá o
administrador já terá `MainLayout`, cadastro de clientes vindo do Firebird e tela de
vendedores. Só `AdminVisitasPage` (a que recebe as planilhas) migra como está.

### `pages/admin/AdminVisitasPage.vue` — recebe as planilhas

```vue
<template>
  <q-page class="q-pa-md">
    <div class="row items-center justify-between q-mb-md">
      <div class="text-h6">Contagens recebidas</div>
      <q-btn
        color="positive" icon="download" no-caps unelevated
        label="Baixar planilha do período" :loading="baixando"
        @click="exportarConsolidado"
      />
    </div>

    <!-- Filtros -->
    <q-card flat bordered class="q-mb-md">
      <q-card-section class="row q-col-gutter-md">
        <div class="col-12 col-md-3">
          <q-input v-model="filtros.date_from" outlined dense type="date" label="De" />
        </div>
        <div class="col-12 col-md-3">
          <q-input v-model="filtros.date_to" outlined dense type="date" label="Até" />
        </div>
        <div class="col-12 col-md-3">
          <q-select
            v-model="filtros.promoter_id" outlined dense clearable
            label="Promotor" :options="promotores"
            option-value="id" option-label="full_name" emit-value map-options
          />
        </div>
        <div class="col-12 col-md-3">
          <q-select
            v-model="filtros.status" outlined dense clearable
            label="Status" :options="['submitted', 'exported']"
          />
        </div>
      </q-card-section>
    </q-card>

    <q-table
      :rows="visitas" :columns="colunas" row-key="id"
      :loading="carregando" flat bordered
      v-model:pagination="paginacao" @request="carregar"
    >
      <template #body-cell-acoes="props">
        <q-td :props="props" class="text-right">
          <q-btn
            flat dense round icon="download" color="primary"
            :title="'Baixar planilha desta contagem'"
            @click="exportarUma(props.row.id)"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { merchandisingApi } from '@/api/merchandising'
import { usersApi } from '@/api/users'

const visitas = ref([])
const promotores = ref([])
const carregando = ref(false)
const baixando = ref(false)

const filtros = reactive({
  date_from: '', date_to: '', promoter_id: null, status: null,
})
const paginacao = ref({ page: 1, rowsPerPage: 25, rowsNumber: 0 })

const colunas = [
  { name: 'visited_at', label: 'Data', field: 'visited_at', align: 'left',
    format: (v) => (v ? new Date(v).toLocaleString('pt-BR') : '—') },
  { name: 'customer_name', label: 'Cliente', field: 'customer_name', align: 'left' },
  { name: 'promoter_name', label: 'Promotor', field: 'promoter_name', align: 'left' },
  { name: 'items_count', label: 'Itens', field: 'items_count', align: 'right' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

async function carregar(props) {
  const page = props?.pagination?.page || paginacao.value.page
  const rows = props?.pagination?.rowsPerPage || paginacao.value.rowsPerPage

  carregando.value = true
  try {
    const { items, total } = await merchandisingApi.visits({
      ...filtros, limit: rows, offset: (page - 1) * rows,
    })
    visitas.value = items
    paginacao.value = { page, rowsPerPage: rows, rowsNumber: total }
  } finally {
    carregando.value = false
  }
}

const exportarUma = (id) => merchandisingApi.exportVisit(id)

async function exportarConsolidado() {
  baixando.value = true
  try {
    await merchandisingApi.exportConsolidated(filtros)
  } finally {
    baixando.value = false
  }
}

onMounted(async () => {
  promotores.value = await usersApi.list({ role: 'promoter' })
  await carregar()
})
</script>
```

### `pages/admin/AdminVinculosPage.vue` — clientes por promotor

Duas colunas: promotores à esquerda; à direita, a lista de clientes com checkbox. Salvar
chama `PUT /merchandising/assignments/{promoter_id}` com o conjunto completo.

```vue
<template>
  <q-page class="q-pa-md row q-col-gutter-md">
    <div class="col-12 col-md-4">
      <q-card flat bordered>
        <q-card-section class="text-subtitle1">Promotores</q-card-section>
        <q-separator />
        <q-list separator>
          <q-item
            v-for="p in promotores" :key="p.id"
            clickable v-ripple :active="p.id === selecionado?.id"
            active-class="bg-blue-1"
            @click="selecionar(p)"
          >
            <q-item-section>
              <q-item-label>{{ p.full_name }}</q-item-label>
              <q-item-label caption>{{ p.email }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </div>

    <div class="col-12 col-md-8">
      <q-card flat bordered>
        <q-card-section class="row items-center justify-between">
          <div class="text-subtitle1">
            Clientes de {{ selecionado?.full_name || '—' }}
            <q-badge color="primary" class="q-ml-sm">{{ marcados.length }}</q-badge>
          </div>
          <q-btn
            color="primary" no-caps unelevated label="Salvar vínculos"
            :disable="!selecionado" :loading="salvando" @click="salvar"
          />
        </q-card-section>
        <q-separator />

        <q-card-section>
          <q-input v-model="busca" outlined dense clearable placeholder="Buscar cliente...">
            <template #prepend><q-icon name="search" /></template>
          </q-input>
        </q-card-section>

        <q-list separator style="max-height: 60vh; overflow-y: auto">
          <q-item v-for="c in filtrados" :key="c.id" tag="label" v-ripple>
            <q-item-section side top>
              <q-checkbox v-model="marcados" :val="c.id" :disable="!selecionado" />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ c.name }}</q-item-label>
              <q-item-label caption>{{ c.document || 'sem documento' }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { customersApi } from '@/api/customers'
import { usersApi } from '@/api/users'

const $q = useQuasar()

const promotores = ref([])
const clientes = ref([])
const selecionado = ref(null)
const marcados = ref([])
const busca = ref('')
const salvando = ref(false)

const filtrados = computed(() => {
  const term = busca.value?.trim().toLowerCase()
  if (!term) return clientes.value
  return clientes.value.filter(
    (c) => c.name.toLowerCase().includes(term) || (c.document || '').includes(term)
  )
})

async function selecionar(promotor) {
  selecionado.value = promotor
  marcados.value = await merchandisingApi.getAssignments(promotor.id)
}

async function salvar() {
  salvando.value = true
  try {
    await merchandisingApi.setAssignments(selecionado.value.id, marcados.value)
    $q.notify({ type: 'positive', message: 'Vínculos salvos.' })
  } finally {
    salvando.value = false
  }
}

onMounted(async () => {
  promotores.value = await usersApi.list({ role: 'promoter' })
  clientes.value = await customersApi.list()
})
</script>
```

### `pages/admin/AdminCadastrosPage.vue`

Abas com CRUD mínimo de **clientes**, **produtos**, **usuários (promotores)** e o **mix
por cliente** (`PUT /merchandising/customers/{id}/mix`). Use `q-table` com `q-dialog` de
edição — mesmo padrão de `fv-laticinios/frontend/src/pages/ClientesPage.vue`.

> Mantenha esta tela deliberadamente simples. Ela morre na fusão: no ERP, clientes e
> produtos virão do Firebird e essa manutenção manual deixa de existir.

---

## 19. Contrato completo da API

Prefixo `/merchandising` em tudo que é domínio de coleta (Âncora 6).

### Promotor

| Método | Rota | Papéis | Descrição |
|---|---|---|---|
| `GET` | `/merchandising/my-customers?search=` | promoter, admin | Clientes atribuídos + data da última contagem |
| `GET` | `/merchandising/customers/{id}/products?search=` | promoter, admin | Mix do cliente (ou catálogo completo) + quantidade anterior |
| `POST` | `/merchandising/visits` | promoter, admin | Cria/atualiza contagem. **Idempotente** via `client_uuid` |
| `POST` | `/merchandising/visits/{id}/submit` | promoter, admin | Fecha a contagem |
| `GET` | `/merchandising/visits/mine?status=&limit=&offset=` | promoter, admin | Histórico do próprio promotor |

### Administrador

| Método | Rota | Papéis | Descrição |
|---|---|---|---|
| `GET` | `/merchandising/visits?promoter_id=&customer_id=&status=&date_from=&date_to=` | admin | Lista paginada |
| `GET` | `/merchandising/visits/{id}` | admin, promoter | Detalhe com itens |
| `GET` | `/merchandising/visits/{id}/export.xlsx` | admin | Planilha de uma contagem |
| `GET` | `/merchandising/exports.xlsx?...` | admin | Planilha consolidada do período |
| `GET` | `/merchandising/assignments/{promoter_id}` | admin | IDs de clientes do promotor |
| `PUT` | `/merchandising/assignments/{promoter_id}` | admin | Substitui o conjunto de clientes |
| `PUT` | `/merchandising/customers/{id}/mix` | admin | Define o mix de produtos do cliente |

### Fora do prefixo (cadastros temporários + auth)

```
POST   /auth/login            POST /auth/refresh          GET /auth/me
GET    /customers             POST /customers             PUT /customers/{id}
GET    /products              POST /products              PUT /products/{id}
GET    /users?role=promoter   POST /users                 PUT /users/{id}/password
GET    /health
```

### Exemplo de payload — `POST /merchandising/visits`

```json
{
  "customer_id": "3f2a...",
  "client_uuid": "b1e6c0d2-9f4a-4c17-8f0b-2a5d7e91c3aa",
  "visited_at": "2026-08-05T09:30:00Z",
  "notes": "Gôndola em reforma, parte do mix fora de exposição",
  "submit": true,
  "items": [
    { "product_id": "aa11...", "quantity": 12,   "expires_at": "2026-09-30" },
    { "product_id": "bb22...", "quantity": 0,    "notes": "ruptura" },
    { "product_id": "cc33...", "quantity": 6.5 }
  ]
}
```

Reenviar exatamente este JSON **não cria uma segunda contagem** — a constraint
`uq_stock_visits_client_uuid` garante o `UPDATE`.

---

## 20. Playbook da fusão com o ERP

Execute quando o ERP `fv-laticinios` estiver em produção com clientes e produtos
sincronizados do Firebird.

### Passo 1 — Pré-casamento dos cadastros ⚠️ **faça o quanto antes, não no fim**

Assim que o ERP tiver dados reais, exporte clientes e produtos dele para uma tabela
temporária no banco do app standalone e case pela chave natural — `document` para
cliente, `sku` para produto — para preencher `external_id`. Cadastro que não casar é
divergência entre os dois sistemas, e precisa ser resolvida à mão antes da fusão.

```sql
-- No banco do app standalone, após importar o extrato do ERP:
UPDATE customers c
SET    external_id = e.erp_id
FROM   erp_customers_tmp e
WHERE  c.document = e.document
  AND  c.tenant_id = '<tenant>';

-- Conferência: quem ficou de fora precisa de decisão manual
SELECT name, document FROM customers
WHERE external_id IS NULL AND tenant_id = '<tenant>';
```

**Este passo decide se a fusão custa dias ou meses.** Quanto mais tempo os dois cadastros
divergirem sem casamento, maior a lista de órfãos.

### Passo 2 — Código do módulo

```bash
cp -r fv-estoque/backend/app/merchandising \
      fv-laticinios/backend/app/merchandising
cp fv-estoque/backend/app/infrastructure/persistence/models/stock_visit.py \
   fv-laticinios/backend/app/infrastructure/persistence/models/
```

Ajustes no código copiado:

- `stock_visits` ganha `seller_id` (FK para `sellers`), preenchido a partir de
  `sellers.user_id`.
- `MerchandisingRepository` troca `PromoterCustomer` por `SellerCustomer` com
  `link_type='promotor'`, e o join passa por `sellers.user_id == User.id`.
- `customers/` e `products/` do standalone são **descartados**; o ERP já tem os seus.

### Passo 3 — Migrações no ERP

Duas revisões separadas (o Postgres não deixa usar um valor de enum na mesma migração
que o adiciona):

```python
# 0XX_promoter_role.py
def upgrade():
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'promoter'")

# 0XX+1_stock_visits.py  → cria stock_visits e stock_visit_items
#   (copie de fv-estoque/backend/alembic/versions/001_initial.py,
#    acrescentando a coluna seller_id)
```

Encadeie `down_revision` na última revisão do ERP na data da fusão.

### Passo 4 — Migração de dados

Ordem obrigatória (respeita as FKs):

| # | Origem (standalone) | Destino (ERP) | Chave de casamento |
|---|---|---|---|
| 1 | `users` (role=promoter) | `users` | `email` |
| 2 | — | `sellers` | criar com `user_id` do passo 1, `role='operador'` |
| 3 | `promoter_customers` | `seller_customers` | `link_type='promotor'` |
| 4 | `customer_products` | (opcional) | só se quiser manter o mix manual |
| 5 | `stock_visits` | `stock_visits` | **preserva o `id` original** |
| 6 | `stock_visit_items` | `stock_visit_items` | `product_id` via `external_id`/`sku` |

Nos passos 5 e 6, traduza `customer_id` e `product_id` para os UUIDs do ERP usando o
mapa construído no passo 1. Mantenha os UUIDs de `stock_visits.id` — assim qualquer
referência externa (link, planilha já baixada) continua válida.

### Passo 5 — Frontend

```bash
cp -r fv-estoque/frontend/src/pages/promotor \
      fv-laticinios/frontend/src/pages/promotor
cp fv-estoque/frontend/src/api/merchandising.js       fv-laticinios/frontend/src/api/
cp fv-estoque/frontend/src/stores/visita.js           fv-laticinios/frontend/src/stores/
cp fv-estoque/frontend/src/composables/useOfflineQueue.js \
   fv-laticinios/frontend/src/composables/
cp fv-estoque/frontend/src/layouts/PromotorLayout.vue fv-laticinios/frontend/src/layouts/
```

Três edições em arquivos compartilhados, e só três:

1. `router/index.js` — importar e espalhar `...promotorRoutes` no array `routes`.
2. `MainLayout.vue` — dois `q-item` no menu (Contagens recebidas, Vínculos de promotor),
   com `v-if="user?.role === 'admin'"`.
3. `main.py` — um `app.include_router(merchandising_router)`.

### Passo 6 — Desligar o standalone

Só depois de conferir que as contagens migradas aparecem corretamente no ERP e que uma
planilha exportada de lá bate com uma exportada do standalone. Mantenha o banco antigo
em backup por pelo menos um ciclo de fechamento.

---

## 21. Roadmap de execução

| Fase | Entrega | Critério de pronto |
|---|---|---|
| **1** | Esqueleto: docker-compose, fundação copiada, `001_initial`, seed | `make up && make migrate && make seed`; login funciona em `/docs` |
| **2** | Cadastros mínimos (clientes, produtos, promotores) | Admin cadastra os clientes e produtos reais da empresa pela tela |
| **3** | Vínculos promotor↔cliente + mix por cliente | Um promotor de teste vê só os clientes dele |
| **4** | PWA do promotor: clientes → produtos → contagem → enviar | Contagem completa gravada no banco pelo celular |
| **5** | Export `.xlsx` (por visita + consolidado) | Admin baixa a planilha e ela abre corretamente no Excel |
| **6** | Fila offline + reenvio automático | Contagem feita em modo avião sobe sozinha ao voltar o sinal |
| **7** | Piloto com 1–2 promotores em campo | Uma semana de uso real sem perda de dados |
| **8** | Rollout para todos os promotores | — |

As fases 1–5 entregam o fluxo completo descrito. **A fase 6 é o que decide se o app
sobrevive ao uso real** em supermercado. Não pule para a 8 sem a 7.

### Deploy de produção

O ERP serve o frontend em sub-path (`/fv-laticinios/`) atrás do nginx. O app novo pode
ficar em um subdomínio próprio (`estoque.suaempresa.com.br`) com `base: '/'`, que é mais
simples e não conflita.

**HTTPS é obrigatório**, não opcional: PWA instalável e service worker só funcionam em
contexto seguro. Use Let's Encrypt via nginx ou Caddy.

---

## 22. Riscos e divergências deliberadas

### Riscos reconhecidos

**1. Dois cadastros de cliente/produto vivos em paralelo.**
Alguém vai cadastrar um cliente novo no ERP e esquecer do app, ou vice-versa. É o preço
de não esperar o ERP — e provavelmente vale a pena.
*Mitigação:* passo 1 do playbook o quanto antes; CRUD manual deliberadamente pobre para
que a planilha seja sempre a via de entrada.

**2. Perda de contagem por falha de rede.**
O cenário real: gôndola de supermercado, 40 produtos digitados, sinal ruim.
*Mitigação:* fase 6 (fila offline). Não vá a campo sem ela.

**3. Divergência de schema ao longo do tempo.**
O ERP continua evoluindo enquanto o app roda. Uma coluna renomeada em `customers` do
lado de lá cria trabalho na fusão.
*Mitigação:* revisar as Âncoras 4 e 5 sempre que o ERP mexer em `customers`, `products`
ou `users`.

**4. Escopo do admin inchar.**
A tentação de transformar o app standalone num mini-ERP é real e destruiria a premissa
do projeto.
*Mitigação:* qualquer funcionalidade que não seja "coletar estoque e entregar planilha"
deve ser recusada e anotada para o ERP.

### Divergências deliberadas em relação ao ERP

Registradas aqui para que ninguém as "conserte" por engano:

| Item | Divergência | Motivo |
|---|---|---|
| `products.is_active` | Coluna não existe no ERP | O catálogo manual precisa de desativação; colunas extras não quebram a fusão |
| `promoter_customers` | O ERP usa `seller_customers` via `sellers` | Não existe tabela `sellers` no standalone; conversão no passo 4 do playbook |
| `users.profile` / `preferences` | Removidas | Sem uso no MVP |
| PWA `registerType` | `prompt` em vez de `autoUpdate` | Recarregar sozinho pode descartar uma contagem em digitação |
| Token expira em 8h | ERP usa 60 min | Jornada de campo inteira sem reautenticar |
| Sem Celery/Redis | ERP tem | Geração de planilha sob demanda é rápida o bastante |

### Três decisões de produto assumidas

Defaults adotados neste plano. Se algum estiver errado, ajuste antes da fase 3:

1. **Quais produtos aparecem ao abrir um cliente** — o mix cadastrado em
   `customer_products`; sem mix, o catálogo completo.
2. **Formato da planilha** — os dois: por visita e consolidada por período, mesma função
   de geração, admin escolhe.
3. **Cliente novo** — cadastrado pelo admin, na tela de Cadastros. O promotor
   **não** cadastra clientes (prospecção fica para o `prospect_customers` do ERP).

---

## Referências no código do ERP

Arquivos consultados para produzir este plano, úteis como modelo ao implementar:

| Assunto | Arquivo no `fv-laticinios` |
|---|---|
| Padrão de módulo completo | `backend/app/sales_routes/{routes,service,repository,schemas}.py` |
| Auth e formato do token | `backend/app/auth/service.py:44` |
| Guardas de papel | `backend/app/core/dependencies.py` |
| Middleware CORS | `backend/app/main.py:41` |
| Migração que adiciona valor a enum | `backend/alembic/versions/020_supervisor_role.py` |
| Migração com tabelas novas | `backend/alembic/versions/019_sales_routes.py` |
| Vínculo pessoa de campo ↔ cliente | `backend/app/infrastructure/persistence/models/seller_customer.py` |
| Refresh de token no axios | `frontend/src/api/client.js:44` |
| Guard de rotas por papel | `frontend/src/router/index.js:117` |
| Padrão de módulo de API no front | `frontend/src/api/salesRoutes.js` |
| Configuração PWA | `frontend/vite.config.js` |

