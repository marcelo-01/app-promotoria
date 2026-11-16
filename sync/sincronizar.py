"""Manda o faturamento e os brindes do ERP para o app de promotoria (estoque.maisvida.cloud).

Lê as notas de venda (VENDAS e LISTAVENDA) e de brinde (BRINDES e LISTABRINDE) da cópia do banco do ERP (Firebird 2.1,
só leitura) e manda tudo para o servidor num pacote só, compactado e assinado com HMAC-SHA256 da hora do envio e do
hash do conteúdo (o mesmo esquema do BI Mais Vida e do EFFEX Trade). A chave fica no config.ini e na ERP_SYNC_KEY do
servidor e nunca trafega.

Vão as notas não canceladas a cliente dos DIAS dias que terminam no último dia com venda na cópia, com as peças de cada
produto (NUM_PECAS, a coluna N. PEÇAS das planilhas), o CFOP de cada item, a empresa e, no brinde, o motivo: o que as
planilhas de faturamento e de brindes traziam, lido das tabelas de onde o relatório do ERP o tirava. O servidor aplica
as regras de sempre (o CFOP de venda e o de brinde), casa cada nota com o cliente pelo CNPJ e cada item com o produto
pelo código do ERP, e troca as entradas do período inteiro pelas do pacote: a nota cancelada ou corrigida no ERP some
ou muda no app no envio seguinte. Se a leitura dos brindes (ou a das vendas) falhar, a outra vai assim mesmo, e o app
fica com o que já tinha da que falhou.

Uso: dois cliques em sincronizar-faturamento-e-brindes.bat, ou: python sincronizar.py [--sem-enviar] [--forcar]
"""
from __future__ import annotations

import argparse
import configparser
import datetime as dt
import gzip
import hashlib
import hmac
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

PASTA = Path(__file__).resolve().parent
ROTA = "/merchandising/erp/sync"

# Quantos dias vão a cada envio, terminando no último dia com venda na cópia. São os mesmos 120 dias que o app olha para
# trás (EXPIRY_WINDOW_DAYS em backend/app/merchandising/service.py): o ciclo mais longo que ele usa cabe aqui dentro.
DIAS = 120
# Cópia do banco mais velha que isso ganha um aviso (a sincronização segue)
DIAS_COPIA_VELHA = 2
# Igual ao servidor (erp_sync.MIN_CHAVE): secrets.token_urlsafe(32) dá 43 caracteres
MIN_CHAVE = 32

# O período termina no último dia com venda na cópia, e não hoje: com uma cópia velha, os dias depois dela iriam vazios
# e apagariam no app o que um envio de cópia mais nova já tinha gravado. Data digitada errada no futuro fica de fora.
CONSULTA_ULTIMA_VENDA = ("SELECT MAX(v.DATA) FROM VENDAS v "
                         "WHERE v.DATA < ? AND v.DATACANCELAMENTO IS NULL AND v.TIPOCLIENTE = 'CLIENTE'")
# Só TIPOCLIENTE = 'CLIENTE': a venda a funcionário, fornecedor ou produtor guarda em ID_CLIENTE o código do cadastro
# deles, e casá-lo com CLIENTES poria a venda na conta de uma loja qualquer (em out/2026, 148 notas assim). As peças vão
# somadas por produto e CFOP em cada nota. NUM_PECAS é a coluna N. PEÇAS das planilhas; a QUANTIDADE não serve, porque
# mistura unidade e quilo (queijo é faturado por peso). A data é VENDAS.DATA, a EMISSÃO da planilha.
CONSULTA_VENDAS = ("SELECT v.ID_VENDA, CAST(v.DATA AS DATE), v.NOTAFISCAL, v.ID_EMPRESA, v.ID_CLIENTE, "
                   "l.ID_ITEM, l.CFOP, SUM(l.NUM_PECAS) "
                   "FROM VENDAS v JOIN LISTAVENDA l ON l.ID_VENDA = v.ID_VENDA "
                   "WHERE v.DATA >= ? AND v.DATA < ? AND v.DATACANCELAMENTO IS NULL AND v.TIPOCLIENTE = 'CLIENTE' "
                   "AND l.ID_ITEM IS NOT NULL "
                   "GROUP BY 1, 2, 3, 4, 5, 6, 7")
# Os brindes, com o motivo. Vão todos os CFOPs: o servidor separa a remessa ao cliente (5910 e 6910) da transferência,
# do retorno e da perda, e conta o que deixou de fora. Aqui o brinde já vem com a contagem de peças de verdade, que a
# planilha de brindes não trazia (ela dava peso ÷ peso da peça: 6,405 peças).
CONSULTA_BRINDES = ("SELECT b.ID_BRINDE, CAST(b.DATA AS DATE), b.NOTAFISCAL, b.ID_EMPRESA, b.ID_CLIENTE, "
                    "b.ID_MOTIVO, l.ID_ITEM, l.CFOP, SUM(l.NUM_PECAS) "
                    "FROM BRINDES b JOIN LISTABRINDE l ON l.ID_BRINDE = b.ID_BRINDE "
                    "WHERE b.DATA >= ? AND b.DATA < ? AND b.DATACANCELAMENTO IS NULL AND b.TIPOCLIENTE = 'CLIENTE' "
                    "AND l.ID_ITEM IS NOT NULL "
                    "GROUP BY 1, 2, 3, 4, 5, 6, 7, 8")
# CGC é o CNPJ (com pontuação); sem ele, o CPF. CODIGO é o código que aparece no ERP (a "COD. CLIENTE" da planilha)
CONSULTA_CLIENTES = "SELECT ID_CLIENTE, CODIGO, CGC, CPF, NOME FROM CLIENTES"
# CODIGO (A51000) é o código do item que o cadastro do app guarda em "código do ERP"; ID_PRODUTO é o interno
CONSULTA_PRODUTOS = "SELECT ID_PRODUTO, CODIGO, NOME FROM PRODUTOS"
CONSULTA_EMPRESAS = "SELECT ID_EMPRESA, NOME FROM CADASTROEMPRESA"
# O motivo do brinde (BRINDES.ID_MOTIVO) fica na mesma tabela dos motivos de devolução
CONSULTA_MOTIVOS = "SELECT ID_MOTIVODEVOLUCAO, NOME FROM MOTIVODEVOLUCAO"


class Problema(Exception):
    """Erro com uma mensagem para quem rodou a sincronização."""

    def __init__(self, mensagem: str, codigo: str | None = None):
        super().__init__(mensagem)
        self.codigo = codigo


def registrar(texto: str) -> None:
    """Uma linha por execução em sincronizar.log, para conferir depois."""
    try:
        with open(PASTA / "sincronizar.log", "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {texto}\n")
    except OSError:
        pass


def ler_config() -> configparser.ConfigParser:
    arquivo = PASTA / "config.ini"
    if not arquivo.exists():
        raise Problema(f"falta o arquivo {arquivo}: copie o config.exemplo.ini para config.ini e preencha")
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(arquivo, encoding="utf-8")
    return ini


def conferir_destino(destino: str, chave: str) -> None:
    if not chave:
        raise Problema("falta a chave em [envio] no config.ini (é a ERP_SYNC_KEY do .env do servidor)")
    if len(chave) < MIN_CHAVE:
        raise Problema(f"a chave em [envio] no config.ini tem menos de {MIN_CHAVE} caracteres; gere outra com:\n"
                       '  python -c "import secrets; print(secrets.token_urlsafe(32))"\n'
                       "  e ponha a mesma na ERP_SYNC_KEY do .env do servidor")
    u = urlparse(destino)
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost")):
        raise Problema(f"o destino em [envio] precisa começar com https:// ({destino or 'vazio'})")


def texto(valor, limite: int) -> str | None:
    return " ".join(("" if valor is None else str(valor)).split())[:limite] or None


def digitos(valor) -> str:
    return re.sub(r"\D", "", "" if valor is None else str(valor))


def dia(valor) -> dt.date | None:
    return valor.date() if isinstance(valor, dt.datetime) else valor


def data_br(iso: str) -> str:
    return f"{dt.date.fromisoformat(iso):%d/%m/%Y}"


def numero(valor: float) -> str:
    """1234567.8 → 1.234.568"""
    return f"{valor:,.0f}".replace(",", ".")


def contagem(valor: float, singular: str, plural: str) -> str:
    """1 entrada, 2 entradas, 1.234 entradas"""
    return f"{numero(valor)} {singular if round(valor) == 1 else plural}"


def resumo_erro(erro: Exception) -> str:
    return " ".join(str(erro).split()) or type(erro).__name__


def ler_notas(bd, consulta: str, de: dt.datetime, ate: dt.datetime, empresas: dict,
              motivos: dict | None) -> list[dict]:
    """Uma nota por número, com um item por produto e CFOP. `motivos` só nos brindes."""
    notas: dict[int, dict] = {}
    for linha in bd.consulta(consulta, (de, ate)):
        if motivos is None:
            numero_nota, data, nf, id_empresa, id_cliente, id_produto, cfop, pecas = linha
            id_motivo = None
        else:
            numero_nota, data, nf, id_empresa, id_cliente, id_motivo, id_produto, cfop, pecas = linha
        if id_cliente is None or int(id_cliente) <= 0 or id_produto is None:
            continue
        nota = notas.get(numero_nota)
        if nota is None:
            empresa = empresas.get(id_empresa) or (f"Empresa {id_empresa}" if id_empresa else None)
            nota = notas[numero_nota] = {"number": int(numero_nota), "issued_on": dia(data).isoformat(),
                                         "invoice": texto(nf, 40), "company": texto(empresa, 120),
                                         "customer": int(id_cliente), "items": []}
            if motivos is not None:
                nota["reason"] = texto(motivos.get(id_motivo), 120)
        nota["items"].append({"product": int(id_produto), "cfop": texto(cfop, 10),
                              "pieces": round(float(pecas or 0), 3)})
    return list(notas.values())


def ler_banco(ini: configparser.ConfigParser, hoje: dt.date) -> dict:
    """As notas de venda e de brinde do período, com os clientes e produtos delas, numa transação só."""
    from fb import BancoSomenteLeitura  # só aqui: o fdb e o Firebird só são necessários para ler o banco

    b = ini["banco"]
    arquivo = Path(b.get("arquivo", "").strip())
    if not arquivo.is_file():
        raise Problema(f"a cópia do banco não está em {arquivo} (confira [banco] arquivo no config.ini)")
    senha = b.get("senha", "").strip()
    if not senha or senha == "COLOQUE_A_SENHA_AQUI":
        raise Problema("falta a senha do banco em [banco] no config.ini")
    # Data da cópia: a criação do arquivo. A de modificação não serve, porque o Firebird regrava o cabeçalho do .GDB
    # a cada conexão (inclusive as do BI e do EFFEX); no Windows, st_ctime é a criação
    st = arquivo.stat()
    copia = dt.datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_ctime)).astimezone()

    erros: dict[str, str] = {}
    vendas = brindes = None
    try:
        with BancoSomenteLeitura(str(arquivo), b.get("usuario", "SYSDBA"), senha, host=b.get("host", "localhost"),
                                 fbclient=b.get("fbclient") or None, codificacao=b.get("codificacao", "cp1252")) as bd:
            amanha = dt.datetime.combine(hoje + dt.timedelta(days=1), dt.time())
            fim = dia(bd.consulta(CONSULTA_ULTIMA_VENDA, (amanha,))[0][0]) or hoje
            inicio = fim - dt.timedelta(days=DIAS - 1)
            de = dt.datetime.combine(inicio, dt.time())
            ate = dt.datetime.combine(fim + dt.timedelta(days=1), dt.time())
            empresas = dict(bd.consulta(CONSULTA_EMPRESAS))
            clientes = bd.consulta(CONSULTA_CLIENTES)
            produtos = bd.consulta(CONSULTA_PRODUTOS)
            # Cada origem à parte: se uma tabela mudar no ERP, a outra vai assim mesmo
            try:
                vendas = ler_notas(bd, CONSULTA_VENDAS, de, ate, empresas, None)
            except Exception as e:
                erros["vendas"] = resumo_erro(e)
            try:
                motivos = dict(bd.consulta(CONSULTA_MOTIVOS))
                brindes = ler_notas(bd, CONSULTA_BRINDES, de, ate, empresas, motivos)
            except Exception as e:
                erros["brindes"] = resumo_erro(e)
    except Exception as e:
        raise Problema(f"falha ao ler o banco: {resumo_erro(e)}\n  Confira se o serviço 'Firebird Server - "
                       "DefaultInstance' está rodando e se a cópia do banco terminou de ser gravada.") from None
    if vendas is None and brindes is None:
        raise Problema(f"não deu para ler as notas. Vendas: {erros['vendas']}. Brindes: {erros['brindes']}.")
    if vendas is not None and not vendas:
        raise Problema(f"nenhuma venda a cliente nos {DIAS} dias até {fim:%d/%m/%Y}: a cópia do banco está completa?")

    # Só os clientes e produtos que aparecem nas notas, e só as notas cujo cliente e produtos existem no cadastro do
    # ERP (o servidor recusa o pacote inteiro se uma nota apontar para um cadastro que não veio)
    cadastro_clientes = {int(i): (cod, cgc, cpf, nome) for i, cod, cgc, cpf, nome in clientes if i is not None}
    cadastro_produtos = {int(i): (cod, nome) for i, cod, nome in produtos if i is not None}
    descartadas = 0
    for notas in (vendas, brindes):
        if notas is None:
            continue
        boas = []
        for nota in notas:
            nota["items"] = [i for i in nota["items"] if i["product"] in cadastro_produtos]
            if nota["customer"] in cadastro_clientes and nota["items"]:
                boas.append(nota)
            else:
                descartadas += 1
        notas[:] = boas
    todas = (vendas or []) + (brindes or [])
    usados_c = {n["customer"] for n in todas}
    usados_p = {i["product"] for n in todas for i in n["items"]}
    return {
        "copia": copia, "inicio": inicio, "fim": fim, "vendas": vendas, "brindes": brindes, "erros": erros,
        "descartadas": descartadas,
        "clientes": [{"erp_id": i, "code": texto(cod, 40), "document": (digitos(cgc) or digitos(cpf))[:20] or None,
                      "name": texto(nome, 255)}
                     for i, (cod, cgc, cpf, nome) in cadastro_clientes.items() if i in usados_c],
        "produtos": [{"erp_id": i, "code": texto(cod, 50), "name": texto(nome, 255)}
                     for i, (cod, nome) in cadastro_produtos.items() if i in usados_p],
    }


def resumo_notas(rotulo: str, notas: list[dict] | None, erro: str | None) -> str:
    """Sem as peças: as dos brindes incluem as transferências entre filiais, que o servidor deixa de fora pelo CFOP.
    As peças que contam são as que o servidor diz que entraram."""
    if notas is None:
        return f"  Atenção: {rotulo.lower()} não foram lidos ({erro}).\n  O app continua com o que já tinha deles."
    itens = sum(len(n["items"]) for n in notas)
    return (f"  {rotulo}: {numero(len(notas))} notas, {numero(itens)} itens, "
            f"{numero(len({n['customer'] for n in notas}))} clientes.")


def enviar(destino: str, chave: str, corpo: bytes) -> dict:
    data = str(int(time.time()))
    assinatura = hmac.new(chave.encode(), f"{data}\n{hashlib.sha256(corpo).hexdigest()}".encode(),
                          hashlib.sha256).hexdigest()
    req = urllib.request.Request(destino + ROTA, data=corpo, method="POST", headers={
        "Content-Type": "application/gzip",
        "User-Agent": "Promotoria-sincronizacao/1.0",
        "X-Estoque-Data": data,
        "X-Estoque-Assinatura": assinatura,
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            detalhe = json.loads(e.read()).get("detail")
        except Exception:
            detalhe = None
        codigo = None
        if isinstance(detalhe, dict):
            mensagem, codigo = detalhe.get("message"), detalhe.get("code")
        elif isinstance(detalhe, str) and e.code != 404:
            mensagem = detalhe
        elif e.code == 404:
            mensagem = "o servidor ainda não tem a sincronização; publique a versão nova do app"
        elif e.code == 429:
            mensagem = "muitos envios seguidos; espere um minuto e rode de novo"
        else:
            mensagem = None
        raise Problema(f"o servidor recusou o envio ({e.code}): {mensagem or e.reason}", codigo) from None
    except urllib.error.URLError as e:
        raise Problema(f"sem conexão com {destino}: {e.reason}") from None
    except TimeoutError:
        raise Problema(f"{destino} não respondeu em 5 minutos; rode de novo daqui a pouco") from None


def relato_origem(rotulo: str, r: dict | None) -> tuple[list[str], str]:
    """As linhas do resumo de uma origem e o pedaço dela no log."""
    if r is None:
        return [f"  {rotulo}: não foi no pacote; o app ficou com o que já tinha."], f"{rotulo.lower()} não enviado"
    pecas = float(r.get("matched_quantity") or 0)
    entraram = r["matched_lines"]
    linhas = [f"  {rotulo}: {contagem(entraram, 'item entrou', 'itens entraram')} no app "
              f"({contagem(pecas, 'peça', 'peças')}, {contagem(r.get('matched_customers', 0), 'cliente', 'clientes')});"
              f" o envio trocou {contagem(r.get('previous_lines', 0), 'entrada', 'entradas')} que havia no período."]
    fora = []
    if r.get("ignored_cfop"):
        fora.append(f"{numero(r['ignored_cfop'])} pelo CFOP")
    if r.get("ignored_incomplete"):
        fora.append(f"{numero(r['ignored_incomplete'])} sem peças")
    if fora:
        linhas.append(f"    Itens que ficaram de fora: {' e '.join(fora)}.")
    sem_p, sem_c = r.get("unknown_products_total", 0), r.get("unknown_customers_total", 0)
    if sem_p or sem_c:
        linhas.append(f"    Sem cadastro no app: {contagem(sem_p, 'produto', 'produtos')} e "
                      f"{contagem(sem_c, 'cliente', 'clientes')} (a lista está na tela Faturamento do ERP).")
    motivos = r.get("by_reason") or []
    if motivos:
        linhas.append("    Por motivo: " + "; ".join(f"{m['code']} ({numero(float(m['quantity']))} peças)"
                                                     for m in motivos))
    log = (f"{rotulo.lower()} {r['matched_lines']} itens ({pecas:.0f} pç, {r.get('matched_customers', 0)} clientes, "
           f"havia {r.get('previous_lines', 0)})")
    return linhas, log


def main() -> int:
    parser = argparse.ArgumentParser(description="Manda o faturamento e os brindes do ERP para o app de promotoria.")
    parser.add_argument("--sem-enviar", action="store_true",
                        help="só lê a cópia do banco e mostra o resumo, sem mandar nada ao servidor")
    parser.add_argument("--forcar", action="store_true",
                        help="confirma um envio que deixaria o período com menos da metade das entradas de hoje "
                             "(o servidor pede confirmação)")
    args = parser.parse_args()

    print("Promotoria - sincronização do faturamento e dos brindes com o ERP\n")
    try:
        ini = ler_config()
        destino = ini.get("envio", "destino", fallback="").strip().rstrip("/")
        chave = ini.get("envio", "chave", fallback="").strip()
        if not args.sem_enviar:
            conferir_destino(destino, chave)

        print("Lendo as notas de venda e de brinde da cópia do banco...")
        lido = ler_banco(ini, dt.date.today())
        copia = lido["copia"]
        print(f"  Cópia do banco de {copia:%d/%m/%Y às %H:%M}; notas de {lido['inicio']:%d/%m/%Y} "
              f"a {lido['fim']:%d/%m/%Y}.")
        if dt.datetime.now().astimezone() - copia > dt.timedelta(days=DIAS_COPIA_VELHA):
            print(f"  Atenção: a cópia do banco tem mais de {DIAS_COPIA_VELHA} dias.")
        print(resumo_notas("Faturamento", lido["vendas"], lido["erros"].get("vendas")))
        print(resumo_notas("Brindes", lido["brindes"], lido["erros"].get("brindes")))
        if lido["descartadas"]:
            print(f"  Atenção: {lido['descartadas']} notas apontam para cliente ou produto que não existe no "
                  "cadastro do ERP e ficaram de fora.")

        pacote = {"copy_at": copia.isoformat(timespec="seconds"), "first_day": lido["inicio"].isoformat(),
                  "last_day": lido["fim"].isoformat(), "customers": lido["clientes"], "products": lido["produtos"]}
        if lido["vendas"] is not None:
            pacote["sales"] = lido["vendas"]
        if lido["brindes"] is not None:
            pacote["gifts"] = lido["brindes"]
        if args.forcar:
            pacote["force"] = True
        corpo = gzip.compress(json.dumps(pacote, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        if args.sem_enviar:
            print(f"\nNada foi enviado (--sem-enviar). O pacote teria {len(corpo) / 1024:.0f} KB.")
            registrar(f"TESTE leitura sem envio: notas de {lido['inicio']:%d/%m/%Y} a {lido['fim']:%d/%m/%Y}, "
                      f"{len(lido['vendas'] or [])} vendas e {len(lido['brindes'] or [])} brindes, "
                      f"{len(corpo) / 1024:.0f} KB")
            return 0

        print(f"Enviando para {destino} ({len(corpo) / 1024:.0f} KB)...")
        r = enviar(destino, chave, corpo)
    except Problema as e:
        print(f"\nNÃO SINCRONIZOU: {e}")
        if e.codigo == "MUITAS_REMOCOES":
            print("\nSe estiver certo (clientes ou produtos saíram do app de propósito), rode de novo confirmando:\n"
                  "  sincronizar-faturamento-e-brindes.bat --forcar")
        registrar(f"ERRO  {e}")
        return 1

    print(f"\nSincronização concluída (notas de {data_br(r['first_day'])} a {data_br(r['last_day'])}):")
    log = []
    for rotulo, chave_relato in (("Faturamento", "sales"), ("Brindes", "gifts")):
        linhas, pedaco = relato_origem(rotulo, r.get(chave_relato))
        print("\n".join(linhas))
        log.append(pedaco)
    registrar(f"OK    {'; '.join(log)}; notas de {data_br(r['first_day'])} a {data_br(r['last_day'])} ({destino})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
