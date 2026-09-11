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
Percorrendo as contagens completas do produto, em ordem, e em cada intervalo:

1. **o que entrou** — as notas emitidas para aquele cliente no intervalo abrem
   um lote cada, datado pela emissão;
2. **o que foi para o lixo** — o vencido que o promotor retirou sai do lote
   correspondente, e NÃO conta como venda;
3. **a conferência** — o que a contagem achou a menos do que o razão esperava
   saiu pela porta da frente (consome dos lotes que vencem primeiro); o que ela
   achou a mais é entrada que a planilha não cobriu, e vira um lote datado ali.

Repare no que a ordem faz: a contagem deixa de ser a FONTE dos lotes e passa a
ser a CONFERÊNCIA deles. E quando não há nota nenhuma no intervalo — planilha
ainda não anexada, período antigo — o passo 3 sozinho reproduz exatamente o
comportamento antigo (subiu vira lote, caiu consome). O razão degrada para a
estimativa pura sem nenhum código de exceção.

O vencimento de um lote estimado é a data em que ele entrou mais o
`arrival_shelf_life_days` do produto: com quantos dias para vencer a mercadoria
costuma chegar ao cliente.

É função pura das entradas: nada é gravado, nada é incremental. Corrigir uma
contagem antiga reescreve o razão inteiro certo, sozinho.

POR QUE O VENCIDO RETIRADO NÃO É DETALHE
----------------------------------------
Sem registrar o que o promotor tira da gôndola, mercadoria que foi para o lixo é
lida como venda: o estoque caiu e não há como saber por quê. O efeito é perverso
e trabalha contra esta função inteira — a loja parece girar mais rápido, "dias
para escoar" encolhe, e o alerta de "não vai dar tempo de vender" deixa de
disparar justamente no produto que está vencendo. Quanto mais vencia, menos o
sistema avisava.

A COLETA MANDA MAIS QUE A ESTIMATIVA
------------------------------------
No dia em que o promotor digita as datas, a fila inteira é substituída pelo que
ele leu na embalagem. A estimativa existe para provocar a PRIMEIRA coleta; dali
em diante o razão anda em cima de data real, e o erro para de se acumular.

O QUE ESTES NÚMEROS NÃO SÃO
---------------------------
Estimativa, e não medição — três limites que valem repetir:

* A fila supõe que a loja vende o mais velho primeiro. É o que o promotor
  organiza estando lá, mas é suposição — e é a única das fraquezas originais que
  nem a planilha nem a retirada resolvem.
* A data da nota é a da EMISSÃO, não a da entrega (a planilha traz a de entrega
  vazia na maior parte das linhas). O caminhão leva um ou dois dias, então a
  mercadoria aparece no razão um pouco antes de existir na loja. Numa contagem
  semanal isso cabe no ruído; e some sozinho na contagem seguinte.
* Sem nota no intervalo, valem as três ressalvas antigas: entrega escondida
  superestima o tamanho do lote velho (erra para o lado de pedir coleta demais),
  e a data de chegada tem a precisão da visita — com visita semanal, ±7 dias. É
  por isso que as janelas aqui são largas, e não de dois ou três dias.
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


def _take(lots: list[Lot], expires_on: date, amount: float) -> None:
    """Tira unidades do lote que vence NAQUELA data — o vencido que o promotor
    retirou e leu na embalagem.

    Se não houver lote com essa data, a estimativa errou em algum ponto do
    passado; a mercadoria saiu do mesmo jeito, então sai pela frente da fila. É
    a leitura menos errada disponível: o que foi retirado por vencimento era,
    por definição, o mais velho que havia.
    """
    for lot in lots:
        if lot.expires_on == expires_on:
            tirado = min(lot.quantity, amount)
            lot.quantity -= tirado
            amount -= tirado
            break
    lots[:] = [lot for lot in lots if lot.quantity > EPS]
    if amount > EPS:
        _consume(lots, amount)


@dataclass
class Ledger:
    """O estado do produto naquele cliente no fim da história."""

    lots: list[Lot]
    # Unidades que saíram pela porta da frente na janela observada. Não é a
    # venda medida — é o que sobra depois de descontar entradas e retiradas de
    # tudo que mudou entre as contagens.
    sold: float
    days: int          # dias entre a primeira e a última contagem completa
    counts: int        # quantas contagens completas entraram na conta

    @property
    def velocity(self) -> float:
        """Unidades por dia. Zero quando não há intervalo em que acreditar."""
        return self.sold / self.days if self.days > 0 else 0.0


def ledger(
    serie: Series,
    arrival_days: int,
    collections: Optional[dict[str, Sequence[tuple[date, float]]]] = None,
    deliveries: Optional[Sequence[tuple[date, float]]] = None,
    removals: Optional[Sequence[tuple[date, date, float]]] = None,
) -> Ledger:
    """A história do produto → os lotes que ainda estão na loja, o mais velho
    primeiro, e quanto saiu pela frente no caminho.

    `deliveries` são `(emissão, quantidade)`; `removals`, `(dia da retirada,
    data que estava na embalagem, quantidade)`; `collections`, as datas já
    coletadas, indexadas pelo dia (`'2026-09-11'`).

    No dia de uma coleta a fila inteira é trocada por ela: data lida vale mais
    que data calculada, e o razão volta a andar em cima de verdade de campo.
    """
    collections = collections or {}
    entradas = sorted(deliveries or [])
    retiradas = sorted(removals or [])

    lots: list[Lot] = []
    vendido = 0.0
    completos = serie.complete_days()
    anterior: Optional[date] = None

    for dia, _, _, total in completos:
        hoje = date.fromisoformat(dia)

        # ── 1. o que entrou desde a contagem anterior ─────────────────────
        # Na primeira contagem o intervalo é aberto para trás: nota antiga vira
        # lote velho, e a conferência do passo 3 desconta o que já tinha sido
        # vendido antes de existir contagem.
        for emitida, quanto in entradas:
            if (anterior is None or emitida > anterior) and emitida <= hoje:
                lots.append(Lot(emitida + timedelta(days=arrival_days), quanto, False))

        # ── 2. o que o promotor retirou por vencimento ────────────────────
        # Sai do razão SEM entrar em `vendido`: foi para o lixo, não para o caixa.
        for retirado_em, vencia_em, quanto in retiradas:
            if (anterior is None or retirado_em > anterior) and retirado_em <= hoje:
                _take(lots, vencia_em, quanto)

        lots.sort(key=lambda lot: lot.expires_on)

        # ── 3. a conferência contra o que o promotor achou ────────────────
        coleta = collections.get(dia)
        if coleta:
            lots = [Lot(quando, float(quanto), True) for quando, quanto in coleta]
            lots.sort(key=lambda lot: lot.expires_on)
            _reconcile(lots, total, hoje, arrival_days)
        else:
            esperado = sum(lot.quantity for lot in lots)
            if total < esperado - EPS:
                # Saiu mais do que as entradas e retiradas explicam: venda.
                saiu = esperado - total
                _consume(lots, saiu)
                if anterior is not None:
                    vendido += saiu
            elif total > esperado + EPS:
                # Achou mais do que o razão previa: entrada que a planilha não
                # cobriu. Datada aqui, que é o mais novo que ela poderia ser.
                lots.append(Lot(hoje + timedelta(days=arrival_days), total - esperado, False))

        lots.sort(key=lambda lot: lot.expires_on)
        anterior = hoje

    dias = 0
    if len(completos) >= 2:
        dias = (
            date.fromisoformat(completos[-1][0]) - date.fromisoformat(completos[0][0])
        ).days

    return Ledger(lots=lots, sold=vendido, days=dias, counts=len(completos))


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
    deliveries: Optional[Sequence[tuple[date, float]]] = None,
    removals: Optional[Sequence[tuple[date, date, float]]] = None,
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
    razao = ledger(serie, arrival_days, collections, deliveries, removals)
    if not razao.lots or razao.lots[0].quantity <= EPS:
        return None

    velho = razao.lots[0]
    faltam = (velho.expires_on - today).days

    giro = razao.velocity
    escoar = velho.quantity / giro if giro > EPS else None

    motivo = ""
    if faltam <= alert_window(arrival_days):
        motivo = "vence"
    elif (
        razao.counts >= MIN_COUNTS_FOR_VELOCITY
        and faltam <= alert_horizon(arrival_days)
        and (escoar is None or escoar > faltam)
    ):
        motivo = "nao_escoa"

    return Forecast(
        customer_id=serie.customer_id,
        product_id=serie.product_id,
        expires_on=velho.expires_on,
        quantity=velho.quantity,
        days_left=faltam,
        days_to_sell=escoar,
        collected=velho.collected,
        alert=bool(motivo),
        reason=motivo,
    )


def forecasts(
    series: Iterable[Series],
    arrival_days: dict[UUID, Optional[int]],
    today: date,
    collections: Optional[dict[tuple[UUID, UUID], dict[str, Sequence[tuple[date, float]]]]] = None,
    deliveries: Optional[dict[tuple[UUID, UUID], Sequence[tuple[date, float]]]] = None,
    removals: Optional[dict[tuple[UUID, UUID], Sequence[tuple[date, date, float]]]] = None,
) -> dict[tuple[UUID, UUID], Forecast]:
    """O veredito de cada (cliente, produto) que tem um a dar.

    As três fontes extras vêm indexadas por `(cliente, produto)` — a mesma chave
    da série. Produto sem `arrival_shelf_life_days` cadastrado fica de fora
    inteiro: sem saber com quanta vida a mercadoria chega, não há data que se
    possa estimar, e inventar uma seria pior que ficar calado.
    """
    collections, deliveries, removals = collections or {}, deliveries or {}, removals or {}
    saida = {}

    for serie in series:
        dias = arrival_days.get(serie.product_id)
        if not dias or dias <= 0:
            continue

        chave = (serie.customer_id, serie.product_id)
        veredito = forecast(
            serie, dias, today,
            collections.get(chave), deliveries.get(chave), removals.get(chave),
        )
        if veredito:
            saida[chave] = veredito

    return saida
