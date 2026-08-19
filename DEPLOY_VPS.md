# Hospedar numa VPS Linux

Runbook para colocar o app no ar numa VPS do zero, alcançável pelos promotores
em campo e voltando sozinha depois de qualquer reinício.

Este é o **caminho em uso**. Os outros dois hospedeiros avaliados estão
registrados para não voltarem à mesa por engano: o PC Windows do escritório
(`DEPLOY_WINDOWS.md`, não adotado) e o servidor da empresa (descartado — as
portas do IP público pertencem a outros sistemas e o TI não redireciona novas).

## Antes de começar

- Uma VPS com **Ubuntu 22.04 ou 24.04**, acesso root e IP público fixo.
- **2 GB de RAM ou mais.** O build do frontend (Vite) é o pico de consumo do
  deploy inteiro; com 1 GB ele é morto pelo kernel no meio, e o sintoma é um
  `npm run build` que morre sem explicar por quê. Com 1 GB, o passo 3 resolve.
- O repositório é **privado**. A VPS entra nele com uma chave de deploy, criada
  no passo 5 — não use sua chave pessoal na VPS.

Sem domínio, o app é servido em **HTTP puro na porta 80**, alcançado por
`http://<ip>`. O preço disso (não instala como app no Android, não abre sem
sinal, tráfego em claro) está na seção "O que este deploy não faz" do README, e
some no dia em que houver um domínio, sem refazer nada.

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

Guarde o IP público: ele vai no `.env` e é o endereço que os promotores usam.

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
free -h | awk '/Swap:/ {print "Swap: " $2}'
```

O `fstab` é o que mantém o swap depois do reboot. Isso é para o build passar,
não para o app rodar em swap — se a VPS tem 1 GB, o app roda, mas apertado.

## 4. Firewall

```bash
ufw allow 22/tcp        # SSH — libere ANTES de ligar o ufw, ou você se tranca fora
ufw allow 80/tcp        # o app
ufw --force enable
ufw status numbered
```

O Postgres (5432) e a API (8000) **não** aparecem aqui de propósito: eles não
publicam porta no host, só existem dentro da rede do compose. Se algum dia
aparecerem no `ss -tlnp`, algo saiu errado no compose.

**Atenção ao firewall do painel do provedor.** Hostinger, Oracle e AWS têm um
segundo firewall, fora do sistema operacional, que ignora o `ufw`. Se o app não
abrir de fora mas responder no `curl -I http://localhost` de dentro, é ele.

## 5. Chave de deploy e clone

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

Na primeira conexão o SSH pergunta se confia no host do GitHub — responda `yes`.

## 6. Configurar o `.env`

```bash
cd /opt/app-promotoria
cp .env.example .env
```

Gere as senhas e escreva o IP de uma vez só (troque o IP pelo seu):

```bash
IP=203.0.113.10
SECRET=$(openssl rand -hex 32)
DBPASS=$(openssl rand -hex 16)

sed -i \
  -e "s|^API_ENV=.*|API_ENV=production|" \
  -e "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$DBPASS|" \
  -e "s|^DATABASE_PASSWORD=.*|DATABASE_PASSWORD=$DBPASS|" \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://estoque:$DBPASS@db:5432/estoque_db|" \
  -e "s|^FRONTEND_URL=.*|FRONTEND_URL=http://$IP|" \
  .env

grep -E '^(API_ENV|SECRET_KEY|POSTGRES_PASSWORD|DATABASE_PASSWORD|DATABASE_URL|FRONTEND_URL|VITE_API_URL)=' .env
```

O que não pode errar, e o sintoma de cada erro:

| Variável | Valor | Se errar |
|---|---|---|
| `SECRET_KEY` | 32 bytes aleatórios | **A API se recusa a subir** — a chave de exemplo está publicada no repositório e com ela qualquer um forja um token de administrador |
| `POSTGRES_PASSWORD` = `DATABASE_PASSWORD` = a de dentro da `DATABASE_URL` | as três iguais | **A API se recusa a subir** |
| `VITE_API_URL` | `/api` (já vem certo) | O app quebra em todo celular, sem um único erro no log do servidor |
| `FRONTEND_URL` | `http://<ip>`, sem barra no fim e sem `:80` | O download da planilha falha por CORS |

O `.env` não está no Git e nunca deve estar. Ele existe só nesta máquina —
**guarde uma cópia das senhas fora da VPS**, senão um dia elas se perdem junto
com ela.

## 7. Subir

```bash
cd /opt/app-promotoria
make prod-up      # build + up -d — o build do frontend leva alguns minutos
make prod-ps      # os três: db, api e web
make prod-seed    # SÓ NA PRIMEIRA VEZ: cria o tenant e o usuário admin
```

As migrações rodam sozinhas toda vez que a API sobe — não existe passo manual de
`alembic` neste deploy. É de propósito: esquecer o `alembic upgrade` deixava a
API respondendo `/health` com 200 e estourando 500 no login, que é o pior jeito
de descobrir o problema.

## 8. Conferir que está mesmo no ar

De dentro da VPS:

```bash
curl -s http://localhost/api/health          # {"status":"ok","environment":"production"}
curl -s -o /dev/null -w '%{http_code}\n' http://localhost/   # 200
```

Do seu computador, que é o teste que vale:

```bash
curl -s http://<ip>/api/health
```

E no celular, pelos dados móveis (não pelo Wi-Fi do escritório): abra
`http://<ip>`, entre com `admin` / `admin` e **troque a senha na hora**, no menu
do canto superior direito → *Trocar minha senha*. Enquanto não trocar, o app
está com a senha que está escrita neste arquivo.

Vale conferir também que o freio de força bruta do login enxerga o IP certo:

```bash
docker logs estoque_web --tail 20
```

Os IPs no início de cada linha têm que ser IPs de internet. Se aparecer
`172.x.x.x` em tudo, o nginx está vendo o IP do Docker em vez do celular, e o
limite de taxa do `/auth/login` passa a contar a equipe inteira como um cliente
só — um promotor errando a senha bloquearia o login de todos.

## 9. Backup

Os volumes moram no mesmo disco da VPS e somem junto com ela. Backup que fica
só na máquina não é backup.

```bash
cd /opt/app-promotoria && make prod-backup   # banco + fotos em ./backups
```

Diário, às 2h:

```bash
crontab -e
```

```cron
0 2 * * * cd /opt/app-promotoria && make prod-backup >> /var/log/backup-estoque.log 2>&1
0 3 * * * find /opt/app-promotoria/backups -mtime +14 -delete
```

A segunda linha existe porque o backup diário enche o disco em algumas semanas e
o sintoma disso é o app parando por falta de espaço, sem aviso.

**Copie os arquivos para fora da VPS.** Enquanto isso não estiver automatizado,
baixe de vez em quando, do seu computador:

```bash
rsync -avz root@<ip>:/opt/app-promotoria/backups/ ~/backups-estoque/
```

Para voltar um dump: `make prod-restore f=backups/banco_AAAAMMDD_HHMMSS.sql.gz`.

## 10. Atualizar depois

```bash
cd /opt/app-promotoria && git pull && make prod-up
```

O `--build` refaz as imagens e as migrações pendentes sobem junto. Banco
(`estoque_pg_data`) e fotos (`estoque_uploads`) estão em volumes e sobrevivem ao
redeploy.

## Quando houver um domínio

Registrar um domínio (~R$ 40/ano) desfaz as três perdas do HTTP puro sem refazer
o deploy: o app volta a instalar como aplicativo no Android, a abrir sem sinal e
a trafegar cifrado. O passo a passo está no cabeçalho do `Caddyfile`, que
continua no repositório justamente para esse dia. Banco, fotos e usuários ficam
onde estão.

## Se der errado

| Sintoma | Onde olhar |
|---|---|
| `make prod-up` termina mas a API reinicia sozinha | `docker logs estoque_api --tail 50` — a primeira linha diz se foi `SECRET_KEY`/senha do banco |
| Abre de dentro (`curl localhost`) e não de fora | firewall do painel do provedor (passo 4), não o `ufw` |
| Login responde 500 | migração — `make prod-logs` e procure `alembic` |
| Planilha não baixa, resto funciona | `FRONTEND_URL` diferente do endereço do navegador (barra no fim, `:80`, ou IP trocado) |
| App abre, mas nenhuma tela carrega dados | `VITE_API_URL` não era `/api` na hora do build — corrija o `.env` e rode `make prod-up` de novo |
| `npm run build` morre sem erro | RAM — passo 3 |
