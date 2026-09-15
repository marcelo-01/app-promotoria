"""O pedido que o sistema sugere ao vendedor — e quando ele deixa de valer.

Este módulo não fala com o banco. Recebe o ciclo de um produto num cliente (a
`Cycle` de `expiry`, com a venda já calculada) e o fator de giro que o vendedor
escolheu para aquela loja, e responde: **quanto pedir?**

A CONTA
-------

    sugestão = venda × fator de giro − estoque atual

A venda é a mesma da coleta de vencimento — o que saiu pelo caixa entre as duas
últimas contagens completas. O fator é o vendedor quem diz, cliente a cliente,
de 1 a 3: com 1 o pedido repõe o que vendeu; com 2, dobra a cobertura. O que a
loja ainda tem em estoque desconta do pedido.

Sugestão de zero ou menos não é pedido: o estoque cobre a venda, e o produto
simplesmente não aparece na tela. Estoque zerado, ao contrário, é o caso mais
urgente — e é por isso que a `Cycle` não o descarta.

O RESET DE DOMINGO
------------------
A sugestão só vale na semana da coleta que a gerou. Uma sugestão feita sobre a
contagem da semana passada é perigosa: o vendedor pode já ter lançado aquele
pedido, e a mercadoria pode já estar na loja sem que a contagem tenha visto.

Não há tarefa agendada zerando nada: a regra é de DATA, como o visto verde do
promotor. A tela compara o dia da última coleta com o domingo mais recente —
coleta anterior a ele, sugestões zeradas até a próxima contagem. No domingo, o
"domingo mais recente" é o próprio dia, e tudo zera sozinho.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from app.merchandising.expiry import EPS, Cycle


@dataclass(frozen=True)
class Suggestion:
    """Quanto pedir de um produto num cliente, com a conta aberta.

    Os campos intermediários são o que a tela mostra embaixo do número: é por
    eles que o vendedor confere se a sugestão faz sentido antes de lançar.
    """

    customer_id: UUID
    product_id: UUID
    cycle_days: int
    sold: float
    current_stock: float
    factor: float
    suggested: int           # unidades inteiras, arredondadas para cima


def suggest(ciclo: Cycle, factor: float) -> Optional[Suggestion]:
    """A sugestão deste produto neste cliente, ou `None` se não há o que pedir.

    Arredonda para cima: pedido é em unidades inteiras, e meia unidade a mais
    é melhor do que faltar. O `EPS` evita que um resto de ponto flutuante
    (0,0004) vire uma unidade inteira.
    """
    bruto = ciclo.sold * factor - ciclo.current_stock
    if bruto <= EPS:
        return None

    return Suggestion(
        customer_id=ciclo.customer_id,
        product_id=ciclo.product_id,
        cycle_days=ciclo.cycle_days,
        sold=ciclo.sold,
        current_stock=ciclo.current_stock,
        factor=factor,
        suggested=math.ceil(bruto - EPS),
    )


def week_start(day: date) -> date:
    """O domingo mais recente, inclusive — se `day` é domingo, é ele mesmo."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def is_fresh(collected: date, today: date) -> bool:
    """A coleta ainda vale? Só se for desta semana (do domingo em diante)."""
    return collected >= week_start(today)
