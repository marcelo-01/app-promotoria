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


def forecast(
    serie: Series,
    shelf_life: int,
    invoiced: float = 0.0,
    gifted: float = 0.0,
    expired: float = 0.0,
) -> Optional[Forecast]:
    """O veredito deste produto neste cliente.

    `invoiced`, `gifted` e `expired` são os totais **dentro do ciclo** — entre a
    contagem anterior (exclusive) e a atual (inclusive). Quem recorta a janela é
    quem consulta o banco; aqui já chegam somados.

    Devolve `None` quando não há o que dizer:

    * menos de duas contagens completas — sem duas, não existe ciclo;
    * contagens no mesmo dia, que dariam ciclo de zero dia e divisão sem sentido;
    * estoque atual zerado — não há mercadoria para vencer nem data para ler.
    """
    completos = serie.complete_days()
    if len(completos) < 2:
        return None

    (dia_anterior, _, _, estoque_anterior) = completos[-2]
    (dia_atual, _, _, estoque_atual) = completos[-1]

    ciclo = (date.fromisoformat(dia_atual) - date.fromisoformat(dia_anterior)).days
    if ciclo <= 0 or estoque_atual <= EPS:
        return None

    # A venda é o que sobra depois de descontar o que se sabe que entrou e o que
    # se sabe que foi para o lixo. Negativa não existe: entrou mercadoria que as
    # planilhas não cobriram, e isso não é venda ao contrário.
    venda = estoque_anterior + invoiced + gifted - estoque_atual - expired
    venda = max(0.0, venda)

    if venda <= EPS:
        # Não girou nada no ciclo. Estoque parado não sai sozinho — vence.
        ciclos = dias = None
        motivo = "parado"
    else:
        ciclos = estoque_atual / venda
        dias = ciclos * ciclo
        motivo = "nao_escoa" if dias > shelf_life else ""

    return Forecast(
        customer_id=serie.customer_id,
        product_id=serie.product_id,
        cycle_days=ciclo,
        previous_stock=estoque_anterior,
        current_stock=estoque_atual,
        invoiced=invoiced,
        gifted=gifted,
        expired=expired,
        sold=venda,
        cycles_to_clear=ciclos,
        days_to_clear=dias,
        shelf_life=shelf_life,
        alert=bool(motivo),
        reason=motivo,
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


def forecasts(
    series: Iterable[Series],
    shelf_lives: dict[UUID, Optional[int]],
    invoiced: Optional[dict[tuple[UUID, UUID], float]] = None,
    gifted: Optional[dict[tuple[UUID, UUID], float]] = None,
    expired: Optional[dict[tuple[UUID, UUID], float]] = None,
) -> dict[tuple[UUID, UUID], Forecast]:
    """O veredito de cada (cliente, produto) que tem um a dar.

    As três fontes vêm indexadas por `(cliente, produto)` — a mesma chave da
    série — e já somadas dentro do ciclo. Produto sem validade na chegada
    cadastrada fica de fora inteiro: sem saber quanto tempo a mercadoria aguenta,
    não há com o que comparar, e inventar um número seria pior que ficar calado.
    """
    invoiced, gifted, expired = invoiced or {}, gifted or {}, expired or {}
    saida = {}

    for serie in series:
        vida = shelf_lives.get(serie.product_id)
        if not vida or vida <= 0:
            continue

        chave = (serie.customer_id, serie.product_id)
        veredito = forecast(
            serie, vida,
            invoiced.get(chave, 0.0), gifted.get(chave, 0.0), expired.get(chave, 0.0),
        )
        if veredito:
            saida[chave] = veredito

    return saida
