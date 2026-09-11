"""A planilha de faturamento do ERP → as entradas de mercadoria em cada cliente.

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
COLUNAS = {
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

# Só saída de mercadoria entra. CFOP de venda começa em 5 (dentro do estado) ou
# 6 (fora). Entrada — devolução, retorno — começa em 1, 2 ou 3, e não é tratada
# aqui: a devolução só é lançada no ERP dias depois, quando a mercadoria volta
# fisicamente, e para esta conta isso chega tarde demais. Quem cobre a perda por
# validade é a retirada que o promotor registra no aplicativo.
CFOP_SAIDA = ("5", "6")


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


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


@dataclass
class Parsed:
    """O que saiu do arquivo, e o que ficou pelo caminho."""

    rows: list[Row] = field(default_factory=list)
    total: int = 0                       # linhas de dados lidas
    ignored_cfop: int = 0                # devolução e outras entradas
    ignored_incomplete: int = 0          # sem data, sem quantidade, sem chave
    missing_columns: list[str] = field(default_factory=list)

    @property
    def first_day(self) -> Optional[date]:
        return min((r.issued_on for r in self.rows), default=None)

    @property
    def last_day(self) -> Optional[date]:
        return max((r.issued_on for r in self.rows), default=None)


def parse(content: bytes) -> Parsed:
    """Arquivo .xlsx → linhas de venda aproveitáveis.

    Lê a primeira aba. Cabeçalho que não for encontrado é reportado em
    `missing_columns` em vez de estourar: uma exportação com uma coluna a menos
    tem de dizer QUAL falta, não morrer com erro de índice.
    """
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    linhas = ws.iter_rows(values_only=True)

    try:
        cabecalho = next(linhas)
    except StopIteration:
        return Parsed(missing_columns=sorted(COLUNAS.values()))

    posicao = {_chave(nome): i for i, nome in enumerate(cabecalho)}
    indices, faltando = {}, []
    for campo, titulo in COLUNAS.items():
        i = posicao.get(_chave(titulo))
        if i is None:
            faltando.append(titulo)
        else:
            indices[campo] = i

    if faltando:
        return Parsed(missing_columns=faltando)

    saida = Parsed()
    for linha in linhas:
        pega = lambda campo: linha[indices[campo]]  # noqa: E731
        if not any(v is not None for v in linha):
            continue
        saida.total += 1

        cfop = _texto(pega("cfop"))
        if not cfop.startswith(CFOP_SAIDA):
            saida.ignored_cfop += 1
            continue

        emitida = _data(pega("issued_on"))
        quantidade = _numero(pega("quantity"))
        venda = _texto(pega("sale_number"))
        item = _texto(pega("product_code"))

        if not emitida or not quantidade or quantidade <= 0 or not venda or not item:
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
            )
        )

    return saida
