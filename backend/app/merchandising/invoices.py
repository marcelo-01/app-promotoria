"""As notas do ERP → as entradas de mercadoria em cada cliente.

São duas origens, com regras próprias: o FATURAMENTO (o que foi vendido) e os
BRINDES (o que foi enviado sem cobrar). Na conta as duas se somam — mercadoria é
mercadoria, chegou é chegou —, mas cada uma tem o seu filtro de CFOP.

As notas chegam do computador da empresa, que lê a cópia do banco do ERP
(`sync/sincronizar.py`) e manda o pacote que `erp_sync.py` confere. Até
nov/2026 elas vinham em planilhas exportadas do ERP e anexadas à mão; o pacote
traz os mesmos campos, lidos das tabelas de onde o relatório os tirava, e as
regras daqui são as mesmas da planilha. Comparado o mês de outubro/2026 inteiro,
cada item da planilha de faturamento estava no banco com as mesmas peças.

Este módulo não fala com o banco: recebe as notas, devolve linhas e um relato
do que não deu para aproveitar. Quem casa com o cadastro e grava é o serviço.

OS CAMPOS QUE IMPORTAM, E POR QUÊ ESTES
---------------------------------------
* **A data da nota** (VENDAS.DATA, a EMISSÃO da planilha) e não a de saída ou a
  de entrega — a de entrega vinha vazia na maior parte das linhas. E a emissão
  basta: sem ela o sistema só sabe que a mercadoria chegou "entre duas
  visitas", uma janela de sete dias. Uma data com dois dias de erro é ganho
  grande sobre isso.

* **As peças** (NUM_PECAS, a coluna N. PEÇAS da planilha) e não a QUANTIDADE —
  a quantidade vem na unidade de faturamento, que mistura unidades e QUILOS
  (queijo é vendido por peso). Somá-la jogaria quilo e unidade no mesmo balde.
  Peças é o que o promotor conta na prateleira, que é o outro lado desta conta.
  No brinde o banco tem a contagem de verdade (6 peças); a planilha de brindes
  trazia peso ÷ peso da peça (6,405 peças) e, antes disso, nem trazia peças.

* **Nº da venda + item + empresa** como chave da linha, e não a nota fiscal: a
  venda do próprio dia ainda não faturada vem sem número de nota.

* **CNPJ** para casar o cliente e **código do item** (PRODUTOS.CODIGO, o "COD.
  ITEM" da planilha) para casar o produto — são os dois campos que o cadastro
  deste app já reservava para o dia da integração.

UMA AUSÊNCIA QUE VALE ESTAR ESCRITA
-----------------------------------
Não há lote, fabricação nem validade nas notas do ERP (a planilha tinha uma
coluna VENCIMENTO, mas era a data de pagar a duplicata). É por isso que a
estimativa continua necessária e a coleta do promotor, insubstituível.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional, Sequence

from app.merchandising.schemas import ErpCustomer, ErpDocument, ErpProduct

# ── O que entra de cada origem ────────────────────────────────────────────
#
# FATURAMENTO: só saída de mercadoria. CFOP de venda começa em 5 (dentro do
# estado) ou 6 (fora). Entrada — devolução, retorno — começa em 1, 2 ou 3, e não
# é tratada aqui: a devolução só é lançada no ERP dias depois, quando a
# mercadoria volta fisicamente, e para esta conta isso chega tarde demais. Quem
# cobre a perda por validade é a retirada que o promotor registra no aplicativo.
CFOP_VENDA = ("5", "6")

# BRINDE: a tabela de brindes do ERP NÃO é só de brindes. Ela mistura remessa ao
# cliente com transferência entre filiais, retorno de mercadoria, consumo
# interno e baixa por perda — e nenhuma dessas últimas põe mercadoria no estoque
# de um cliente.
#
# O corte é pelo CFOP, e não pelo motivo: 5910 e 6910 são exatamente "remessa em
# bonificação, doação ou brinde", saída da empresa para o cliente. O motivo é
# cadastro de gente e ganha opção nova; CFOP é código fiscal. Em outubro/2026 o
# CFOP deixou entrar BRINDE - VENCIDO, os três BRINDE - DANIFICADO, DOAÇÃO,
# BRINDE - DEGUSTAÇÃO e BRINDE - PAGAMENTO DE CONTRATO, e deixou de fora
# RETORNO, TRANSFERÊNCIA, CONSUMO INTERNO e PERDA. A planilha que se anexava
# antes já vinha filtrada pelos quatro primeiros motivos; os outros três
# aparecem na quebra por motivo da tela, para quem quiser conferir.
CFOP_BRINDE = ("5910", "6910")


def aceita_cfop(kind: str, cfop: str) -> bool:
    """O item é entrada de mercadoria no cliente, pelo CFOP da origem?"""
    if kind == "brinde":
        return cfop in CFOP_BRINDE
    return cfop.startswith(CFOP_VENDA)


def _digitos(valor: Optional[str]) -> str:
    return re.sub(r"\D", "", valor or "")


def _texto(valor: Optional[str]) -> str:
    return " ".join((valor or "").split())


@dataclass(frozen=True)
class Row:
    """Um item de nota, já limpo — ainda sem casar com o cadastro."""

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
    # Só o brinde traz — é o que o administrador confere para saber se o filtro
    # de CFOP pegou o que devia.
    reason: str = ""


@dataclass
class Parsed:
    """O que saiu das notas, e o que ficou pelo caminho."""

    first_day: date
    last_day: date
    rows: list[Row] = field(default_factory=list)
    total: int = 0                       # itens de nota lidos
    ignored_cfop: int = 0                # o que não é remessa ao cliente
    ignored_incomplete: int = 0          # sem peças ou sem código de produto


def from_package(
    documents: Sequence[ErpDocument],
    customers: Mapping[int, ErpCustomer],
    products: Mapping[int, ErpProduct],
    kind: str,
    first_day: date,
    last_day: date,
) -> Parsed:
    """Notas do pacote → linhas de entrada de mercadoria aproveitáveis.

    `kind` escolhe o filtro de CFOP: `'venda'` para o faturamento, `'brinde'`
    para os brindes. Cada nota já vem com um item por produto e CFOP; o mesmo
    produto em dois CFOPs vira duas linhas aqui, e o serviço as soma na chave.

    As referências (cliente e produto de cada nota) já foram conferidas em
    `erp_sync.conferir_pacote`: aqui elas existem.
    """
    saida = Parsed(first_day=first_day, last_day=last_day)
    for nota in documents:
        cliente = customers[nota.customer]
        for item in nota.items:
            saida.total += 1

            cfop = (item.cfop or "").strip()
            if not aceita_cfop(kind, cfop):
                saida.ignored_cfop += 1
                continue

            produto = products[item.product]
            codigo = (produto.code or "").strip()
            # Item pesado sem a contagem de peças (NUM_PECAS zero) não vira peça
            # chutada; produto sem código no ERP não casa com cadastro nenhum.
            if not codigo or item.pieces <= 0:
                saida.ignored_incomplete += 1
                continue

            saida.rows.append(
                Row(
                    company=_texto(nota.company) or "—",
                    sale_number=str(nota.number),
                    invoice=_texto(nota.invoice) or None,
                    issued_on=nota.issued_on,
                    cfop=cfop,
                    customer_code=_texto(cliente.code) or str(cliente.erp_id),
                    customer_name=_texto(cliente.name),
                    customer_document=_digitos(cliente.document),
                    product_code=codigo,
                    product_name=_texto(produto.name),
                    quantity=round(float(item.pieces), 3),
                    reason=_texto(nota.reason),
                )
            )
    return saida
