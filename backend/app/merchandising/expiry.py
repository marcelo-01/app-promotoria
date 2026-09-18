"""A venda de um produto num cliente entre duas contagens.

Este módulo não fala com o banco. Recebe a história de um produto num cliente
(as `Series` do `evolution`), o que entrou pelas planilhas e o que o promotor
retirou por vencimento, e responde uma pergunta só: **quanto saiu pelo caixa
desta loja no intervalo entre duas contagens?**

A CONTA
-------
Tudo se apoia num intervalo — o CICLO, que são os dias entre a contagem atual e a
anterior. Dentro dele:

    venda = estoque anterior + faturado + brinde − estoque atual − vencidos

As três parcelas do meio são fatos conhecidos: as duas primeiras vêm das
planilhas do ERP, a última vem da mão do promotor. O que sobra depois de
descontá-las é a única coisa que a contagem não explica de outro jeito —
mercadoria que saiu pelo caixa.

Essa venda é um número que serve a mais de um veredito, e por isso ela sai numa
`Cycle` à parte: em `orders` ela vira a sugestão de pedido do vendedor, e no
aparelho do promotor ela vira os "dias para escoar" que decidem a coleta de
vencimento. Uma conta só, dois leitores — corrigir a venda aqui corrige os dois.

ONDE FICA O VEREDITO DO VENCIMENTO
----------------------------------
Em `frontend/src/lib/vencimento.js`, e não aqui.

O ciclo que decide a coleta termina na contagem que o promotor está fazendo
NAQUELE MOMENTO: o que precisa caber dentro de uma validade é o estoque que está
na loja com ele na frente, não o da visita passada. Essa ponta de cima não existe
no banco na hora em que o servidor monta a folha — ela está sendo digitada. Então
o servidor manda os ingredientes (`service._expiry_inputs`) e o aparelho fecha a
conta offline, no fim da contagem.

A regra que ele aplica é esta, e está escrita por extenso do outro lado:

    ciclos para escoar = estoque de hoje ÷ venda
    COLETA se (ciclos para escoar × dias do ciclo) > validade na chegada

O QUE ESTA CONTA NÃO FAZ
------------------------
Ela é ESTIMATIVA em dois pontos: o giro sai de um ciclo só (uma semana atípica
inverte o veredito), e a `venda` é um piso — entrega e venda que se anulem dentro
do mesmo intervalo, com a nota fora da planilha, somem juntas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional
from uuid import UUID

from app.merchandising.evolution import Series

# Diferença de quantidade abaixo disto é ruído de arredondamento (as quantidades
# são Numeric(15,3) virando float), não venda nem entrega.
EPS = 0.001


# ─── O ciclo: a venda entre duas contagens ────────────────────────────────────


@dataclass(frozen=True)
class Cycle:
    """O que aconteceu com um produto num cliente entre as duas últimas
    contagens completas — com a conta aberta.

    É o pedaço da história que os vereditos compartilham. Não julga nada:
    estoque zerado é um ciclo válido (para o vendedor, é o mais urgente), e quem
    decide se ele serve é quem o lê.
    """

    customer_id: UUID
    product_id: UUID

    previous_day: date       # a contagem anterior
    current_day: date        # a atual — a coleta de onde os números saíram
    cycle_days: int          # dias entre as duas
    previous_stock: float    # o que havia na contagem anterior
    current_stock: float     # o que há agora
    invoiced: float          # entrou pela planilha de faturamento
    gifted: float            # entrou pela planilha de brinde
    expired: float           # o promotor retirou por vencimento
    sold: float              # a venda do cliente no ciclo (nunca negativa)


def cycle_sale(
    serie: Series,
    invoiced: float = 0.0,
    gifted: float = 0.0,
    expired: float = 0.0,
) -> Optional[Cycle]:
    """A venda deste produto neste cliente no último ciclo.

    `invoiced`, `gifted` e `expired` são os totais **dentro do ciclo** — entre a
    contagem anterior (exclusive) e a atual (inclusive). Quem recorta a janela é
    quem consulta o banco; aqui já chegam somados.

    Devolve `None` quando não há ciclo:

    * menos de duas contagens completas — sem duas, não existe intervalo;
    * contagens no mesmo dia, que dariam ciclo de zero dia e divisão sem sentido.
    """
    completos = serie.complete_days()
    if len(completos) < 2:
        return None

    (dia_anterior, _, _, estoque_anterior) = completos[-2]
    (dia_atual, _, _, estoque_atual) = completos[-1]

    anterior, atual = date.fromisoformat(dia_anterior), date.fromisoformat(dia_atual)
    ciclo = (atual - anterior).days
    if ciclo <= 0:
        return None

    # A venda é o que sobra depois de descontar o que se sabe que entrou e o que
    # se sabe que foi para o lixo. Negativa não existe: entrou mercadoria que as
    # planilhas não cobriram, e isso não é venda ao contrário.
    venda = estoque_anterior + invoiced + gifted - estoque_atual - expired
    venda = max(0.0, venda)

    return Cycle(
        customer_id=serie.customer_id,
        product_id=serie.product_id,
        previous_day=anterior,
        current_day=atual,
        cycle_days=ciclo,
        previous_stock=estoque_anterior,
        current_stock=estoque_atual,
        invoiced=invoiced,
        gifted=gifted,
        expired=expired,
        sold=venda,
    )


def cycle_bounds(serie: Series) -> Optional[tuple[date, date]]:
    """As duas pontas do ciclo deste produto: a contagem anterior e a atual.

    É por elas que se recorta o que entrou e o que foi retirado no período. Fica
    aqui, e não em quem consulta o banco, para que a definição de ciclo exista num
    lugar só — se um dia ela mudar, muda aqui.
    """
    completos = serie.complete_days()
    if len(completos) < 2:
        return None
    return date.fromisoformat(completos[-2][0]), date.fromisoformat(completos[-1][0])


def cycle_sales(
    series: Iterable[Series],
    invoiced: Optional[dict[tuple[UUID, UUID], float]] = None,
    gifted: Optional[dict[tuple[UUID, UUID], float]] = None,
    expired: Optional[dict[tuple[UUID, UUID], float]] = None,
) -> dict[tuple[UUID, UUID], Cycle]:
    """O ciclo de cada (cliente, produto) que tem um.

    As três fontes vêm indexadas por `(cliente, produto)` — a mesma chave da
    série — e já somadas dentro do ciclo.
    """
    invoiced, gifted, expired = invoiced or {}, gifted or {}, expired or {}
    saida = {}
    for serie in series:
        chave = (serie.customer_id, serie.product_id)
        ciclo = cycle_sale(
            serie, invoiced.get(chave, 0.0), gifted.get(chave, 0.0), expired.get(chave, 0.0)
        )
        if ciclo:
            saida[chave] = ciclo
    return saida
