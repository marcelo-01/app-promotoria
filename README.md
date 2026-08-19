# Coleta de Estoque do Promotor

App standalone de coleta de estoque em ponto de venda, construído para ser
incorporado ao ERP `fv-laticinios` no futuro com o menor custo possível de fusão.

A arquitetura, as decisões e o playbook da fusão estão em
[`PLANO_APP_ESTOQUE_PROMOTOR.md`](PLANO_APP_ESTOQUE_PROMOTOR.md). **Leia-o antes de
mexer no schema ou renomear qualquer coisa** — várias escolhas aqui parecem
arbitrárias e não são (as "6 âncoras", seção 3 do plano).

## O fluxo

**Promotor** (celular, PWA): escolhe o cliente → escolhe **gôndola** ou **estoque** →
um produto por tela (foto grande na metade de cima, dois campos embaixo: **caixas**
e **unidades avulsas**) → envia. Produto sem nenhum número digitado não é enviado.
Enviou, o cliente ganha um **visto verde** naquele tipo de contagem, que some
sozinho na virada do dia.

**Administrador** (desktop): cadastra clientes (só o nome), produtos (nome, foto e
quantas unidades vêm numa caixa) e promotores (nome, e-mail e senha), define quais
clientes cada promotor atende, e baixa as contagens em planilha `.xlsx` — já com
as caixas convertidas em unidades.

Gôndola e estoque do mesmo cliente são contagens independentes: cada uma tem sua
data, sua planilha, sua "contagem anterior" e seu visto do dia.

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
| Fotos | Pillow — gravadas em `backend/uploads/`, servidas em `/uploads/` |

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
2. **Cadastros → Clientes** e **→ Produtos** → cadastre os clientes (só o nome) e os
   produtos (nome + foto + unidades por caixa). A foto é o que o promotor usa para
   reconhecer a embalagem na gôndola, então vale tirar uma boa; as unidades por
   caixa são o que converte a contagem na planilha (produto vendido só a granel
   fica com 1).
3. **Cadastros → Promotores** → crie o promotor com nome, e-mail e senha.
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
preciso **HTTPS** — que o deploy atual não tem. Ver "O que este deploy não faz".

## Deploy em produção

A stack de produção é outra: `docker-compose.prod.yml`. Ela não monta o código do
host, não roda `--reload` e serve o frontend compilado por nginx. Só o nginx
publica porta (80); API e banco ficam na rede interna do compose.

```
internet → nginx :80 (SPA + /api/) → api → db
```

O app roda numa **VPS Linux dedicada a ele**. O passo a passo de instalar a VPS
do zero — Docker, firewall, chave de deploy, backup automático — está em
[`DEPLOY_VPS.md`](DEPLOY_VPS.md). O que vem abaixo é a stack em si, que serve
para qualquer hospedeiro.

**Em HTTP puro, sem TLS.** Não é descuido: o app é alcançado por IP, sem domínio,
e Let's Encrypt não emite certificado para endereço IP. A alternativa seria uma
CA própria com o certificado instalado à mão em cada celular, o que foi
descartado. O `Caddyfile` continua no repositório e documenta o caminho de volta
para quando houver um domínio.

### Configurar

```bash
cp .env.example .env
```

Depois edite o `.env`. Estes cinco são o deploy inteiro:

| Variável | O que pôr | Se errar |
|---|---|---|
| `API_ENV` | `production` | Deixa `/docs` aberto e o CORS frouxo |
| `SECRET_KEY` | `openssl rand -hex 32` | **A API se recusa a subir** |
| `POSTGRES_PASSWORD` (e a mesma em `DATABASE_PASSWORD` e dentro de `DATABASE_URL`) | `openssl rand -hex 16` | **A API se recusa a subir** |
| `VITE_API_URL` | `/api` | O app quebra em todo celular, sem erro no servidor |
| `FRONTEND_URL` | o endereço exato pelo qual o navegador abre o app (`http://<ip>`) | O download da planilha falha por CORS |

As duas primeiras são checadas na largada: subir com as credenciais do
`.env.example` derruba a API com o motivo na primeira linha do log. Isso é de
propósito — a `SECRET_KEY` de exemplo está publicada neste repositório, e com ela
qualquer um forja um token de administrador.

### O que este deploy não faz

Servir em HTTP puro tem três consequências, todas aceitas de olhos abertos:

1. **Não instala como aplicativo no Android.** O Chrome só oferece "Instalar" em
   contexto seguro. Dá para "Adicionar à tela inicial", mas o ícone abre o
   Chrome com a barra de endereço à mostra, em vez de tela cheia. No iPhone o
   Safari abre em tela cheia assim mesmo, por causa do
   `apple-mobile-web-app-capable` que já está no `index.html`.

2. **O app não abre sem sinal.** Sem contexto seguro o service worker não
   registra, e nada é guardado em cache. A fila offline do `useOfflineQueue.js`
   continua funcionando — ela é JavaScript comum e não depende de service
   worker —, mas só enquanto a página seguir aberta: recarregar ou reabrir o app
   sem rede cai na tela de erro do navegador.

3. **Senha e token trafegam em claro**, inclusive no Wi-Fi do supermercado.

As três somem no dia em que houver um domínio, sem refazer o deploy. O caminho
de volta está no `Caddyfile`.

### Subir

```bash
make prod-up      # build + up -d
make prod-seed    # SÓ NA PRIMEIRA VEZ: cria o tenant e o usuário admin
make prod-logs
```

As migrações rodam sozinhas toda vez que a API sobe — não há passo manual de
`alembic` no deploy.

### Logo depois da primeira subida

1. Entre como `admin` / `admin`.
2. **Troque a senha na hora**, no menu do canto superior direito → *Trocar minha
   senha*. Enquanto não trocar, o app está com a senha que está escrita neste
   README.

### Atualizar depois

```bash
git pull && make prod-up
```

O `--build` refaz as imagens e as migrações pendentes sobem junto. Fotos
(`estoque_uploads`) e banco (`estoque_pg_data`) estão em volumes e sobrevivem ao
redeploy.

### Backup

```bash
make prod-backup   # banco + fotos em ./backups
```

Roda o `pg_dump` e empacota as fotos. **Copie os arquivos para fora do servidor** —
os volumes moram no mesmo disco e somem junto com ele. Um `cron` diário resolve:

```cron
0 2 * * * cd /caminho/do/app-promotoria && make prod-backup
```

Para voltar um dump: `make prod-restore f=backups/banco_AAAAMMDD_HHMMSS.sql.gz`.

### Onde o app é hospedado

| Hospedeiro | Runbook | Situação |
|---|---|---|
| VPS Linux | [`DEPLOY_VPS.md`](DEPLOY_VPS.md) | **Em uso** |
| PC Windows do escritório | [`DEPLOY_WINDOWS.md`](DEPLOY_WINDOWS.md) | Plano B, não adotado |

O app não muda entre um e outro — o que muda é o hospedeiro.

### Comandos de produção

```bash
make prod-up       # sobe (com build)
make prod-down     # derruba
make prod-logs     # acompanha os logs
make prod-ps       # estado dos contêineres
make prod-migrate  # aplica migrações sem reiniciar
make prod-seed     # cria tenant + admin (só na primeira vez)
make prod-shell    # bash dentro do container da API
make prod-backup   # banco + fotos em ./backups
```

Os alvos sem o prefixo `prod-` falam com o compose de **desenvolvimento** e não
fazem nada de útil no servidor.

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
  no dia da integração. Continuam nas tabelas mesmo sem ninguém as digitar hoje —
  o cadastro deste app pede só o nome. `external_id` nasce vazio e recebe o ID do
  Firebird.
- **Foto do produto em disco, não em base64 no banco.** A tela de contagem carrega
  o catálogo inteiro de uma vez; foto embutida no JSON inviabilizaria isso no sinal
  de um supermercado. Em disco, o service worker cacheia cada foto e a contagem
  funciona offline.
- **`visit_type` (`gondola`/`estoque`) na visita.** O promotor conta os dois lugares
  separadamente.
- **`boxes` e `units` no item, e `quantity` com o total convertido.** O cliente tem
  "1 caixa e 5 unidades" do mesmo produto — não uma coisa ou outra. Os dois números
  ficam gravados como foram digitados; `quantity` guarda
  `boxes * products.package_size + units`, que é o número que a planilha entrega.
  A planilha refaz essa conta com o `package_size` de hoje, para que corrigir o
  cadastro do produto conserte também as contagens já recebidas. `unit_type`
  sobreviveu como coluna, sempre `unidade` — é a unidade de `quantity`.
- **O "contado hoje" é uma data, não um flag.** O visto verde no card do cliente
  compara a data do último envio com a de hoje. Ninguém zera nada às 00:00: a marca
  de ontem simplesmente deixa de ser a de hoje. Vale a marca local do aparelho
  (aparece na hora, funciona offline) ou a data que veio do servidor (cobre a
  contagem feita em outro aparelho).
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
