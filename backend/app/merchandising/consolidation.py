"""O par gôndola + estoque, e a linha consolidada que ele vira na planilha.

O promotor continua contando os dois lugares separadamente — são duas visitas,
duas telas, dois botões no card do cliente. O administrador, porém, não recebe
duas planilhas: recebe uma linha por produto com o que havia na gôndola e o que
havia no estoque. Juntar as duas pontas é o serviço deste módulo.

Uma contagem só entra na planilha quando o par dela chegou: MESMO CLIENTE, MESMO
PROMOTOR, MESMO DIA. Contagem sozinha fica de fora e aparece como "aguardando"
na tela do administrador — meia contagem viraria uma planilha com metade dos
números e nada avisando que a outra metade não existe.

O "mesmo dia" é o dia de quem lê a planilha (`TIMEZONE`), não o do servidor: a
contagem das 22h em São Paulo é gravada como 01h do dia seguinte em UTC, e
pareá-la pelo dia UTC separaria justamente as duas contagens da mesma visita.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.infrastructure.persistence.models.stock_visit import VisitType

logger = logging.getLogger(__name__)

GONDOLA = VisitType.GONDOLA.value
ESTOQUE = VisitType.ESTOQUE.value
SIDES = (GONDOLA, ESTOQUE)

SIDE_LABEL = {GONDOLA: "gôndola", ESTOQUE: "estoque"}


# ─── Dia local ────────────────────────────────────────────────────────────────


def local_zone() -> ZoneInfo:
    """Fuso configurado, com UTC como último recurso.

    Um `TIMEZONE` escrito errado no `.env` não pode derrubar a exportação — a
    planilha sai em UTC e o aviso fica no log.
    """
    try:
        return ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            "TIMEZONE inválido (%r) — a planilha sairá em UTC", settings.timezone
        )
        return ZoneInfo("UTC")


def as_utc(moment: datetime) -> datetime:
    """Instante gravado → instante com fuso. Linha vinda do SQLite volta ingênua;
    assume-se UTC, que é como foi gravada."""
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def local_day(moment: Optional[datetime]) -> str:
    """Instante gravado → 'AAAA-MM-DD' no fuso de quem lê. É a chave do par."""
    if not moment:
        return ""
    return as_utc(moment).astimezone(local_zone()).strftime("%Y-%m-%d")


def day_window(day: str) -> tuple[datetime, datetime]:
    """'AAAA-MM-DD' local → os dois instantes UTC que delimitam esse dia.

    O banco guarda UTC, então buscar "as contagens do dia 19" é buscar de 03h do
    dia 19 até 03h do dia 20 (no horário de Brasília).
    """
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=local_zone())
    return as_utc(start).astimezone(timezone.utc), (
        start + timedelta(days=1)
    ).astimezone(timezone.utc)


def day_bounds(
    date_from: Optional[datetime], date_to: Optional[datetime]
) -> tuple[Optional[str], Optional[str]]:
    """Filtro de data do administrador → primeiro e último dia local.

    A tela manda '2026-08-19' (um `<input type="date">`), que chega aqui como
    meia-noite sem fuso: isso é um DIA, não um instante, e é lido como o dia
    local que o administrador escolheu. Comparar dias, e não instantes, é o que
    faz "até 19/08" incluir a contagem das 21h do dia 19.
    """
    def dia(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.strftime("%Y-%m-%d") if value.tzinfo is None else local_day(value)

    return dia(date_from), dia(date_to)


def within_days(pair: "Pair", first: Optional[str], last: Optional[str]) -> bool:
    """O par caiu no período pedido? Datas em 'AAAA-MM-DD' comparam como texto."""
    if first and pair.day < first:
        return False
    if last and pair.day > last:
        return False
    return True


# ─── Agrupamento ──────────────────────────────────────────────────────────────

# Chave do par: quem foi contado, por quem, em que dia.
GroupKey = tuple[UUID, UUID, str]


def group_key(visit) -> GroupKey:
    return (visit.customer_id, visit.promoter_id, local_day(visit.visited_at))


def _moment(visit) -> datetime:
    """Quando esta contagem foi fechada — usado para escolher entre duas
    contagens do mesmo lado no mesmo dia."""
    marca = visit.submitted_at or visit.visited_at or visit.created_at
    return as_utc(marca) if marca else datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class Pair:
    """As duas contagens de um cliente num dia, do jeito que a planilha precisa."""

    key: GroupKey
    # {'gondola': visita, 'estoque': visita} — só a mais recente de cada lado
    sides: dict[str, object] = field(default_factory=dict)
    # Todas as visitas do grupo, inclusive as substituídas por uma recontagem:
    # a exportação fecha todas, senão a antiga ficaria pendente para sempre.
    visit_ids: list[UUID] = field(default_factory=list)

    @property
    def day(self) -> str:
        """O dia local em que as duas contagens foram feitas."""
        return self.key[2]

    @property
    def complete(self) -> bool:
        return all(side in self.sides for side in SIDES)

    @property
    def missing(self) -> Optional[str]:
        """O lado que falta para fechar o par, ou None se já fechou."""
        faltando = [side for side in SIDES if side not in self.sides]
        return faltando[0] if len(faltando) == 1 else None

    @property
    def moment(self) -> Optional[datetime]:
        """A primeira das duas contagens do dia — é a data que vai na planilha."""
        datas = [
            as_utc(v.visited_at) for v in self.sides.values() if v.visited_at
        ]
        return min(datas) if datas else None

    def side(self, side: str):
        return self.sides.get(side)


def group_visits(visits: Iterable) -> dict[GroupKey, Pair]:
    """Visitas soltas → pares por cliente/promotor/dia.

    Recontagem do mesmo lado no mesmo dia (o promotor refez porque errou) não
    duplica o par: vale a mais recente, e a antiga entra só em `visit_ids`.
    """
    pares: dict[GroupKey, Pair] = {}

    for visit in visits:
        key = group_key(visit)
        par = pares.setdefault(key, Pair(key=key))
        par.visit_ids.append(visit.id)

        atual = par.sides.get(visit.visit_type)
        if atual is None or _moment(visit) >= _moment(atual):
            par.sides[visit.visit_type] = visit

    return pares


def missing_side_by_visit(visits: Iterable) -> dict[UUID, Optional[str]]:
    """{visit_id: lado que falta para o par fechar, ou None}.

    É o que a lista do administrador mostra como "aguardando estoque": a
    contagem chegou, mas sozinha ela não vira planilha.
    """
    pares = group_visits(visits)
    return {
        visit_id: par.missing
        for par in pares.values()
        for visit_id in par.visit_ids
    }


# ─── Linhas da planilha ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConsolidatedRow:
    """Uma linha da planilha: um produto, nos dois lugares, num dia.

    `gondola`/`estoque` em None querem dizer coisas diferentes conforme o
    `_vazio` do lado: produto não contado naquele lado (célula em branco) ou
    lado inteiro declarado sem produtos (célula com "sem produtos").
    """

    visited_at: Optional[datetime]
    customer_name: str
    promoter_name: str
    product_name: str
    gondola: Optional[float]
    estoque: Optional[float]
    gondola_vazia: bool
    estoque_vazio: bool

    @property
    def total(self) -> float:
        return (self.gondola or 0.0) + (self.estoque or 0.0)


def _package_size(row) -> float:
    """Unidades por caixa do produto. Nulo ou zero vira 1 — produto sem caixa
    cadastrada é contado como se a caixa fosse a própria unidade."""
    return float(row.package_size) if row.package_size else 1.0


def product_totals(item_rows: Sequence) -> dict[UUID, dict[UUID, tuple[str, float]]]:
    """Itens achatados → {visit_id: {product_id: (nome, total em unidades)}}.

    O total é recalculado com o `package_size` de hoje, e não lido do que foi
    gravado na contagem: se o cadastro do produto for corrigido, a planilha
    seguinte já sai certa — inclusive para contagens antigas.
    """
    totais: dict[UUID, dict[UUID, tuple[str, float]]] = {}
    for row in item_rows:
        total = float(row.boxes or 0) * _package_size(row) + float(row.units or 0)
        totais.setdefault(row.visit_id, {})[row.product_id] = (
            row.product_name or "", total,
        )
    return totais


def build_rows(
    pairs: Iterable[Pair], item_rows: Sequence
) -> tuple[list[ConsolidatedRow], list[UUID]]:
    """Pares completos → linhas da planilha + as visitas que entraram nela.

    Pares incompletos são descartados aqui: é o único lugar que decide o que o
    administrador leva, e ele não leva meia contagem.
    """
    totais = product_totals(item_rows)
    completos = sorted(
        (par for par in pairs if par.complete),
        key=lambda par: (par.moment or datetime.min.replace(tzinfo=timezone.utc),
                         (par.side(GONDOLA).customer_name or "").lower()),
    )

    linhas: list[ConsolidatedRow] = []
    exportadas: list[UUID] = []

    for par in completos:
        exportadas.extend(par.visit_ids)

        gondola, estoque = par.side(GONDOLA), par.side(ESTOQUE)
        itens_g = totais.get(gondola.id, {})
        itens_e = totais.get(estoque.id, {})

        nomes = {pid: nome for pid, (nome, _) in {**itens_g, **itens_e}.items()}
        produtos = sorted(nomes, key=lambda pid: nomes[pid].lower())

        comum = dict(
            visited_at=par.moment,
            customer_name=gondola.customer_name or "",
            promoter_name=gondola.promoter_name or "",
            gondola_vazia=bool(gondola.no_products),
            estoque_vazio=bool(estoque.no_products),
        )

        if not produtos:
            # Os dois lados declarados sem produtos: a visita aconteceu e não
            # havia nada. Uma linha sem produto registra isso — sem ela, o par
            # sairia da planilha como se ninguém tivesse passado na loja.
            linhas.append(
                ConsolidatedRow(product_name="—", gondola=None, estoque=None, **comum)
            )
            continue

        linhas.extend(
            ConsolidatedRow(
                product_name=nomes[pid],
                gondola=itens_g[pid][1] if pid in itens_g else None,
                estoque=itens_e[pid][1] if pid in itens_e else None,
                **comum,
            )
            for pid in produtos
        )

    return linhas, exportadas
