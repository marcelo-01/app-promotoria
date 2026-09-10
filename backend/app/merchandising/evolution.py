"""A evolução do estoque do cliente — o que mudou entre uma contagem e outra.

Este módulo não fala com o banco. Recebe as contagens enviadas e os itens delas,
monta a história de cada produto em cada cliente, e responde as perguntas que só
o tempo responde: o que parou de girar, o que sumiu da loja, o que voltou, e o
que está encalhado no depósito enquanto a gôndola fica vazia.

O QUE ESTES NÚMEROS SÃO — E O QUE NÃO SÃO
-----------------------------------------
Este app não conhece entregas nem pedidos, então a diferença entre duas
contagens é LÍQUIDA, nunca bruta. Estoque que subiu quer dizer que houve entrega
de pelo menos aquilo; estoque que caiu, que saiu pelo menos aquilo. Se entrou e
saiu no mesmo intervalo, o número esconde os dois — e quanto mais longo o
intervalo, mais ele subestima. Por isso nada aqui se chama "venda": é sempre
variação entre contagens, que é um piso e não uma medição.

A CONTAGEM É IRREGULAR — E A CONTA TEM DE AGUENTAR ISSO
------------------------------------------------------
O promotor não passa todo dia, e nem sempre no mesmo intervalo. Duas
consequências que atravessam o módulo inteiro:

* A série anda por CONTAGEM, não por dia. Não existe interpolação: dia sem
  contagem é dia sem dado, e inventar o valor dele seria inventar o estoque.

* As comparações de total usam só os dias COMPLETOS — aqueles em que gôndola e
  estoque foram contados. É a mesma regra da planilha, e pelo mesmo motivo: num
  dia em que só a gôndola chegou, o total da loja aparece menor do que é, e todo
  produto guardado no depósito seria lido como "sumiu".

Produto que não aparece nos itens de uma contagem que aconteceu é lido como
zero. É a leitura mais provável — o promotor passou o dedo pela lista e não
achou o produto — mas continua sendo leitura: enquanto a tela de contagem não
tiver um "não tem" explícito, ausência e zero são a mesma coisa no banco.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Optional, Sequence
from uuid import UUID

from app.merchandising.consolidation import ESTOQUE, GONDOLA, SIDES, as_utc, local_day


def _moment(visit) -> datetime:
    """Quando esta contagem foi fechada — desempata duas do mesmo lado no mesmo
    dia, exatamente como a planilha desempata (ver `consolidation`)."""
    marca = visit.submitted_at or visit.visited_at or visit.created_at
    return as_utc(marca) if marca else datetime.min.replace(tzinfo=timezone.utc)


def _package_size(row) -> float:
    """Unidades por caixa. Nulo ou zero vale 1 — produto sem caixa cadastrada é
    contado como se a caixa fosse a própria unidade, nunca como zero."""
    return float(row.package_size) if row.package_size else 1.0


# ─── A história de um produto num cliente ─────────────────────────────────────


@dataclass
class Series:
    """Quanto havia deste produto neste cliente, em cada dia contado.

    `days` guarda só os lados efetivamente contados: `{'2026-09-10': {'gondola':
    12.0, 'estoque': 0.0}}`. Um dia em que só a gôndola chegou tem uma chave só,
    e é por isso que as contas de total olham `complete_days`.
    """

    customer_id: UUID
    customer_name: Optional[str]
    product_id: UUID
    product_name: Optional[str]
    days: dict[str, dict[str, float]] = field(default_factory=dict)

    def complete_days(self) -> list[tuple[str, float, float, float]]:
        """(dia, gôndola, estoque, total) dos dias com os dois lados contados,
        do mais antigo para o mais novo."""
        completos = []
        for dia in sorted(self.days):
            lados = self.days[dia]
            if all(lado in lados for lado in SIDES):
                gondola, estoque = lados[GONDOLA], lados[ESTOQUE]
                completos.append((dia, gondola, estoque, gondola + estoque))
        return completos


def build_series(visits: Iterable, item_rows: Sequence) -> list[Series]:
    """Contagens + itens → a história de cada (cliente, produto).

    Recontagem do mesmo lado no mesmo dia não vira ponto novo: vale a mais
    recente, como na planilha. A antiga é descartada inteira, itens inclusive.
    """
    # (cliente, dia, lado) → a contagem que vale
    contagens: dict[tuple[UUID, str, str], object] = {}
    for visit in visits:
        dia = local_day(visit.visited_at)
        if not dia:
            # Sem data da visita não há lugar na linha do tempo.
            continue
        chave = (visit.customer_id, dia, visit.visit_type)
        atual = contagens.get(chave)
        if atual is None or _moment(visit) >= _moment(atual):
            contagens[chave] = visit

    valem = {v.id: chave for chave, v in contagens.items()}

    # visit_id → {product_id: (nome, quantidade em unidades)}
    itens: dict[UUID, dict[UUID, tuple[Optional[str], float]]] = {}
    for row in item_rows:
        if row.visit_id not in valem:
            continue
        total = float(row.boxes or 0) * _package_size(row) + float(row.units or 0)
        itens.setdefault(row.visit_id, {})[row.product_id] = (row.product_name, total)

    # Os produtos que cada cliente carrega — o universo sobre o qual a ausência
    # numa contagem é lida como zero. Sai das próprias contagens: produto que
    # nunca foi contado em lugar nenhum não tem história para contar.
    catalogo: dict[UUID, dict[UUID, Optional[str]]] = {}
    nomes_cliente: dict[UUID, Optional[str]] = {}
    for visit in contagens.values():
        nomes_cliente[visit.customer_id] = visit.customer_name
        do_cliente = catalogo.setdefault(visit.customer_id, {})
        for product_id, (nome, _) in itens.get(visit.id, {}).items():
            do_cliente.setdefault(product_id, nome)

    series: dict[tuple[UUID, UUID], Series] = {}
    for (customer_id, dia, lado), visit in contagens.items():
        contados = itens.get(visit.id, {})
        for product_id, nome in catalogo.get(customer_id, {}).items():
            serie = series.setdefault(
                (customer_id, product_id),
                Series(
                    customer_id=customer_id,
                    customer_name=nomes_cliente.get(customer_id),
                    product_id=product_id,
                    product_name=nome,
                ),
            )
            # Ausente numa contagem que aconteceu = zero. Ver o cabeçalho.
            serie.days.setdefault(dia, {})[lado] = contados.get(product_id, (None, 0.0))[1]

    return list(series.values())


# ─── Produtos parados ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stalled:
    """Produto cuja quantidade não se mexeu ao longo de várias contagens."""

    customer_id: UUID
    customer_name: Optional[str]
    product_id: UUID
    product_name: Optional[str]
    quantity: float
    counts: int          # quantas contagens seguidas no mesmo patamar
    days: int            # dias entre a primeira e a última delas
    since: str


def _flat_run(completos: list[tuple[str, float, float, float]], tolerance: float):
    """Quantas contagens, a contar da última para trás, ficaram no mesmo patamar.

    Tolerância proporcional com piso de uma unidade: 12 → 12 → 11 é parado, e num
    produto de 400 unidades uma diferença de 15 também é. Sem o piso, todo
    produto de quantidade pequena precisaria ser idêntico ao milésimo.
    """
    if not completos:
        return []

    nivel = completos[-1][3]
    margem = max(1.0, tolerance * nivel)

    corrida = []
    for ponto in reversed(completos):
        if abs(ponto[3] - nivel) > margem:
            break
        corrida.append(ponto)
    return list(reversed(corrida))


def stalled(
    series: Iterable[Series], min_counts: int = 3, tolerance: float = 0.05
) -> list[Stalled]:
    """Produtos parados, do que está parado há mais tempo para o mais recente.

    Parado é estoque morto na loja: não vendeu e não foi reposto entre contagens
    seguidas. É o indicador mais robusto à contagem irregular — a planura é o
    sinal, e ela não depende de quanto tempo passou entre uma visita e outra.

    Quantidade zerada não entra: zero repetido não é produto encalhado, é
    produto em falta, e quem responde por ele é a lista de sumidos.
    """
    parados = []
    for serie in series:
        corrida = _flat_run(serie.complete_days(), tolerance)
        if len(corrida) < min_counts or corrida[-1][3] <= 0:
            continue

        primeiro, ultimo = corrida[0][0], corrida[-1][0]
        parados.append(
            Stalled(
                customer_id=serie.customer_id,
                customer_name=serie.customer_name,
                product_id=serie.product_id,
                product_name=serie.product_name,
                quantity=corrida[-1][3],
                counts=len(corrida),
                days=(date.fromisoformat(ultimo) - date.fromisoformat(primeiro)).days,
                since=primeiro,
            )
        )

    return sorted(parados, key=lambda p: (-p.days, -p.counts))


# ─── Sumiu e voltou ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Moved:
    """Produto que zerou entre duas contagens, ou que voltou depois de zerado."""

    customer_id: UUID
    customer_name: Optional[str]
    product_id: UUID
    product_name: Optional[str]
    day: str             # a contagem em que a mudança apareceu
    previous_day: str
    previous: float
    current: float
    days: int            # intervalo entre as duas contagens


def moved(series: Iterable[Series]) -> tuple[list[Moved], list[Moved]]:
    """(sumiram, voltaram), comparando as duas últimas contagens completas.

    Comparar o cliente com ele mesmo é mais confiável do que procurar zero
    absoluto: não depende de o promotor ter digitado o zero, e sim de o produto
    ter estado lá antes.
    """
    sumiram, voltaram = [], []

    for serie in series:
        completos = serie.complete_days()
        if len(completos) < 2:
            continue

        (dia_ant, _, _, antes), (dia, _, _, agora) = completos[-2], completos[-1]
        if (antes > 0) == (agora > 0):
            continue

        registro = Moved(
            customer_id=serie.customer_id,
            customer_name=serie.customer_name,
            product_id=serie.product_id,
            product_name=serie.product_name,
            day=dia,
            previous_day=dia_ant,
            previous=antes,
            current=agora,
            days=(date.fromisoformat(dia) - date.fromisoformat(dia_ant)).days,
        )
        (sumiram if antes > 0 else voltaram).append(registro)

    ordem = lambda m: (m.day, (m.customer_name or "").lower())  # noqa: E731
    return sorted(sumiram, key=ordem, reverse=True), sorted(voltaram, key=ordem, reverse=True)


# ─── Gôndola vazia com estoque no depósito ────────────────────────────────────


@dataclass(frozen=True)
class ShelfGap:
    """Prateleira vazia com mercadoria guardada — falha de reposição, não falta."""

    customer_id: UUID
    customer_name: Optional[str]
    product_id: UUID
    product_name: Optional[str]
    day: str
    estoque: float
    # Aconteceu também na contagem anterior. Sem isso, a lista pegaria a loja no
    # instante entre a venda e a reposição; com isso, é problema instalado.
    repeated: bool


def shelf_gap(series: Iterable[Series]) -> list[ShelfGap]:
    """Produtos zerados na gôndola com saldo no estoque, na última contagem.

    É o que a separação entre os dois lugares foi feita para revelar: a
    mercadoria está na loja, atrás, e o cliente na frente não a encontra.
    Repetidos primeiro — esses já não são coincidência de horário.
    """
    faltas = []
    for serie in series:
        completos = serie.complete_days()
        if not completos:
            continue

        _, gondola, estoque, _ = completos[-1]
        if gondola > 0 or estoque <= 0:
            continue

        repetido = len(completos) >= 2 and completos[-2][1] <= 0 < completos[-2][2]
        faltas.append(
            ShelfGap(
                customer_id=serie.customer_id,
                customer_name=serie.customer_name,
                product_id=serie.product_id,
                product_name=serie.product_name,
                day=completos[-1][0],
                estoque=estoque,
                repeated=repetido,
            )
        )

    return sorted(faltas, key=lambda f: (not f.repeated, -f.estoque))


# ─── A série para o gráfico ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Point:
    """Um dia contado. Lado não contado vem como None — e fica sem ponto no
    gráfico, em vez de virar zero."""

    day: str
    gondola: Optional[float]
    estoque: Optional[float]


def history(
    series: Iterable[Series], customer_id: UUID, product_id: Optional[UUID] = None
) -> list[Point]:
    """A evolução de um cliente ao longo do tempo — de um produto, ou de tudo.

    Sem `product_id` soma o cliente inteiro; com ele, isola um produto. Dias sem
    contagem não aparecem: a linha liga um ponto ao outro, e o espaçamento
    irregular entre eles é a informação, não um defeito a corrigir.
    """
    totais: dict[str, dict[str, float]] = {}

    for serie in series:
        if serie.customer_id != customer_id:
            continue
        if product_id and serie.product_id != product_id:
            continue
        for dia, lados in serie.days.items():
            do_dia = totais.setdefault(dia, {})
            for lado, quantidade in lados.items():
                do_dia[lado] = do_dia.get(lado, 0.0) + quantidade

    return [
        Point(day=dia, gondola=totais[dia].get(GONDOLA), estoque=totais[dia].get(ESTOQUE))
        for dia in sorted(totais)
    ]


# ─── Os clientes que têm história ─────────────────────────────────────────────


@dataclass(frozen=True)
class CustomerCounts:
    """Um cliente com contagem na janela, e quanta história ele tem."""

    customer_id: UUID
    customer_name: Optional[str]
    complete_counts: int
    first_day: str
    last_day: str


def customers(series: Iterable[Series]) -> list[CustomerCounts]:
    """Os clientes contados na janela, do que tem mais história para o que tem
    menos. Um cliente com uma contagem só aparece na lista — mas não rende
    comparação nenhuma, e a tela precisa poder dizer isso."""
    dias: dict[UUID, set[str]] = {}
    nomes: dict[UUID, Optional[str]] = {}

    for serie in series:
        nomes[serie.customer_id] = serie.customer_name
        dias.setdefault(serie.customer_id, set()).update(
            dia for dia, _, _, _ in serie.complete_days()
        )

    return sorted(
        (
            CustomerCounts(
                customer_id=customer_id,
                customer_name=nomes.get(customer_id),
                complete_counts=len(datas),
                first_day=min(datas) if datas else "",
                last_day=max(datas) if datas else "",
            )
            for customer_id, datas in dias.items()
        ),
        key=lambda c: (-c.complete_counts, (c.customer_name or "").lower()),
    )
