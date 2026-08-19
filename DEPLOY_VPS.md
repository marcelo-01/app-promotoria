# Hospedar numa VPS Linux

Runbook para colocar o app no ar numa VPS do zero, alcançável pelos promotores
em campo, com HTTPS e voltando sozinha depois de qualquer reinício.

Este é o **caminho em uso**. Os outros dois hospedeiros avaliados estão
registrados para não voltarem à mesa por engano: o PC Windows do escritório
(`DEPLOY_WINDOWS.md`, não adotado) e o servidor da empresa (descartado — as
portas do IP público pertencem a outros sistemas e o TI não redireciona novas).

## Antes de começar

- Uma VPS com **Ubuntu 22.04 ou 24.04**, acesso root e IP público fixo.
- **2 GB de RAM ou mais.** O build do frontend (Vite) é o pico de consumo do
  deploy inteiro; com 1 GB ele é morto pelo kernel no meio, e o sintoma é um
  `npm run build` que morre sem explicar por quê. Com 1 GB, o passo 3 resolve.
- **Um domínio** apontando para a VPS. Não é preferência estética: sem domínio
  não há certificado, sem certificado não há contexto seguro, e sem contexto
  seguro o app não instala como aplicativo no Android nem abre sem sinal dentro
  do mercado — que são requisitos do trabalho do promotor, não enfeites.
- O repositório é **privado**. A VPS entra nele com uma chave de deploy, criada
  no passo 6 — não use sua chave pessoal na VPS.

## 1. Reconhecimento

Antes de instalar qualquer coisa, saiba o que veio na máquina:

```bash
. /etc/os-release && echo "$PRETTY_NAME"
free -h | awk '/Mem:/ {print "RAM: " $2 " (livre " $7 ")"}'
df -h / | awk 'NR==2 {print "Disco: " $2 " (livre " $4 ")"}'
nproc | xargs echo "CPUs:"
docker --version 2>/dev/null || echo "Docker: NAO INSTALADO"
curl -s -4 ifconfig.me | xargs echo "IP público:"
```

Guarde o IP público: é para ele que o domínio vai apontar.

## 2. Docker

Se o passo anterior disse `NAO INSTALADO`:

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker compose version   # tem que responder; se não, o plugin não veio junto
```

`systemctl enable` é o que faz os contêineres voltarem sozinhos depois de um
reinício da VPS — combinado com o `restart: unless-stopped` que já está no
compose. Sem ele, um reboot noturno derruba o app até alguém perceber.

## 3. Swap (só se a RAM for menor que 2 GB)

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

O `fstab` é o que mantém o swap depois do reboot. Isso é para o build passar,
não para o app rodar em swap.

## 4. Domínio e DNS

No painel de DNS do domínio, um registro **A** apontando para o IP da VPS:

```
A    estoque    <ip-da-vps>
```

Prefira um **subdomínio** (`estoque.seudominio.com`) a usar o domínio raiz: o
mesmo domínio passa a servir os próximos aplicativos sem registrar nada de novo,
e cada um ganha certificado próprio no mesmo `Caddyfile`.

Confira antes de seguir — o Caddy falha em obter certificado se o nome ainda não
resolver, e cada falha conta no limite de emissões do Let's Encrypt:

```bash
dig +short estoque.seudominio.com    # tem que responder o IP da VPS
```

Propagação leva de minutos a algumas horas. **Não suba o app antes disso.**

## 5. Firewall

```bash
ufw allow 22/tcp        # SSH — libere ANTES de ligar o ufw, ou você se tranca fora
ufw allow 80/tcp        # HTTP: redirecionamento para HTTPS e validação do certificado
ufw allow 443/tcp       # HTTPS
ufw allow 443/udp       # HTTP/3
ufw --force enable
ufw status numbered
```

A 80 não pode ser fechada mesmo com o app todo em HTTPS: é por ela que o Let's
Encrypt valida o domínio a cada renovação.

O Postgres (5432), a API (8000) e o nginx **não** aparecem aqui de propósito:
eles não publicam porta no host, só existem dentro da rede do compose. Só o
Caddy fala com a internet.

**Atenção ao firewall do painel do provedor.** Hostinger, Oracle e AWS têm um
segundo firewall, fora do sistema operacional, que ignora o `ufw`. Se o app não
abrir de fora mas responder no `curl -I http://localhost` de dentro, é ele.

## 6. Chave de deploy e clone

O repositório é privado. Gere na VPS uma chave só dela:

```bash
ssh-keygen -t ed25519 -C "vps-app-promotoria" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Cadastre essa chave pública no GitHub como **deploy key** do repositório
(Settings → Deploy keys → Add), **sem** marcar "Allow write access": a VPS só
precisa ler. Depois:

```bash
mkdir -p /opt && git clone git@github.com:marcelo-01/app-promotoria.git /opt/app-promotoria
cd /opt/app-promotoria
```

## 7. Configurar o `.env`

```bash
cd /opt/app-promotoria
cp .env.example .env
```

Gere as senhas e escreva o domínio de uma vez só (troque pelo seu):

```bash
DOMINIO=estoque.seudominio.com
SECRET=$(openssl rand -hex 32)
DBPASS=$(openssl rand -hex 16)

sed -i \
  -e "s|^API_ENV=.*|API_ENV=production|" \
  -e "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$DBPASS|" \
  -e "s|^DATABASE_PASSWORD=.*|DATABASE_PASSWORD=$DBPASS|" \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://estoque:$DBPASS@db:5432/estoque_db|" \
  -e "s|^APP_DOMAIN=.*|APP_DOMAIN=$DOMINIO|" \
  -e "s|^FRONTEND_URL=.*|FRONTEND_URL=https://$DOMINIO|" \
  .env

grep -E '^(API_ENV|SECRET_KEY|POSTGRES_PASSWORD|DATABASE_PASSWORD|DATABASE_URL|APP_DOMAIN|FRONTEND_URL|VITE_API_URL|CADDY_TLS)=' .env
```

O que não pode errar, e o sintoma de cada erro:

| Variável | Valor | Se errar |
|---|---|---|
| `SECRET_KEY` | 32 bytes aleatórios | **A API se recusa a subir** — a chave de exemplo está publicada no repositório e com ela qualquer um forja um token de administrador |
| `POSTGRES_PASSWORD` = `DATABASE_PASSWORD` = a de dentro da `DATABASE_URL` | as três iguais | **A API se recusa a subir** |
| `VITE_API_URL` | `/api` (já vem certo) | O app quebra em todo celular, sem um único erro no log do servidor |
| `APP_DOMAIN` | o domínio, sem `https://` | O Caddy não sobe |
| `FRONTEND_URL` | `https://<domínio>`, sem barra no fim | O download da planilha falha por CORS |
| `CADDY_TLS` | vazio (já vem certo) | Preenchido com `tls internal`, cada celular passa a exigir a CA instalada à mão |

O `.env` não está no Git e nunca deve estar. Ele existe só nesta máquina —
**guarde uma cópia das senhas fora da VPS**, senão um dia elas se perdem junto
com ela.

## 8. Subir

```bash
cd /opt/app-promotoria
command -v make >/dev/null || (apt-get update -qq && apt-get install -y -qq make)

make prod-up      # build + up -d — o build do frontend leva alguns minutos
make prod-ps      # os quatro: db, api, web e caddy
make prod-seed    # SÓ NA PRIMEIRA VEZ: cria o tenant e o usuário admin
```

As migrações rodam sozinhas toda vez que a API sobe — não existe passo manual de
`alembic` neste deploy. É de propósito: esquecer o `alembic upgrade` deixava a
API respondendo `/health` com 200 e estourando 500 no login, que é o pior jeito
de descobrir o problema.

O certificado é emitido na primeira subida do Caddy, em segundos. Se demorar,
acompanhe: `docker logs estoque_caddy --tail 30`.

## 9. Conferir que está mesmo no ar

De dentro da VPS:

```bash
curl -s https://estoque.seudominio.com/api/health   # {"status":"ok","environment":"production"}
curl -sI http://estoque.seudominio.com | head -1    # 308: HTTP redireciona para HTTPS
```

Do seu computador, que é o teste que vale:

```bash
curl -s https://estoque.seudominio.com/api/health
curl -sI https://estoque.seudominio.com | grep -i "^HTTP\|^alt-svc"
```

E no celular, **pelos dados móveis** (não pelo Wi-Fi do escritório — assim você
testa o caminho que o promotor usa): abra o domínio, confirme o **cadeado** na
barra de endereço, entre com `admin` / `admin` e **troque a senha na hora**, no
menu do canto superior direito → *Trocar minha senha*. Enquanto não trocar, o app
está com a senha que está escrita neste arquivo.

Com o cadeado no lugar, o Chrome oferece **Instalar aplicativo** no menu — é
assim que o promotor põe o ícone na tela inicial e ganha o modo offline.

Vale conferir também que o freio de força bruta do login enxerga o IP certo:

```bash
docker logs estoque_web --tail 20 | grep auth/login
```

Os IPs têm que ser IPs de internet. Se aparecer o IP do Caddy em tudo, o
`set_real_ip_from` do `nginx.prod.conf` saiu do ar e o limite de taxa passa a
contar a equipe inteira como um cliente só — um promotor errando a senha
bloquearia o login de todos.

## 10. Backup

Os volumes moram no mesmo disco da VPS e somem junto com ela. Backup que fica
só na máquina não é backup.

```bash
cd /opt/app-promotoria && make prod-backup   # banco + fotos em ./backups
```

Diário, às 2h:

```cron
0 2 * * * cd /opt/app-promotoria && make prod-backup >> /var/log/backup-estoque.log 2>&1
0 3 * * * find /opt/app-promotoria/backups -mtime +14 -delete
```

A segunda linha existe porque o backup diário enche o disco em algumas semanas e
o sintoma disso é o app parando por falta de espaço, sem aviso.

**Copie os arquivos para fora da VPS.** Do seu computador, de vez em quando:

```bash
rsync -avz root@<ip>:/opt/app-promotoria/backups/ ~/backups-estoque/
```

Para voltar um dump: `make prod-restore f=backups/banco_AAAAMMDD_HHMMSS.sql.gz`.

## 11. Atualizar depois

```bash
cd /opt/app-promotoria && git pull && make prod-up
```

O `--build` refaz as imagens e as migrações pendentes sobem junto. Banco
(`estoque_pg_data`), fotos (`estoque_uploads`) e certificados (`caddy_data`)
estão em volumes e sobrevivem ao redeploy.

## Hospedar outros aplicativos no mesmo domínio

Cada novo app ganha um subdomínio (`outroapp.seudominio.com` → mesmo IP) e um
bloco próprio no `Caddyfile`, com certificado próprio, automático. Não é preciso
registrar domínio novo nem mexer neste app.

## Se der errado

| Sintoma | Onde olhar |
|---|---|
| Navegador diz "conexão não é particular" | O Caddy não conseguiu o certificado: `docker logs estoque_caddy`. Quase sempre o DNS ainda não resolvia na hora da subida (passo 4) |
| `make prod-up` termina mas a API reinicia sozinha | `docker logs estoque_api --tail 50` — a primeira linha diz se foi `SECRET_KEY`/senha do banco |
| Abre de dentro e não de fora | firewall do painel do provedor (passo 5), não o `ufw` |
| Login responde 500 | migração — `make prod-logs` e procure `alembic` |
| Planilha não baixa, resto funciona | `FRONTEND_URL` diferente do endereço do navegador (barra no fim, `http` em vez de `https`) |
| App abre, mas nenhuma tela carrega dados | `VITE_API_URL` não era `/api` na hora do build — corrija o `.env` e rode `make prod-up` de novo |
| Chrome não oferece "Instalar aplicativo" | Sem cadeado não há PWA. Confira o certificado antes de procurar erro no app |
| `npm run build` morre sem erro | RAM — passo 3 |
