"""Qual produto precisa ter o vencimento coletado — e por quê.

Este módulo não fala com o banco. Recebe a história de um produto num cliente
(as `Series` do `evolution`), o que entrou pelas planilhas e o que o promotor
retirou por vencimento, e responde uma pergunta só: **no ritmo desta loja, o
estoque que está lá hoje dura mais do que a mercadoria aguenta?**

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
`Cycle` à parte: daqui saem os "dias para escoar" que decidem a coleta de
vencimento, e em `orders` sai a sugestão de pedido do vendedor. Uma conta só,
dois leitores — corrigir a venda aqui corrige os dois.

Daí saem os dois números que decidem:

    ciclos para escoar = estoque atual ÷ venda
    COLETA se (ciclos para escoar × dias do ciclo) > validade na chegada

Ou seja: se o estoque de hoje, no ritmo de hoje, leva mais tempo para sair do que
a mercadoria tem de vida ao chegar, ela vai vencer na prateleira.

O QUE ESTA CONTA NÃO FAZ
------------------------
Ela **não sabe a idade do que está na loja**. Pergunta "esse estoque cabe numa
validade?", não "essas unidades específicas são velhas?". Duas consequências que
valem estar escritas, porque não são defeito e sim desenho:

* Ela avisa cedo e não alivia. Um produto de giro lento entra na lista já na
  segunda contagem e fica lá enquanto a cobertura for alta.
* Ela para de avisar se a venda acelerar, mesmo que ainda haja mercadoria velha
  na loja. A cobertura despenca, e a conta não tem como saber que aquelas
  unidades estão lá desde sempre.

E ela continua sendo ESTIMATIVA em dois pontos: o giro sai de um ciclo só (uma
semana atípica inverte o veredito), e a `venda` é um piso — entrega e venda que
se anulem dentro do mesmo intervalo, com a nota fora da planilha, somem juntas.

A data impressa na embalagem continua sendo a única verdade de campo, e só o
promotor a enxerga. Esta conta escolhe A QUEM PERGUNTAR; não substitui a pergunta.
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


# ─── O veredito: coletar o vencimento? ────────────────────────────────────────


@dataclass(frozen=True)
class Forecast:
    """O veredito de um produto num cliente, com a conta aberta.

    Os campos intermediários não são enfeite: é por eles que a tela explica ao
    promotor POR QUE aquele produto apareceu, e é por eles que se confere a conta
    quando alguém desconfia dela.
    """

    customer_id: UUID
    product_id: UUID

    cycle_days: int          # dias entre as duas últimas contagens completas
    previous_stock: float    # o que havia na contagem anterior
    current_stock: float     # o que há agora
    invoiced: float          # entrou pela planilha de faturamento
    gifted: float            # entrou pela planilha de brinde
    expired: float           # o promotor retirou por vencimento
    sold: float              # a venda do cliente no ciclo (nunca negativa)

    # None quando a venda deu zero ou menos: o estoque não escoa nunca.
    cycles_to_clear: Optional[float]
    days_to_clear: Optional[float]

    shelf_life: int          # validade na chegada, do cadastro do produto
    alert: bool
    reason: str              # 'nao_escoa', 'parado' ou '' (sem alerta)


def forecast(ciclo: Cycle, shelf_life: int) -> Optional[Forecast]:
    """O veredito deste produto neste cliente.

    Devolve `None` com o estoque atual zerado: não há mercadoria para vencer nem
    data para ler. (O ciclo continua existindo — é o vendedor quem se importa
    com ele nesse caso, não o promotor.)
    """
    if ciclo.current_stock <= EPS:
        return None

    if ciclo.sold <= EPS:
        # Não girou nada no ciclo. Estoque parado não sai sozinho — vence.
        ciclos = dias = None
        motivo = "parado"
    else:
        ciclos = ciclo.current_stock / ciclo.sold
        dias = ciclos * ciclo.cycle_days
        motivo = "nao_escoa" if dias > shelf_life else ""

    return Forecast(
        customer_id=ciclo.customer_id,
        product_id=ciclo.product_id,
        cycle_days=ciclo.cycle_days,
        previous_stock=ciclo.previous_stock,
        current_stock=ciclo.current_stock,
        invoiced=ciclo.invoiced,
        gifted=ciclo.gifted,
        expired=ciclo.expired,
        sold=ciclo.sold,
        cycles_to_clear=ciclos,
        days_to_clear=dias,
        shelf_life=shelf_life,
        alert=bool(motivo),
        reason=motivo,
    )
