# Hospedar num PC Windows

> **Caminho não adotado.** O app foi para uma VPS Linux dedicada — ver
> [`DEPLOY_VPS.md`](DEPLOY_VPS.md).
>
> Este runbook fica como plano B, mas está desatualizado num ponto que importa:
> ele pressupõe HTTPS via Caddy, e o deploy real serve em HTTP puro na porta 80
> — o serviço `caddy` não existe mais no `docker-compose.prod.yml`.

Runbook para colocar o app no ar a partir de uma máquina Windows do escritório,
alcançável pelos promotores em campo, com HTTPS e voltando sozinha depois de
qualquer reinício.

O app roda em contêineres Linux, então o Windows entra só como hospedeiro: quem
executa tudo é o WSL2. Para o deploy genérico (numa VPS ou máquina Linux), veja
a seção "Deploy em produção" do [README](README.md) — daqui para baixo é só o
que o Windows exige a mais.

## O que precisa estar resolvido antes

**Direitos de administrador nesta máquina.** Único item sem alternativa:
instalar o WSL2, o Docker, criar regra de firewall e tarefa agendada exigem
admin. Se a máquina for gerenciada pelo TI, comece por aqui.

Fora isso, **os passos 1 a 8 não dependem de mais ninguém**. Instale tudo, abra
o app em `https://localhost` na própria máquina e confirme que funciona. Só o
passo 9 — o promotor alcançar o app de fora — precisa da rede resolvida, e para
isso há dois caminhos.

### Caminho A: expor a máquina (precisa do TI)

Peça de uma vez, porque costuma demorar mais que a instalação:

- **Reserva de IP na rede local** para este PC, no DHCP — se o IP interno mudar,
  o redirecionamento quebra.
- **Redirecionamento das portas TCP 80 e 443** do IP fixo da empresa para o IP
  local deste PC.
- **Um registro DNS do tipo A** apontando um nome (`estoque.suaempresa.com.br`)
  para o IP fixo.
- **Confirmação de que o firewall da empresa aceita conexões de entrada** nessas
  portas. A 80 precisa continuar aberta depois: é por ela que o certificado
  HTTPS se renova sozinho a cada 3 meses.

Para quem administra o roteador, são dez minutos. É o caminho preferível: usa a
infraestrutura que a empresa já tem e não põe terceiro nenhum no meio.

### Caminho B: túnel (não precisa do TI)

Se o pedido acima for negado ou demorar, um contêiner `cloudflared` abre uma
conexão de dentro para fora e a Cloudflare publica o app em HTTPS. Não há porta
para abrir, firewall para liberar nem IP para reservar. Em troca, é preciso um
domínio próprio com DNS na Cloudflare (plano gratuito), e o tráfego passa por
ela. Este caminho substitui o Caddy no `docker-compose.prod.yml`.

### O que não tem alternativa

**HTTPS.** Acessar por `http://<ip>` parece atalho, mas o navegador não registra
o service worker fora de contexto seguro — e sem service worker não existe modo
offline. O promotor sem sinal no corredor do supermercado perde a tela de
contagem, que é a razão de o app existir. O Let's Encrypt também não emite
certificado para endereço IP, só para nome.

## 1. Fazer o Windows parar de se comportar como desktop

```powershell
# PowerShell como Administrador
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
```

Na BIOS, ligue **Restore on AC Power Loss** = *Power On*: é o que traz a máquina
de volta depois de queda de energia. E em **Windows Update → Opções avançadas**,
ponha o horário de atividade de forma que as reinicializações caiam de
madrugada, não às dez da manhã com os promotores em campo.

## 2. Instalar o WSL2 com Ubuntu

```powershell
wsl --install -d Ubuntu
```

Reinicie. O Ubuntu abre e pede usuário e senha (é a senha do `sudo`). Confira:

```powershell
wsl --version   # precisa ser 0.67.6 ou maior; se não for reconhecido: wsl --update
```

## 3. Ligar o systemd dentro do Ubuntu

Sem systemd o Docker não sobe sozinho, e o passo 7 não funciona.

```bash
sudo tee /etc/wsl.conf > /dev/null <<'EOF'
[boot]
systemd=true
EOF
```

```powershell
wsl --shutdown
```

Reabra o Ubuntu e confirme com `systemctl is-system-running` — `running` ou
`degraded` valem; `offline` não.

## 4. Instalar o Docker dentro do WSL

**Não use o Docker Desktop.** Ele só inicia depois que alguém faz login no
Windows — a máquina reinicia de madrugada e o app fica fora do ar até você
chegar. O Docker Engine dentro do WSL sobe com o sistema e não tem a discussão
de licença para empresas.

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo systemctl enable --now docker
sudo apt update && sudo apt install -y git make cron
sudo systemctl enable --now cron
```

Feche e reabra o terminal (para entrar no grupo `docker`) e teste com
`docker run --rm hello-world`.

## 5. Fazer a rede do Windows enxergar o WSL

O passo que mais derruba servidor caseiro. Por padrão o WSL2 fica atrás de uma
rede virtual própria: responde em `localhost` no Windows, mas não responde para
outras máquinas. Descubra sua versão com `winver`.

### Windows 11 22H2 ou maior

Modo espelhado — o WSL passa a compartilhar as interfaces de rede do Windows:

```powershell
@"
[wsl2]
networkingMode=mirrored
firewall=true
"@ | Set-Content "$env:USERPROFILE\.wslconfig" -Encoding utf8

wsl --shutdown
```

### Windows 10

Não existe modo espelhado. É preciso redirecionar as portas na mão, e como o IP
do WSL muda a cada reinício isso vira um script de boot. Salve como
`C:\Servidor\portas.ps1`:

```powershell
$ip = (wsl -d Ubuntu hostname -I).Trim().Split(" ")[0]
netsh interface portproxy reset
netsh interface portproxy add v4tov4 `
  listenport=80 listenaddress=0.0.0.0 connectport=80 connectaddress=$ip
netsh interface portproxy add v4tov4 `
  listenport=443 listenaddress=0.0.0.0 connectport=443 connectaddress=$ip
```

Ele entra no Agendador de Tarefas junto com o do passo 7.

### Nos dois casos

```powershell
New-NetFirewallRule -DisplayName "Estoque HTTP"  -Direction Inbound `
  -Protocol TCP -LocalPort 80  -Action Allow
New-NetFirewallRule -DisplayName "Estoque HTTPS" -Direction Inbound `
  -Protocol TCP -LocalPort 443 -Action Allow
```

## 6. Subir o app

Clone **dentro do sistema de arquivos do Linux** (`~`), nunca em `/mnt/c/` — lá
o Docker fica lento e as permissões dão problema.

```bash
cd ~
git clone <url-do-repositorio> app-promotoria
cd app-promotoria
cp .env.example .env
openssl rand -hex 32   # SECRET_KEY
openssl rand -hex 16   # senha do banco
nano .env
```

Seis valores mudam:

| Variável | Valor |
|---|---|
| `API_ENV` | `production` |
| `SECRET_KEY` | o primeiro `openssl` |
| `POSTGRES_PASSWORD` | o segundo `openssl` — repita em `DATABASE_PASSWORD` e dentro da `DATABASE_URL` |
| `VITE_API_URL` | `/api` |
| `APP_DOMAIN` | o nome que o TI apontou no DNS |
| `FRONTEND_URL` | `https://` + o mesmo nome |

Deixe `CADDY_TLS` vazio: com domínio público apontado para o IP fixo, o
certificado sai sozinho pelo Let's Encrypt.

```bash
make prod-up
make prod-seed    # só nesta primeira vez
make prod-logs
```

Assim que o site abrir, entre como `admin`/`admin` e **troque a senha na hora**,
no menu do canto superior direito.

## 7. Fazer tudo voltar sozinho depois do reinício

O WSL não é um serviço do Windows: só liga quando alguém o usa. Sem este passo,
a máquina reinicia às 3h e o app só volta quando você fizer login.

No **Agendador de Tarefas** → **Criar Tarefa** (não "tarefa básica"):

1. **Geral**: nome `Servidor Estoque`. Marque *Executar estando o usuário
   conectado ou não* e *Executar com privilégios mais altos*.
2. **Disparadores** → Novo → *Ao iniciar o computador*.
3. **Ações** → Novo → Programa `C:\Windows\System32\wsl.exe`, argumentos:
   `-d Ubuntu -u root -e sh -c "sleep infinity"`
4. **Condições**: desmarque *Iniciar a tarefa somente se o computador estiver
   ligado na energia*.
5. Ao salvar, o Windows pede a senha da sua conta — é o que permite a tarefa
   rodar sem ninguém logado.

A tarefa acorda o WSL no boot e o mantém acordado; o systemd sobe o Docker, e o
Docker sobe os contêineres, que já estão como `restart: unless-stopped`.

No **Windows 10**, crie uma segunda tarefa igual para o `portas.ps1` do passo 5,
com programa `powershell.exe` e argumentos
`-ExecutionPolicy Bypass -File C:\Servidor\portas.ps1`.

## 8. Tirar o backup de dentro da máquina

O disco desta máquina é o que vai morrer um dia, levando junto o banco e as
fotos. Grave o backup numa pasta do *Windows* e sincronize com OneDrive ou
Drive — aí ele passa a existir fora do prédio.

```bash
mkdir -p /mnt/c/Backups/estoque
crontab -e
```

```cron
0 2 * * * cd ~/app-promotoria && make prod-backup BACKUP_DIR=/mnt/c/Backups/estoque
```

De vez em quando rode `docker builder prune -f`: o cache de compilação cresce
alguns GB a cada atualização.

## 9. Provar que está de pé

O teste que importa não é abrir o site nesta máquina — é reiniciar e **não fazer
login**. Reinicie o Windows, pare na tela de senha, espere três minutos e faça o
resto pelo celular, **no 4G, com o Wi-Fi desligado**:

- [ ] O site abre pelo domínio. *Não abriu: portas no roteador, ou a tarefa do passo 7.*
- [ ] Aparece o cadeado, sem aviso de certificado. *Apareceu aviso: a porta 80 precisa estar aberta de fora.*
- [ ] O navegador oferece instalar o app na tela inicial. *É a prova de que o modo offline vai funcionar no mercado.*
- [ ] Login do promotor e uma contagem enviada, com produtos de verdade.
- [ ] A planilha baixa pelo painel do admin, com a hora batendo com o relógio.
- [ ] No dia seguinte existe arquivo em `C:\Backups\estoque`. *Não existe: `sudo systemctl status cron`.*

## Quando alguma coisa parar

**O site sumiu depois de um reinício.** Quase sempre é a tarefa do passo 7: veja
o *Resultado da última execução* no Agendador de Tarefas. Enquanto investiga,
`wsl -d Ubuntu -e true` no PowerShell levanta tudo na hora.

**Abre no escritório, mas não pelo 4G.** O problema está fora da máquina:
redirecionamento das portas, IP local do PC que mudou, ou DNS não propagado.

**Reclamação de certificado.** O Caddy precisa alcançar a internet pela porta 80
para validar o domínio. O motivo exato está em
`docker compose -f docker-compose.prod.yml logs caddy`.

**Atualizar o app.** Em `~/app-promotoria`: `git pull && make prod-up`. As
migrações sobem junto; banco, fotos e certificados ficam em volumes e
sobrevivem. Rode `make prod-backup` antes, por hábito.
