"""Qual produto precisa ter o vencimento coletado — e por quê.

Este módulo não fala com o banco. Recebe a história de um produto num cliente
(as `Series` do `evolution`) e responde uma pergunta só: **a mercadoria que está
na loja hoje chegou quando?**

POR QUE NÃO SE TENTA MEDIR VENDA
--------------------------------
A tentação é calcular quanto o cliente vendeu e ver se dá tempo de escoar. Mas
este app não conhece pedido nem entrega, e a diferença entre duas contagens é
LÍQUIDA — entrega e venda se escondem uma na outra (ver o cabeçalho do
`evolution`). Perseguir a venda é perseguir um número que os dados não têm.

A pergunta que os dados RESPONDEM é outra, e é a que interessa: das unidades que
estão lá hoje, quantas são as mesmas que já estavam há cinco semanas? Cem
unidades paradas há cinco semanas são cem unidades a cinco semanas do vencimento
— e isso o histórico de contagens diz sem precisar saber de venda nenhuma.

O RAZÃO DE LOTES
----------------
Percorrendo as contagens completas do produto, em ordem:

* estoque SUBIU  → houve entrega: abre um lote com a diferença, datado ali;
* estoque CAIU   → saiu mercadoria: consome dos lotes que vencem primeiro;
* estoque IGUAL  → nada muda, e os lotes envelhecem mais uma semana.

No fim sobra uma fila de lotes, e o primeiro dela — o que vence antes — é o que
manda. O vencimento de um lote estimado é o dia em que ele apareceu mais o
`arrival_shelf_life_days` do produto: com quantos dias para vencer a mercadoria
costuma chegar ao cliente.

É função pura da série: nada é gravado, nada é incremental. Corrigir uma
contagem antiga reescreve o razão inteiro certo, sozinho.

A COLETA MANDA MAIS QUE A ESTIMATIVA
------------------------------------
No dia em que o promotor digita as datas, a fila inteira é substituída pelo que
ele leu na embalagem. A estimativa existe para provocar a PRIMEIRA coleta; dali
em diante o razão anda em cima de data real, e o erro para de se acumular.

O QUE ESTES NÚMEROS NÃO SÃO
---------------------------
Estimativa, e não medição — três limites que valem repetir:

* Entrega escondida (vendeu 20 e chegou 20 entre duas contagens) mantém a DATA
  do lote velho certa, mas superestima o TAMANHO dele. Erra para o lado de pedir
  coleta demais, e a coleta corrige.
* A fila supõe que a loja vende o mais velho primeiro. É o que o promotor
  organiza estando lá, mas é suposição.
* A data de chegada tem a precisão da visita: com visita semanal, ±7 dias. É por
  isso que as janelas aqui são largas, e não de dois ou três dias.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Sequence
from uuid import UUID

from app.merchandising.evolution import Series

# Diferença de quantidade abaixo disto é ruído de arredondamento (as quantidades
# são Numeric(15,3) virando float), não entrega nem venda.
EPS = 0.001

# Abaixo disto não há velocidade em que acreditar: duas contagens dão um
# intervalo só, e um intervalo não é uma tendência. Com menos que isso, só o
# vencimento em si dispara a coleta — nunca o "não vai dar tempo de vender".
MIN_COUNTS_FOR_VELOCITY = 3


def alert_window(arrival_days: int) -> int:
    """Faltando isto para vencer, coleta e ponto — sem olhar giro.

    Um terço da vida que o produto tem ao chegar, com piso de uma semana: 13 dias
    para uma bebida que chega com 40, 7 para um produto que chega com 15. Fixar
    um número só serviria mal aos dois extremos.
    """
    return max(7, arrival_days // 3)


def alert_horizon(arrival_days: int) -> int:
    """Até quando faz sentido avisar que "não vai dar tempo de vender".

    Sem este teto, um produto de giro lento entraria na coleta desde a primeira
    semana e ficaria lá para sempre — e o promotor passaria a visita inteira
    digitando datas de mercadoria que ainda tem mês e meio de vida. Metade da
    vida na chegada é onde ainda dá para reagir (degustação, promoção) e já dá
    para ter certeza de que a curva de venda não vai salvar sozinha.
    """
    return max(alert_window(arrival_days), arrival_days // 2)


# ─── A fila de lotes ──────────────────────────────────────────────────────────


@dataclass
class Lot:
    """Uma porção do estoque atual com a mesma data de vencimento."""

    expires_on: date
    quantity: float
    # True = o promotor leu na embalagem. False = estimado pela data de chegada.
    collected: bool


def _consume(lots: list[Lot], amount: float) -> None:
    """Tira `amount` unidades da fila, começando pelas que vencem primeiro."""
    while amount > EPS and lots:
        if lots[0].quantity <= amount + EPS:
            amount -= lots[0].quantity
            lots.pop(0)
        else:
            lots[0].quantity -= amount
            return


def _reconcile(lots: list[Lot], total: float, day: date, arrival_days: int) -> None:
    """Acerta a fila coletada com o total contado naquele mesmo dia.

    A tela só deixa enviar quando a soma das datas fecha com a contagem, então na
    prática os dois números batem. Mas a contagem pode ser CORRIGIDA depois da
    coleta — e aí a fila ficaria descrevendo um estoque que não existe mais.
    Sobra vira lote sem data lida; falta sai pela frente da fila.
    """
    coletado = sum(lot.quantity for lot in lots)
    if coletado < total - EPS:
        lots.append(Lot(day + timedelta(days=arrival_days), total - coletado, False))
    elif coletado > total + EPS:
        _consume(lots, coletado - total)


def ledger(
    serie: Series,
    arrival_days: int,
    collections: Optional[dict[str, Sequence[tuple[date, float]]]] = None,
) -> list[Lot]:
    """A história do produto → os lotes que ainda estão na loja, o mais velho
    primeiro.

    `collections` são as datas já coletadas, por dia (`'2026-09-11'`). No dia de
    uma coleta a fila inteira é trocada por ela: data lida vale mais que data
    calculada.
    """
    collections = collections or {}
    lots: list[Lot] = []
    anterior: Optional[float] = None

    for dia, _, _, total in serie.complete_days():
        hoje = date.fromisoformat(dia)
        coleta = collections.get(dia)

        if coleta:
            lots = [Lot(quando, float(quanto), True) for quando, quanto in coleta]
            lots.sort(key=lambda lot: lot.expires_on)
            _reconcile(lots, total, hoje, arrival_days)
        elif anterior is None:
            # Primeira contagem: tudo que está lá é um lote só, datado aqui. O
            # estoque pode já estar velho, e então esta data o rejuvenesce — o
            # erro é para o lado de alertar de menos, e some em algumas semanas.
            if total > EPS:
                lots = [Lot(hoje + timedelta(days=arrival_days), total, False)]
        else:
            delta = total - anterior
            if delta > EPS:
                lots.append(Lot(hoje + timedelta(days=arrival_days), delta, False))
            elif delta < -EPS:
                _consume(lots, -delta)

        anterior = total
        lots.sort(key=lambda lot: lot.expires_on)

    return lots


def velocity(serie: Series) -> float:
    """Unidades que saem por dia — o piso, nunca a venda.

    Soma só as quedas entre contagens e divide pelos dias observados. Entrega que
    entrou no meio do intervalo não aparece, então o número é sempre menor ou
    igual à venda real — e um giro subestimado alerta mais, que é o lado seguro.
    """
    completos = serie.complete_days()
    if len(completos) < 2:
        return 0.0

    saiu = sum(
        max(0.0, anterior[3] - atual[3])
        for anterior, atual in zip(completos, completos[1:])
    )
    dias = (date.fromisoformat(completos[-1][0]) - date.fromisoformat(completos[0][0])).days
    return saiu / dias if dias > 0 else 0.0


# ─── O veredito ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Forecast:
    """O lote mais velho de um produto num cliente, e se ele pede coleta."""

    customer_id: UUID
    product_id: UUID
    expires_on: date
    quantity: float      # saldo do lote mais velho, em unidades
    days_left: int       # dias até vencer (negativo = já venceu)
    # None = o produto não girou nada na janela observada
    days_to_sell: Optional[float]
    collected: bool      # a data veio da embalagem, não de conta
    alert: bool          # o promotor tem de coletar o vencimento
    reason: str          # 'vence', 'nao_escoa' ou '' (sem alerta)


def forecast(
    serie: Series,
    arrival_days: int,
    today: date,
    collections: Optional[dict[str, Sequence[tuple[date, float]]]] = None,
) -> Optional[Forecast]:
    """O lote mais velho deste produto neste cliente, com o veredito.

    Devolve `None` quando não há o que dizer: produto sem histórico completo, ou
    sem saldo nenhum na loja.

    ALERTA quando o lote mais velho ainda tem saldo e:

    * **vence**    — falta menos que a janela de aviso. Vale sempre, com uma
      contagem que seja: depende só da data, não de giro.
    * **nao_escoa** — já está na segunda metade da vida E, no ritmo observado,
      não dá tempo de vender o lote antes de ele vencer. Precisa de pelo menos
      três contagens completas, senão é chute com cara de conta.

    Produto que não girou nada cai sempre em `nao_escoa` ao entrar no horizonte —
    e está certo: estoque parado não vai embora sozinho, vence.
    """
    lots = ledger(serie, arrival_days, collections)
    if not lots or lots[0].quantity <= EPS:
        return None

    velho = lots[0]
    faltam = (velho.expires_on - today).days

    giro = velocity(serie)
    escoar = velho.quantity / giro if giro > EPS else None
    tem_historico = len(serie.complete_days()) >= MIN_COUNTS_FOR_VELOCITY

    razao = ""
    if faltam <= alert_window(arrival_days):
        razao = "vence"
    elif (
        tem_historico
        and faltam <= alert_horizon(arrival_days)
        and (escoar is None or escoar > faltam)
    ):
        razao = "nao_escoa"

    return Forecast(
        customer_id=serie.customer_id,
        product_id=serie.product_id,
        expires_on=velho.expires_on,
        quantity=velho.quantity,
        days_left=faltam,
        days_to_sell=escoar,
        collected=velho.collected,
        alert=bool(razao),
        reason=razao,
    )


def forecasts(
    series: Iterable[Series],
    arrival_days: dict[UUID, Optional[int]],
    today: date,
    collections: Optional[dict[tuple[UUID, UUID], dict[str, Sequence[tuple[date, float]]]]] = None,
) -> dict[tuple[UUID, UUID], Forecast]:
    """O veredito de cada (cliente, produto) que tem um a dar.

    Produto sem `arrival_shelf_life_days` cadastrado fica de fora inteiro: sem
    saber com quanta vida a mercadoria chega, não há data que se possa estimar, e
    inventar uma seria pior que ficar calado.
    """
    collections = collections or {}
    saida = {}

    for serie in series:
        dias = arrival_days.get(serie.product_id)
        if not dias or dias <= 0:
            continue

        chave = (serie.customer_id, serie.product_id)
        veredito = forecast(serie, dias, today, collections.get(chave))
        if veredito:
            saida[chave] = veredito

    return saida
