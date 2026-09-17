"""As planilhas do ERP → as entradas de mercadoria em cada cliente.

São duas, com formatos diferentes: a de FATURAMENTO (o que foi vendido) e a de
BRINDES (o que foi enviado sem cobrar). Na conta as duas se somam — mercadoria é
mercadoria, chegou é chegou — mas os arquivos não se parecem, e por isso cada um
tem o seu mapa de colunas aqui.

Este módulo não fala com o banco: recebe o arquivo, devolve linhas e um relato
do que não deu para aproveitar. Quem casa com o cadastro e grava é o serviço.

AS COLUNAS QUE IMPORTAM, E POR QUÊ ESTAS
----------------------------------------
A exportação tem 76 colunas. Seis servem, e a escolha de cada uma tem motivo:

* **EMISSÃO** e não DATA ENTREGA — a de entrega vem vazia na maior parte das
  linhas. E a emissão basta: sem ela o sistema só sabe que a mercadoria chegou
  "entre duas visitas", uma janela de sete dias. Uma data com dois dias de erro
  é ganho grande sobre isso.

* **N. PEÇAS** e não QUANTIDADE — a coluna de quantidade vem na unidade de
  faturamento, que mistura unidades e QUILOS (queijo é vendido por peso).
  Somá-la jogaria quilo e unidade no mesmo balde. Peças é o que o promotor
  conta na prateleira, que é o outro lado desta conta.

* **Nº VENDA + COD. ITEM + EMPRESA** como chave da linha, e não a nota fiscal:
  a venda do próprio dia ainda não faturada vem sem número de nota, e essas
  linhas entrariam duplicadas no upload do dia seguinte. A empresa entra porque
  são duas (matriz e filial) e nada garante que a numeração siga compartilhada.

* **CNPJ** para casar o cliente e **COD. ITEM** para casar o produto — são os
  dois campos que o cadastro deste app já reservava para o dia da integração.

UMA ARMADILHA QUE VALE ESTAR ESCRITA
------------------------------------
A planilha tem uma coluna chamada VENCIMENTO. Ela **não** é a validade do
produto: é a data de pagar a duplicata (emissão + prazo da opção de pagamento).
Não há lote, fabricação nem validade em nenhuma das 76 colunas — e é por isso
que a estimativa continua necessária e a coleta do promotor, insubstituível.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Optional

# Cabeçalhos, como saem do ERP. A comparação é feita sem acento, sem espaço
# sobrando e sem caixa — "DATA ENTREGA " veio com espaço no fim no primeiro
# arquivo, e isso não pode quebrar a importação.
COLUNAS_VENDA = {
    "company": "EMPRESA",
    "sale_number": "Nº VENDA",
    "invoice": "NOTA FISCAL",
    "issued_on": "EMISSÃO",
    "cfop": "CFOP",
    "customer_code": "COD. CLIENTE",
    "customer_name": "CLIENTE",
    "customer_document": "CNPJ / CPF",
    "product_code": "COD. ITEM",
    "product_name": "ITEM",
    "quantity": "N. PEÇAS",
}

# A planilha de brindes é outro relatório: menos colunas, nomes próprios, e uma
# ausência que custa caro — não há contagem de PEÇAS, só a quantidade na unidade
# de faturamento (ver `_pecas` abaixo).
#
# O cabeçalho vem com "COD PROUTO", sem o D, direto do ERP. A comparação ignora
# pontuação e caixa, então "COD. PRODUTO" também casaria se um dia arrumarem —
# mas o que está no arquivo hoje é o com o erro.
COLUNAS_BRINDE = {
    "sale_number": "Nº BRINDE",
    "invoice": "NOTA FISCAL",
    "issued_on": "DATA",
    "cfop": "CFOP",
    "customer_code": "CÓD",
    "customer_name": "CLIENTE",
    "customer_document": "CNPJ",
    "product_code": "COD PROUTO",
    "product_name": "ITEM",
    "quantity": "QUANTIDADE",
    "reason": "MOTIVO",
}

COLUNAS = {"venda": COLUNAS_VENDA, "brinde": COLUNAS_BRINDE}

# Colunas que podem ou não estar no arquivo. A de brindes vai passar a sair com
# contagem de peças; enquanto não sair, vale o desencalhe do `_pecas` abaixo.
# Mais de um nome por campo porque o título exato depende de como o relatório for
# configurado no ERP, e não vale quebrar a importação por causa de um acento.
COLUNAS_OPCIONAIS = {
    "venda": {},
    "brinde": {"pieces": ("N. PEÇAS", "PEÇAS", "QUANTIDADE PEÇAS")},
}

# ── O que entra de cada planilha ──────────────────────────────────────────
#
# FATURAMENTO: só saída de mercadoria. CFOP de venda começa em 5 (dentro do
# estado) ou 6 (fora). Entrada — devolução, retorno — começa em 1, 2 ou 3, e não
# é tratada aqui: a devolução só é lançada no ERP dias depois, quando a
# mercadoria volta fisicamente, e para esta conta isso chega tarde demais. Quem
# cobre a perda por validade é a retirada que o promotor registra no aplicativo.
CFOP_VENDA = ("5", "6")

# BRINDE: o relatório de brindes NÃO é só de brindes. Ele mistura, no mesmo
# arquivo, remessa ao cliente com transferência entre filiais, retorno de
# mercadoria, consumo interno e baixa por perda — e nenhuma dessas últimas põe
# mercadoria no estoque de um cliente.
#
# O corte é pelo CFOP, e não pela coluna MOTIVO: 5910 e 6910 são exatamente
# "remessa em bonificação, doação ou brinde", saída da empresa para o cliente.
# MOTIVO é texto livre digitado por gente e muda de redação; CFOP é código
# fiscal. No primeiro arquivo recebido os dois critérios selecionam o mesmo
# conjunto — 368 linhas de 647 —, e o CFOP é o que continua valendo quando
# alguém inventar um motivo novo.
CFOP_BRINDE = ("5910", "6910")


class UnreadableWorkbook(ValueError):
    """O arquivo tem extensão .xlsx, mas não é um .xlsx que se consiga abrir.

    O caso típico é o ERP exportar em .xls (ou uma tabela HTML com esse nome) e
    alguém só trocar a extensão. Sem este erro isso estourava como 500 genérico,
    e "Erro interno do servidor" não diz a ninguém que a saída é salvar de novo
    pelo Excel.
    """


def _texto(valor) -> str:
    """Célula → texto limpo. Célula vazia é '' (o leitor devolve '' e não None).

    Número inteiro guardado como float vira '5102', não '5102.0': CFOP, código
    do item e nº da venda são comparados como texto, e uma exportação que os
    grave como número não pode mudar a chave da linha.
    """
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _chave(nome) -> str:
    """Cabeçalho → forma comparável: sem acento, sem pontuação, sem caixa."""
    limpo = _texto(nome).upper()
    for de, para in (("Á", "A"), ("Ã", "A"), ("Â", "A"), ("É", "E"), ("Ê", "E"),
                     ("Í", "I"), ("Ó", "O"), ("Õ", "O"), ("Ô", "O"), ("Ú", "U"),
                     ("Ç", "C"), ("º", "")):
        limpo = limpo.replace(de, para)
    return re.sub(r"[^A-Z0-9]", "", limpo)


def _digitos(valor) -> str:
    return re.sub(r"\D", "", _texto(valor))


def _data(valor) -> Optional[date]:
    """Célula → data. O ERP exporta texto 'dd/mm/aaaa', mas a mesma planilha
    salva de novo pelo Excel pode virar data de verdade — os dois entram."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = _texto(valor)
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _numero(valor) -> Optional[float]:
    """Célula → número. Aceita o decimal com vírgula que o Excel às vezes deixa
    passar como texto."""
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = _texto(valor).replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


@dataclass(frozen=True)
class Row:
    """Uma linha de venda, já limpa — ainda sem casar com o cadastro."""

    company: str
    sale_number: str
    invoice: Optional[str]
    issued_on: date
    cfop: str
    customer_code: str
    customer_name: str
    customer_document: str      # só dígitos
    product_code: str
    product_name: str
    quantity: float
    # Só a planilha de brindes traz — é o que o administrador confere para saber
    # se o filtro de CFOP pegou o que devia.
    reason: str = ""


@dataclass
class Parsed:
    """O que saiu do arquivo, e o que ficou pelo caminho."""

    rows: list[Row] = field(default_factory=list)
    total: int = 0                       # linhas de dados lidas
    ignored_cfop: int = 0                # o que não é remessa ao cliente
    ignored_incomplete: int = 0          # sem data, sem quantidade, sem chave
    # Linhas em que a quantidade não é contagem de peças (ver `_pecas`)
    ignored_weight: int = 0
    missing_columns: list[str] = field(default_factory=list)

    @property
    def first_day(self) -> Optional[date]:
        return min((r.issued_on for r in self.rows), default=None)

    @property
    def last_day(self) -> Optional[date]:
        return max((r.issued_on for r in self.rows), default=None)


def _pecas(valor, kind: str) -> Optional[float]:
    """Quantidade da linha, em PEÇAS — ou `None` quando não dá para saber.

    Na planilha de faturamento existe a coluna `N. PEÇAS`, e o número já vem
    certo. Na de brindes não existe: há só `QUANTIDADE`, na unidade de
    faturamento, que mistura unidades e QUILOS (queijo e manteiga a granel são
    vendidos por peso) sem nenhuma coluna dizendo qual é qual.

    O que se pode afirmar com segurança é isto: **contagem de peças é inteira.**
    Uma linha de brinde com 1,55 ou 32,75 é peso, e transformá-la em "32,75
    peças" de um queijo de 4 kg inflaria a entrada em oito vezes — estragando a
    venda calculada daquele produto naquele cliente.

    Então fracionário é descartado e contado à parte, para o administrador saber
    o tamanho do buraco. Descartar subestima a entrada, o que subestima a venda,
    o que provoca aviso A MAIS — o lado seguro do erro.

    A saída definitiva é o relatório trazer a contagem de peças — e quando ela
    vier, `COLUNAS_OPCIONAIS` a encontra e esta função sai do caminho.
    """
    numero = _numero(valor)
    if numero is None:
        return None
    if kind == "brinde" and abs(numero - round(numero)) > 1e-6:
        return None
    return numero


def _celula(linha, i: Optional[int]):
    """A célula `i` da linha — ou None quando a coluna não existe ou a linha
    veio mais curta que o cabeçalho (o leitor não completa linha nenhuma)."""
    if i is None or i >= len(linha):
        return None
    return linha[i]


def parse(content: bytes, kind: str = "venda") -> Parsed:
    """Arquivo .xlsx → linhas de entrada de mercadoria aproveitáveis.

    `kind` escolhe o mapa de colunas e o filtro de CFOP: `'venda'` para a
    planilha de faturamento, `'brinde'` para a de brindes.

    Lê a primeira aba. Cabeçalho que não for encontrado é reportado em
    `missing_columns` em vez de estourar: uma exportação com uma coluna a menos
    tem de dizer QUAL falta, não morrer com erro de índice.

    O leitor é o calamine, e não o openpyxl, por tamanho: dois meses de
    faturamento são 25 MB e 60 mil linhas, que o openpyxl leva mais de meio
    minuto para percorrer (o dobro na VPS de 1 vCPU) — e a planilha passa por
    aqui duas vezes, na prévia e na importação. O calamine faz o mesmo em três
    segundos. O preço é memória: ele carrega a aba inteira (uns 400 MB para
    esse arquivo), e é isso que dita o teto de tamanho aceito na rota.
    """
    from python_calamine import CalamineWorkbook

    colunas = COLUNAS[kind]
    try:
        wb = CalamineWorkbook.from_filelike(BytesIO(content))
    except Exception as erro:  # zip corrompido, HTML com nome de .xlsx…
        raise UnreadableWorkbook(
            "Este arquivo não abre como planilha .xlsx. Se o ERP exportou em "
            ".xls, abra no Excel e salve como \"Pasta de Trabalho do Excel "
            "(.xlsx)\" antes de anexar."
        ) from erro
    if not wb.sheet_names:
        return Parsed(missing_columns=sorted(colunas.values()))
    linhas = wb.get_sheet_by_name(wb.sheet_names[0]).iter_rows()

    try:
        cabecalho = next(linhas)
    except StopIteration:
        return Parsed(missing_columns=sorted(colunas.values()))

    posicao = {_chave(nome): i for i, nome in enumerate(cabecalho)}
    indices, faltando = {}, []
    for campo, titulo in colunas.items():
        i = posicao.get(_chave(titulo))
        if i is None:
            faltando.append(titulo)
        else:
            indices[campo] = i

    if faltando:
        return Parsed(missing_columns=faltando)

    # Contagem de peças, quando o relatório trouxer: é ela que manda, e aí não há
    # peso disfarçado de quantidade nem linha descartada.
    for campo, apelidos in COLUNAS_OPCIONAIS[kind].items():
        for apelido in apelidos:
            i = posicao.get(_chave(apelido))
            if i is not None:
                indices[campo] = i
                break

    saida = Parsed()
    for linha in linhas:
        pega = lambda campo: _celula(linha, indices.get(campo))  # noqa: E731
        if not any(v not in (None, "") for v in linha):
            continue
        saida.total += 1

        cfop = _texto(pega("cfop"))
        aceita = cfop in CFOP_BRINDE if kind == "brinde" else cfop.startswith(CFOP_VENDA)
        if not aceita:
            saida.ignored_cfop += 1
            continue

        emitida = _data(pega("issued_on"))
        venda = _texto(pega("sale_number"))
        item = _texto(pega("product_code"))
        if not emitida or not venda or not item:
            saida.ignored_incomplete += 1
            continue

        # Com coluna de peças, é ela; sem, resta desencalhar a quantidade.
        if "pieces" in indices:
            quantidade = _numero(pega("pieces"))
        else:
            quantidade = _pecas(pega("quantity"), kind)
        if quantidade is None:
            # Peso disfarçado de quantidade: não vira peça, e não se chuta.
            saida.ignored_weight += 1
            continue
        if quantidade <= 0:
            saida.ignored_incomplete += 1
            continue

        saida.rows.append(
            Row(
                company=_texto(pega("company")) or "—",
                sale_number=venda,
                invoice=_texto(pega("invoice")) or None,
                issued_on=emitida,
                cfop=cfop,
                customer_code=_texto(pega("customer_code")),
                customer_name=_texto(pega("customer_name")),
                customer_document=_digitos(pega("customer_document")),
                product_code=item,
                product_name=_texto(pega("product_name")),
                quantity=quantidade,
                reason=_texto(pega("reason")),
            )
        )

    return saida
