# Coleta de Estoque do Promotor

App standalone de coleta de estoque em ponto de venda, construído para ser
incorporado ao ERP `fv-laticinios` no futuro com o menor custo possível de fusão.

A arquitetura, as decisões e o playbook da fusão estão em
[`PLANO_APP_ESTOQUE_PROMOTOR.md`](PLANO_APP_ESTOQUE_PROMOTOR.md). **Leia-o antes de
mexer no schema ou renomear qualquer coisa** — várias escolhas aqui parecem
arbitrárias e não são (as "6 âncoras", seção 3 do plano).

## O fluxo

**Promotor** (celular, PWA): clientes → produtos → digita o estoque → envia.
**Administrador** (desktop): cadastra clientes/produtos, define quais clientes cada
promotor atende, e baixa as contagens em planilha `.xlsx`.

## Stack

| Camada | Tecnologia |
|---|---|
| API | FastAPI (`routes → service → repository`) |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Migrações | Alembic |
| Banco | PostgreSQL 16 (porta 5434) |
| Auth | JWT (python-jose) + bcrypt |
| App | Vue 3 + Quasar 2 + Pinia + Vite (PWA) |
| Excel | openpyxl |

Portas escolhidas para não colidir com o ERP rodando na mesma máquina:
API `8002`, web `5174`, Postgres `5434`.

## Subir o ambiente

```bash
cp .env.example .env
docker compose up -d --build
make migrate
make seed
```

- API e documentação: http://localhost:8002/docs
- App web: http://localhost:5174

Usuários criados pelo `seed`:

| Usuário | Senha | Papel |
|---|---|---|
| `admin` | `admin` | administrador |
| `promotor` | `promotor` | promotor |

## Primeiro uso

1. Entre como `admin`.
2. **Importar planilhas** → baixe a planilha-modelo, preencha e importe clientes e
   produtos. (Ou cadastre manualmente em **Cadastros** — mas a planilha é a via
   pensada para volume.)
3. **Cadastros → Promotores** → crie o promotor com e-mail e senha.
4. **Clientes por promotor** → marque quais clientes ele atende e salve.
5. *(Opcional)* **Cadastros → Mix por cliente** → escolha quais produtos são
   contados em cada cliente. Sem mix, o promotor vê o catálogo completo.
6. Entre como o promotor (de preferência no celular) e faça uma contagem.
7. Volte ao admin em **Contagens recebidas** e baixe a planilha.

## Comandos

```bash
make up        # sobe os containers
make down      # derruba
make logs      # acompanha os logs
make migrate   # aplica as migrações
make seed      # cria tenant, admin e promotor de teste
make reset-db  # zera o banco e refaz migrate + seed
make shell     # bash dentro do container da API
```

## Testar no celular durante o desenvolvimento

O `vite.config.js` já expõe o dev server em `0.0.0.0:5174` e o CORS da API aceita
IPs de rede local. Acesse `http://<ip-da-maquina>:5174` pelo Wi-Fi.

Para instalar como PWA de verdade (e testar o modo offline com service worker) é
preciso **HTTPS** — em produção, use Let's Encrypt via nginx ou Caddy.

## Estrutura

```
backend/app/
├── core/            # config, security e dependencies (os dois últimos, cópias do ERP)
├── auth/            # login, refresh, /me
├── infrastructure/  # base, session, types e os 7 models
├── customers/       # cadastro temporário — MORRE na fusão
├── products/        # cadastro temporário — MORRE na fusão
├── users/           # o admin cria promotores
└── merchandising/   # ← O CORAÇÃO. Migra inteiro para o ERP.

frontend/src/
├── api/             # client.js (cópia do ERP), merchandising, customers, products, users
├── stores/          # auth e user (cópias do ERP), visita (rascunho + fila offline)
├── composables/     # useOfflineQueue — reenvia quando a conexão volta
├── layouts/         # PromotorLayout (mobile) e AdminLayout (desktop)
└── pages/
    ├── promotor/    # ← migra como bloco para o ERP
    └── admin/
```

**Regra de ouro:** toda lógica de coleta de estoque vive em `app/merchandising/` e
`pages/promotor/`. Nada de regra de negócio do promotor espalhada em `customers/`
ou `products/` — se a fronteira estiver limpa, a fusão é copiar duas pastas.

## Detalhes que não são acidentais

- **`tenant_id` em toda tabela e em toda query**, mesmo sendo uma empresa só.
  Adicionar isso depois custa migração + backfill + revisão de todas as queries.
- **UUID como PK.** IDs sequenciais colidiriam com os do ERP na fusão.
- **`document` (só dígitos) e `sku`** são as chaves naturais que casam os cadastros
  no dia da integração. `external_id` nasce vazio e recebe o ID do Firebird.
- **`client_uuid` nas visitas.** O celular gera o UUID; reenviar a mesma contagem
  faz `UPDATE`, não duplica. É o que salva a contagem feita com sinal ruim.
- **Prefixo `/merchandising`** em todas as rotas do domínio de coleta, para que o
  frontend não mude uma linha de URL na fusão.
- **PWA com `registerType: 'prompt'`** (o ERP usa `autoUpdate`): recarregar sozinho
  poderia descartar uma contagem em digitação.
- **Token de 8 horas** (o ERP usa 60 min): cobre uma jornada de campo inteira.

## Divergências deliberadas em relação ao ERP

Registradas para que ninguém as "conserte" por engano — a lista completa e os
motivos estão na seção 22 do plano.

| Item | Divergência |
|---|---|
| `products.is_active` | Coluna não existe no ERP (colunas extras não quebram a fusão) |
| `promoter_customers` | O ERP usa `seller_customers` via `sellers` |
| `users.profile` / `preferences` | Removidas — sem uso no MVP |
| Sem Celery/Redis/Firebird | Geração de planilha sob demanda é rápida o bastante |
