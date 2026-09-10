"""Os dois números que o administrador olha antes de abrir qualquer filtro.

Este módulo não fala com o banco. Recebe a carteira — quais lojas cada promotor
deveria visitar — e as contagens já agrupadas por `consolidation`, e devolve o
que a tela mostra:

* **Cobertura do dia**: quantas lojas da carteira fecharam a visita. Fechar é
  ter as duas contagens, gôndola e estoque, porque é isso que faz a planilha
  sair. Contar meia visita como visita diria que o dia terminou justamente
  enquanto o administrador ainda não consegue exportar nada.

* **Visitas pela metade**: os pares em que só um lado chegou, do mais antigo
  para o mais novo. A tela de contagens já marca isso linha a linha, mas
  ordenada pela data mais recente e misturada com tudo o que deu certo. O que
  falta lá é a idade: meia visita de hoje é o promotor ainda dentro da loja;
  meia visita de três dias atrás é um telefonema.

A regra do par é a mesma da planilha — mesmo cliente, mesmo promotor, mesmo dia
local — e é reaproveitada de propósito. Se um dia ela mudar, muda nos três
lugares ao mesmo tempo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Sequence
from uuid import UUID

from app.merchandising.consolidation import Pair

# Estado de uma loja no dia
CLOSED = "closed"      # as duas contagens chegaram — a planilha dela sai
PARTIAL = "partial"    # só a gôndola ou só o estoque
MISSING = "missing"    # ninguém passou lá


# ─── Cobertura ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Coverage:
    """Quantas lojas de uma carteira fecharam o dia."""

    customers_total: int = 0
    closed: int = 0
    partial: int = 0
    missing: int = 0


@dataclass(frozen=True)
class PromoterCoverage:
    promoter_id: UUID
    promoter_name: Optional[str]
    coverage: Coverage


def _states_by_customer(pairs: Iterable[Pair]) -> dict[UUID, str]:
    """{customer_id: CLOSED|PARTIAL} para as lojas com contagem no dia.

    Loja atendida por dois promotores no mesmo dia forma dois pares. Basta um
    deles ter fechado para a loja estar fechada: a contagem dela existe inteira,
    não importa qual dos dois a fez.
    """
    estados: dict[UUID, str] = {}
    for par in pairs:
        customer_id = par.key[0]
        if par.complete:
            estados[customer_id] = CLOSED
        else:
            estados.setdefault(customer_id, PARTIAL)
    return estados


def _states_by_promoter(pairs: Iterable[Pair]) -> dict[tuple[UUID, UUID], str]:
    """{(promoter_id, customer_id): CLOSED|PARTIAL} — a mesma leitura, mas de
    quem foi até lá. É o que permite cobrar cada promotor pela própria carteira
    em vez de pelo total da operação."""
    estados: dict[tuple[UUID, UUID], str] = {}
    for par in pairs:
        customer_id, promoter_id, _ = par.key
        chave = (promoter_id, customer_id)
        if par.complete:
            estados[chave] = CLOSED
        else:
            estados.setdefault(chave, PARTIAL)
    return estados


def _count(customer_ids: set[UUID], estado_de) -> Coverage:
    fechadas = sum(1 for cid in customer_ids if estado_de(cid) == CLOSED)
    pela_metade = sum(1 for cid in customer_ids if estado_de(cid) == PARTIAL)
    return Coverage(
        customers_total=len(customer_ids),
        closed=fechadas,
        partial=pela_metade,
        missing=len(customer_ids) - fechadas - pela_metade,
    )


def coverage(assignments: Sequence, pairs: Iterable[Pair]) -> Coverage:
    """Cobertura da operação inteira no dia.

    O denominador é a carteira, não as lojas visitadas: sem ele não existe "18
    de 23", só "18". Contagem feita numa loja que não está na carteira de
    ninguém fica de fora — ela não tem denominador, e somá-la ao numerador
    faria a cobertura passar de 100%. Loja assim é falha de cadastro, e aparece
    como tal na tela de vínculos.
    """
    estados = _states_by_customer(pairs)
    clientes = {linha.customer_id for linha in assignments}
    return _count(clientes, estados.get)


def coverage_by_promoter(
    assignments: Sequence, pairs: Iterable[Pair]
) -> list[PromoterCoverage]:
    """Cobertura de cada promotor contra a própria carteira.

    Loja atendida por dois promotores conta na carteira dos dois — por isso a
    soma das linhas pode passar do total geral, que conta a loja uma vez só.
    """
    estados = _states_by_promoter(pairs)

    carteiras: dict[UUID, set[UUID]] = {}
    nomes: dict[UUID, Optional[str]] = {}
    for linha in assignments:
        carteiras.setdefault(linha.promoter_id, set()).add(linha.customer_id)
        nomes[linha.promoter_id] = linha.promoter_name

    return sorted(
        (
            PromoterCoverage(
                promoter_id=promoter_id,
                promoter_name=nomes.get(promoter_id),
                coverage=_count(
                    clientes, lambda cid, p=promoter_id: estados.get((p, cid))
                ),
            )
            for promoter_id, clientes in carteiras.items()
        ),
        key=lambda linha: (linha.promoter_name or "").lower(),
    )


# ─── Visitas pela metade ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class StuckPair:
    """Um par em que só um lado chegou, com a idade que já tem."""

    customer_id: UUID
    customer_name: Optional[str]
    promoter_id: UUID
    promoter_name: Optional[str]
    day: str
    days_waiting: int
    # O lado que falta ('gondola'/'estoque') e a contagem que já chegou — é ela
    # que a tela abre quando o administrador clica na linha.
    missing_side: str
    visit_id: UUID


def _days_between(day: str, today: str) -> int:
    """Dias entre o dia da contagem e hoje. Data inválida vale 0 — uma linha da
    lista não pode derrubar o painel inteiro."""
    try:
        return max((date.fromisoformat(today) - date.fromisoformat(day)).days, 0)
    except ValueError:
        return 0


def stuck_pairs(pairs: Iterable[Pair], today: str) -> list[StuckPair]:
    """Pares com um lado só, do mais antigo para o mais novo.

    Ordenar por idade, e não pela data mais recente, é a única diferença real
    entre esta lista e a tela de contagens — e é ela que faz a lista servir para
    alguma coisa: o que está em cima é o que já não se resolve sozinho.

    Meia visita de hoje entra na lista com idade 0, porque ela pode ser o
    promotor ainda dentro da loja. Quem separa uma coisa da outra é `days_waiting`
    e a contagem de `overdue` — esconder as de hoje deixaria o administrador sem
    saber, às seis da tarde, o que ficou para trás.
    """
    travados = []
    for par in pairs:
        faltando = par.missing
        if not faltando:
            continue

        # O par é incompleto: existe exatamente um lado, e é o que a tela abre.
        (presente,) = par.sides.values()
        customer_id, promoter_id, dia = par.key

        travados.append(
            StuckPair(
                customer_id=customer_id,
                customer_name=presente.customer_name,
                promoter_id=promoter_id,
                promoter_name=presente.promoter_name,
                day=dia,
                days_waiting=_days_between(dia, today),
                missing_side=faltando,
                visit_id=presente.id,
            )
        )

    return sorted(
        travados,
        key=lambda linha: (-linha.days_waiting, (linha.customer_name or "").lower()),
    )


def overdue(stuck: Sequence[StuckPair]) -> int:
    """Quantas dessas já passaram do dia em que foram feitas — as que o promotor
    não vai mais fechar sem alguém pedir."""
    return sum(1 for linha in stuck if linha.days_waiting >= 1)
