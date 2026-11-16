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
sozinho na virada do dia. Antes do primeiro produto há um quadrado só — **"não tem
produtos aqui"** — para o lugar que hoje está vazio: é o que fecha a contagem sem
inventar número nenhum.

**Vendedor** (celular): escolhe o cliente e vê o **pedido sugerido** — os
produtos em ordem alfabética, cada um com a conta aberta embaixo (venda, estoque, o
ciclo de onde a venda saiu e, se o promotor leu, as datas de validade na loja), e no
rodapé a data da última coleta de estoque. A
sugestão é

    sugestão = venda × fator de giro − estoque atual

onde a venda é a mesma da coleta de vencimento (o que saiu pelo caixa entre as
duas últimas coletas completas do promotor) e o **fator de giro** (1 a 3, uma
casa decimal) é o vendedor quem define, **produto a produto em cada loja**, no
campo da própria linha: 1 repõe o que vendeu, 2 dobra a cobertura. Produto em
que ele ainda não mexeu **começa em 2** — repor o que saiu é o pedido mais
conservador que existe, e é mais fácil discordar de um número cheio do que
lembrar de subir um tímido. Os produtos que a loja ainda cobre ficam numa seção
recolhida embaixo, "Sem sugestão", com o mesmo campo — é por ali que ele sobe o
fator de um produto que quer pedir mesmo assim. **Toda semana a tela zera**:
sugestão só vale se a coleta que a gerou for do domingo mais recente em diante
— coleta da semana passada mostra um aviso no lugar da lista, para ninguém
lançar um pedido em cima de número velho.

Havendo pedido, uma barra no rodapé mostra o total (itens e unidades) e **baixa a
folha em PDF** para o vendedor entregar ao comprador da loja: cabeçalho com o
cliente, uma linha por produto com unidades e caixas, e espaço para observações e
assinatura. Só os produtos com sugestão maior que zero entram, e a conta aberta
fica de fora — o fator de giro é a aposta do vendedor sobre a loja, não assunto de
quem compra.

**Administrador** (desktop): cadastra clientes (só o nome), produtos (nome, foto e
quantas unidades vêm numa caixa), promotores e vendedores (nome, e-mail e senha),
define quais clientes cada um atende, e baixa as contagens em planilha `.xlsx` —
já com as caixas convertidas em unidades.

Gôndola e estoque do mesmo cliente são contagens independentes para o promotor:
cada uma tem sua tela, sua "contagem anterior" e seu visto do dia. Para o
administrador, não: **a planilha é uma só, com os dois lados lado a lado** (uma
linha por produto: gôndola, estoque, total) e **só sai quando as duas contagens
chegam** — mesmo cliente, mesmo promotor, mesmo dia. Enquanto faltar uma, a outra
aparece como *aguardando* em **Contagens recebidas** e não entra em planilha
nenhuma.

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
| `vendedor` | `vendedor` | vendedor |

## Primeiro uso

1. Entre como `admin`.
2. **Cadastros → Clientes** e **→ Produtos** → cadastre os clientes (nome e CNPJ) e os
   produtos (nome + código do ERP + foto + unidades por caixa). A foto é o que o
   promotor usa para reconhecer a embalagem na gôndola, então vale tirar uma boa; as
   unidades por caixa são o que converte a contagem na planilha (produto vendido só a
   granel fica com 1). O CNPJ e o código do ERP são opcionais, mas é por eles que as
   notas do ERP entram (ver [Faturamento e brindes do ERP](#faturamento-e-brindes-do-erp)).
3. **Cadastros → Promotores** (e **→ Vendedores**) → crie a pessoa com nome, e-mail e senha.
   Quem conta a loja **e** lança o pedido é uma pessoa só, com um login: marque
   "Também é vendedor" (ou "Também é promotor") ao criar, ou ligue o interruptor na
   linha dela depois. Ela cai no app da aba em que foi criada e troca para o
   outro pelo menu, sem sair.
4. **Clientes por promotor/vendedor** → marque quais clientes cada um atende e salve.
   O vendedor vê o pedido sugerido só dos clientes vinculados a ele. Quem tem os
   dois papéis aparece nas duas listas com os mesmos clientes — o vínculo é da
   pessoa, não do papel.
5. *(Opcional)* **Cadastros → Mix por cliente** → escolha quais produtos são
   contados em cada cliente. Sem mix, o promotor vê o catálogo completo.
6. Entre como o promotor (de preferência no celular) e faça as **duas** contagens
   do cliente — gôndola e estoque. No lugar que estiver vazio, marque o quadrado
   "não tem produtos aqui" em vez de deixar em branco.
7. Volte ao admin em **Contagens recebidas** e baixe a planilha.
8. Entre como o vendedor, escolha o cliente e veja a sugestão — ela só aparece a
   partir da **segunda** coleta completa do cliente, porque é da diferença entre
   duas que sai a venda. O fator de giro se ajusta no campo de cada produto, e a
   barra do rodapé baixa o pedido em PDF.

## Faturamento e brindes do ERP

A venda de um produto num cliente sai da diferença entre duas contagens **mais o
que entrou entre elas**: o faturamento e os brindes do ERP. Essas notas chegam
sozinhas, como no BI Mais Vida e no EFFEX Trade: o computador da empresa lê a
cópia do banco do ERP (Firebird) e manda para o app.

```
  cópia do banco do ERP     sync\sincronizar-faturamento-e-brindes.bat      app
  (Firebird, ~7 GB)    ──►  lê as notas de venda e de brinde dos     ──►    troca as entradas
                            últimos 120 dias e manda (~0,5 MB)              do período inteiro
```

- **O que vai:** as notas não canceladas a cliente (`VENDAS`/`LISTAVENDA` e
  `BRINDES`/`LISTABRINDE`, só `TIPOCLIENTE = 'CLIENTE'`) dos 120 dias que terminam
  no último dia com venda na cópia, com as peças de cada produto (`NUM_PECAS`), o
  CFOP, a empresa e o motivo do brinde.
- **O que entra:** as regras das planilhas que a sincronização substituiu. No
  faturamento, CFOP de saída (5xxx e 6xxx); no brinde, só a remessa ao cliente
  (5910 e 6910), sem transferência, retorno e perda. O cliente casa pelo **CNPJ** e
  o produto pelo **código do ERP**; o que não casa vira a lista de tarefas da tela
  **Faturamento do ERP**, que também diz se os números estão em dia.
- **Como grava:** cada envio troca as entradas do período inteiro, numa transação
  só. A nota cancelada ou corrigida no ERP some ou muda no envio seguinte, e rodar
  de novo não duplica nada.
- **Freios:** o pacote vai assinado com HMAC-SHA256 (a chave nunca trafega); pacote
  com hora de envio igual ou anterior à do último aceito é recusado; e o envio que
  deixaria o período com menos da metade das entradas de hoje (cópia do banco
  incompleta) só passa confirmado com `--forcar`.

**No computador da empresa** — o mesmo do BI e do EFFEX, que já tem o Python, o
`fdb` e o Firebird:

1. Copie `sync\config.exemplo.ini` para `sync\config.ini` e preencha a senha do
   banco (a mesma do `config.ini` do EFFEX) e, em `[envio] chave`, a mesma
   `ERP_SYNC_KEY` do servidor.
2. Dois cliques em `sync\sincronizar-faturamento-e-brindes.bat` depois de cada cópia
   nova do banco. Leva uns 10 segundos e mostra o resumo; cada execução deixa uma
   linha em `sync\sincronizar.log`.

Com `--sem-enviar`, o `.bat` só lê a cópia e mostra o resumo, sem mandar nada.

**No servidor:** `ERP_SYNC_KEY` no `.env` (ver [Configurar](#configurar)) e
`make prod-up`. Sem ela, a rota que recebe o pacote (`POST
/merchandising/erp/sync`) responde 503 e nada entra.

| O `.bat` mostra | O que fazer |
|---|---|
| `sem conexão com https://estoque.maisvida.cloud/api` | A internet do PC caiu ou o app está fora do ar. Tente abrir o app no navegador. |
| `o relógio do computador que envia está mais de 15 minutos diferente do servidor` | Acerte a hora do Windows: Configurações › Hora e idioma › Sincronizar agora. |
| `Assinatura inválida` | A `chave` do `sync\config.ini` não é a `ERP_SYNC_KEY` do `.env` do servidor. |
| `Sincronização desligada` | Falta a `ERP_SYNC_KEY` no `.env` do servidor (e o `make prod-up` depois). |
| `O envio deixaria o faturamento ... com N entradas, e hoje há M` | Confira se a cópia do banco terminou de ser gravada. Se a queda for de propósito (clientes ou produtos saíram do app), rode com `--forcar`. |
| `falha ao ler o banco` | O problema é no PC: o serviço *Firebird Server - DefaultInstance* parado, ou a cópia ainda sendo gravada. |
| `o servidor ainda não tem a sincronização` | O app no servidor está na versão anterior: publique a nova. |

Para testar no computador: `ERP_SYNC_KEY` no `.env` de desenvolvimento, a mesma em
`chave` no `sync\config.ini` e `destino = http://localhost:8002` lá; `make up` e o
`.bat`.

## Comandos

```bash
make up        # sobe os containers
make down      # derruba
make logs      # acompanha os logs
make migrate   # aplica as migrações
make seed      # cria tenant, admin, promotor e vendedor de teste
make reset-db  # zera o banco e refaz migrate + seed
make shell     # bash dentro do container da API
```

## Testar no celular durante o desenvolvimento

O `vite.config.js` já expõe o dev server em `0.0.0.0:5174` e o CORS da API aceita
IPs de rede local. Acesse `http://<ip-da-maquina>:5174` pelo Wi-Fi.

Para instalar como PWA de verdade (e testar o modo offline com service worker) é
preciso **HTTPS** — em produção isso já vem pronto, ver a seção abaixo.

## Deploy em produção

A stack de produção é outra: `docker-compose.prod.yml`. Ela não monta o código do
host, não roda `--reload`, serve o frontend compilado por nginx e põe um **Caddy**
na frente para o TLS. Só o Caddy publica porta (80 e 443); API, banco e nginx
ficam na rede interna do compose.

```
internet → caddy (TLS) → nginx (SPA + /api/) → api → db
```

O app roda numa **VPS Linux dedicada a ele**. O passo a passo de instalar a VPS
do zero — Docker, domínio, firewall, chave de deploy, backup automático — está em
[`DEPLOY_VPS.md`](DEPLOY_VPS.md). O que vem abaixo é a stack em si, que serve
para qualquer hospedeiro.

### Configurar

```bash
cp .env.example .env
```

Depois edite o `.env`. Estes são o deploy inteiro:

| Variável | O que pôr | Se errar |
|---|---|---|
| `API_ENV` | `production` | Deixa `/docs` aberto e o CORS frouxo |
| `SECRET_KEY` | `openssl rand -hex 32` | **A API se recusa a subir** |
| `POSTGRES_PASSWORD` (e a mesma em `DATABASE_PASSWORD` e dentro de `DATABASE_URL`) | `openssl rand -hex 16` | **A API se recusa a subir** |
| `VITE_API_URL` | `/api` | O app quebra em todo celular, sem erro no servidor |
| `APP_DOMAIN` | o domínio do app | O Caddy não sobe |
| `FRONTEND_URL` | `https://<seu domínio>`, sem barra no fim | O download da planilha falha por CORS |
| `ERP_SYNC_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"`, a mesma do `sync\config.ini` | O faturamento e os brindes do ERP não entram (a sincronização volta 503) |

As duas primeiras são checadas na largada: subir com as credenciais do
`.env.example` derruba a API com o motivo na primeira linha do log. Isso é de
propósito — a `SECRET_KEY` de exemplo está publicada neste repositório, e com ela
qualquer um forja um token de administrador.

**Sem domínio público** (rede interna da empresa): ponha em `APP_DOMAIN` o nome
interno da máquina e `CADDY_TLS=tls internal` no `.env`. O Caddy passa a emitir o
certificado com uma CA própria — que precisa ser instalada em cada celular, senão
o navegador barra o acesso. O arquivo da CA sai em
`docker compose -f docker-compose.prod.yml exec caddy cat /data/caddy/pki/authorities/local/root.crt`.

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
(`estoque_uploads`), banco (`estoque_pg_data`) e certificados (`caddy_data`) estão
em volumes e sobrevivem ao redeploy.

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
├── layouts/         # PromotorLayout e VendedorLayout (mobile), AdminLayout (desktop)
└── pages/
    ├── promotor/    # ← migra como bloco para o ERP
    ├── vendedor/    # pedido sugerido, com o fator de giro por produto na linha
    └── admin/

sync/                # roda no computador da empresa: lê o banco do ERP e manda
                     # o faturamento e os brindes (sincronizar-faturamento-e-brindes.bat)
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
  separadamente — mas o administrador recebe os dois juntos. Quem casa as duas
  pontas é `merchandising/consolidation.py`, por cliente + promotor + dia local
  (o dia de quem lê a planilha, não o UTC do servidor: senão a contagem das 22h
  cairia no dia seguinte e se separaria do próprio par).
- **`no_products` na visita.** "Estive aqui e não há nada" é diferente de "não
  contei" e diferente de "contei e deu zero". Sem essa coluna, o cliente que não
  tem produto num dos dois lugares nunca fecharia o par e travaria o download —
  ou o promotor seria obrigado a digitar um zero que não é verdade.
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
