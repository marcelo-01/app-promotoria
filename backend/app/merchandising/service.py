from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.service import CustomersService
from app.infrastructure.persistence.models.product_expiry import ProductExpiry
from app.infrastructure.persistence.models.stock_visit import (
    StockVisit, StockVisitItem, StockVisitStatus, UnitType, VisitType,
)
from app.infrastructure.persistence.models.user import User, UserRole
from app.merchandising import consolidation, evolution, expiry
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    CountProductResponse, CountSheetResponse, MovedProductResponse,
    ProductExpiryInput, ProductExpiryResponse, PromoterCustomerResponse,
    ShelfGapResponse, StalledProductResponse,
    StockCustomerResponse, StockHistoryResponse, StockInsightsResponse,
    StockPointResponse, StockVisitCreate, StockVisitItemInput, StockVisitItemResponse,
    StockVisitResponse, StockVisitUpdate, VisitPairResponse, VisitPairSideResponse,
)

# Quanto passado o razão de lotes enxerga ao decidir a coleta de vencimento.
# Precisa cobrir com folga a vida de um perecível no cliente: com menos, o lote
# que chegou há três meses some da história e o produto parece novo.
EXPIRY_WINDOW_DAYS = 180


def _is_admin(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.SUPERVISOR)


def _side_response(visit) -> VisitPairSideResponse:
    return VisitPairSideResponse(
        visit_id=visit.id,
        status=visit.status,
        no_products=bool(visit.no_products),
        items_count=visit.items_count,
        visited_at=visit.visited_at,
    )


def _pair_response(par: consolidation.Pair) -> VisitPairResponse:
    """Par → a linha única da tela do administrador."""
    gondola = par.side(consolidation.GONDOLA)
    estoque = par.side(consolidation.ESTOQUE)
    # Cliente e promotor são os mesmos nos dois lados (é o que define o par),
    # então qualquer lado presente serve para nomear a linha.
    qualquer = gondola or estoque
    customer_id, promoter_id, dia = par.key

    return VisitPairResponse(
        id=f"{customer_id}|{promoter_id}|{dia}",
        customer_id=customer_id,
        customer_name=qualquer.customer_name,
        promoter_id=promoter_id,
        promoter_name=qualquer.promoter_name,
        day=dia,
        visited_at=par.moment,
        gondola=_side_response(gondola) if gondola else None,
        estoque=_side_response(estoque) if estoque else None,
        missing_side=par.missing,
        status=par.status,
    )


class MerchandisingService:

    # ── Promotor: clientes ────────────────────────────────────────────────

    @staticmethod
    async def list_my_customers(
        session: AsyncSession, tenant_id: UUID, user: User, search: Optional[str] = None
    ) -> list[PromoterCustomerResponse]:
        # Admin enxerga todos; promotor só os seus
        scope_user_id = None if _is_admin(user) else user.id
        customers = await Repo.list_customers_for_promoter(
            session, tenant_id, scope_user_id, search
        )
        last_visits = await Repo.last_visit_by_customer_and_type(session, tenant_id)

        return [
            PromoterCustomerResponse(
                id=customer.id,
                name=customer.name,
                last_gondola_at=last_visits.get((customer.id, VisitType.GONDOLA.value)),
                last_estoque_at=last_visits.get((customer.id, VisitType.ESTOQUE.value)),
            )
            for customer in customers
        ]

    # ── Promotor: folha de contagem ───────────────────────────────────────

    @staticmethod
    async def count_sheet(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
        visit_type: str,
    ) -> CountSheetResponse:
        """Cliente + produtos + contagem anterior: tudo numa resposta só."""
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, customer_id
        )

        customer = await CustomersService.get(session, tenant_id, customer_id)
        last = await Repo.last_quantities_for_customer(
            session, tenant_id, customer_id, visit_type
        )

        mix = await Repo.list_mix_products(session, tenant_id, customer_id)
        if mix:
            products = [(p, position) for p, position in mix]
        else:
            # Sem mix cadastrado: cai no catálogo completo
            products = [(p, 0) for p in await Repo.list_all_products(session, tenant_id)]

        avisos = await MerchandisingService._expiry_forecasts(
            session, tenant_id, customer_id, [p for p, _ in products]
        )

        vazio = (None, None, None)
        return CountSheetResponse(
            customer_id=customer.id,
            customer_name=customer.name,
            visit_type=visit_type,
            products=[
                CountProductResponse(
                    id=p.id,
                    name=p.name,
                    image_url=p.image_url,
                    position=position,
                    package_size=p.package_size or Decimal(1),
                    last_boxes=last.get(p.id, vazio)[0],
                    last_units=last.get(p.id, vazio)[1],
                    last_quantity=last.get(p.id, vazio)[2],
                    collect_expiry=p.id in avisos,
                    expiry_forecast=avisos[p.id].expires_on if p.id in avisos else None,
                    expiry_quantity=(
                        Decimal(str(round(avisos[p.id].quantity, 3)))
                        if p.id in avisos else None
                    ),
                    expiry_reason=avisos[p.id].reason if p.id in avisos else None,
                )
                for p, position in products
            ],
        )

    @staticmethod
    async def _expiry_forecasts(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, products: list,
    ) -> dict[UUID, expiry.Forecast]:
        """Quais produtos deste cliente pedem coleta de vencimento hoje.

        Roda no SERVIDOR, ao abrir a folha — que é o único momento em que o
        promotor está garantidamente com sinal (a tela de contagem já não abre
        sem ele). O aparelho recebe a resposta pronta e, na hora de fechar a
        contagem, só precisa comparar com o que acabou de contar: nada de rede
        no meio do bloqueio.

        Um produto entrar aqui não significa coletar. Significa que HÁ mercadoria
        velha nesta loja — se a contagem de hoje der zero neste produto, ela foi
        embora e não há data nenhuma para ler.
        """
        chegada = {
            p.id: p.arrival_shelf_life_days
            for p in products
            if p.arrival_shelf_life_days
        }
        # Sem nenhum produto com validade de chegada cadastrada não há o que
        # calcular — e nem por que ir ao banco buscar a história inteira.
        if not chegada:
            return {}

        series, _, hoje = await MerchandisingService._stock_series(
            session, tenant_id, EXPIRY_WINDOW_DAYS, customer_id
        )
        coletadas = await Repo.list_expiries_for_customer(
            session, tenant_id, customer_id,
            date.fromisoformat(hoje) - timedelta(days=EXPIRY_WINDOW_DAYS),
        )

        avisos = expiry.forecasts(
            series, chegada, date.fromisoformat(hoje),
            {
                chave: {
                    dia: [(quando, float(quanto)) for quando, quanto in linhas]
                    for dia, linhas in por_dia.items()
                }
                for chave, por_dia in coletadas.items()
            },
        )
        return {
            product_id: veredito
            for (_, product_id), veredito in avisos.items()
            if veredito.alert
        }

    @staticmethod
    async def visit_sheet(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID
    ) -> CountSheetResponse:
        """Folha de correção de um envio: os mesmos painéis da contagem, mas só
        com os produtos que o promotor de fato contou, já preenchidos com o que
        ele digitou. Quem errou um número volta para corrigir aquele número, não
        para refazer a contagem inteira.
        """
        visit, customer_name = await MerchandisingService._load_editable_visit(
            session, tenant_id, user, visit_id
        )

        # Mesma ordem da tela de contagem: o promotor reencontra os produtos na
        # sequência em que os contou.
        mix = await Repo.list_mix_product_ids(session, tenant_id, visit.customer_id)
        position_of = {product_id: index for index, product_id in enumerate(mix)}

        rows = sorted(
            # Produto apagado do catálogo não tem painel para desenhar
            ((item, p) for item, p in await Repo.list_items(session, visit.id) if p),
            key=lambda row: (position_of.get(row[1].id, len(mix)), row[1].name),
        )

        return CountSheetResponse(
            customer_id=visit.customer_id,
            customer_name=customer_name or "",
            visit_type=visit.visit_type,
            visit_id=visit.id,
            status=visit.status,
            no_products=visit.no_products,
            products=[
                CountProductResponse(
                    id=product.id,
                    name=product.name,
                    image_url=product.image_url,
                    position=position_of.get(product.id, 0),
                    package_size=product.package_size or Decimal(1),
                    boxes=item.boxes,
                    units=item.units,
                )
                for item, product in rows
            ],
        )

    # ── Promotor: gravar contagem ─────────────────────────────────────────

    @staticmethod
    async def upsert_visit(
        session: AsyncSession, tenant_id: UUID, user: User, payload: StockVisitCreate
    ) -> StockVisitResponse:
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, payload.customer_id
        )
        if payload.submit:
            MerchandisingService._assert_not_empty(payload.no_products, payload.items)

        visit = None
        if payload.client_uuid:
            # Idempotência: reenvio da mesma contagem atualiza em vez de duplicar
            visit = await Repo.get_visit_by_client_uuid(session, tenant_id, payload.client_uuid)

        now = datetime.now(timezone.utc)

        if visit is None:
            visit = StockVisit(
                id=uuid4(),
                tenant_id=tenant_id,
                customer_id=payload.customer_id,
                promoter_id=user.id,
                visit_type=payload.visit_type,
                client_uuid=payload.client_uuid,
                status=StockVisitStatus.DRAFT.value,
                no_products=payload.no_products,
                visited_at=payload.visited_at or now,
            )
        else:
            if visit.status == StockVisitStatus.EXPORTED.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Esta contagem já foi exportada e não pode mais ser alterada.",
                )
            if visit.promoter_id != user.id and not _is_admin(user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Esta contagem pertence a outro promotor.",
                )
            visit.visit_type = payload.visit_type
            visit.no_products = payload.no_products
            visit.visited_at = payload.visited_at or visit.visited_at or now

        if payload.submit:
            visit.status = StockVisitStatus.SUBMITTED.value
            visit.submitted_at = now

        visit = await Repo.save_visit(session, visit)

        await Repo.replace_items(
            session, visit.id,
            await MerchandisingService._build_items(
                session, tenant_id, visit.id,
                # "Não tem produtos aqui" é a contagem inteira: o que estivesse
                # digitado antes de marcar o quadrado não vai junto.
                [] if payload.no_products else payload.items,
            ),
        )

        # As datas coletadas NÃO são apagadas pelo "não tem produtos aqui": elas
        # descrevem o par (gôndola + estoque), e o lado vazio é justamente o que
        # joga todo o estoque para o outro lado.
        await Repo.replace_expiries(
            session, visit.id,
            await MerchandisingService._build_expiries(
                session, tenant_id, visit, payload.expiries
            ),
        )

        return await MerchandisingService.get_visit(session, tenant_id, visit.id)

    @staticmethod
    async def update_visit(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID,
        payload: StockVisitUpdate,
    ) -> StockVisitResponse:
        """Correção de uma contagem já enviada: troca as quantidades dos itens.

        Não mexe no status — a contagem continua enviada, só com outros números.
        """
        visit, _ = await MerchandisingService._load_editable_visit(
            session, tenant_id, user, visit_id
        )
        MerchandisingService._assert_not_empty(payload.no_products, payload.items)
        visit.no_products = payload.no_products

        await Repo.replace_items(
            session, visit.id,
            await MerchandisingService._build_items(
                session, tenant_id, visit.id,
                [] if payload.no_products else payload.items,
            ),
        )

        # `updated_at` só muda sozinho quando a própria linha da visita muda, e
        # aqui quem mudou foram os itens. Marcar na mão é o que registra que
        # esta contagem foi corrigida depois de enviada.
        visit.updated_at = datetime.now(timezone.utc)
        await Repo.save_visit(session, visit)

        return await MerchandisingService.get_visit(session, tenant_id, visit.id)

    @staticmethod
    async def _build_items(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID,
        inputs: list[StockVisitItemInput],
    ) -> list[StockVisitItem]:
        """Converte o que o promotor digitou (caixas + unidades) em linhas.

        A conversão para unidades é feita aqui, na hora de gravar, e não na
        planilha: assim o total já vale para o detalhe da visita e para a
        "contagem anterior" da próxima visita, sem repetir a regra em cada
        leitura.
        """
        sizes = await Repo.package_sizes(
            session, tenant_id, [item.product_id for item in inputs]
        )
        return [
            StockVisitItem(
                id=uuid4(),
                tenant_id=tenant_id,
                visit_id=visit_id,
                product_id=item.product_id,
                boxes=item.boxes,
                units=item.units,
                quantity=item.boxes * sizes.get(item.product_id, Decimal(1)) + item.units,
                unit_type=UnitType.UNIDADE.value,
            )
            for item in inputs
        ]

    @staticmethod
    async def _build_expiries(
        session: AsyncSession, tenant_id: UUID, visit: StockVisit,
        inputs: list[ProductExpiryInput],
    ) -> list[ProductExpiry]:
        """As datas digitadas pelo promotor → linhas da coleta.

        Mesma conversão da contagem (caixas viram unidades pelo `package_size` de
        hoje), pelo mesmo motivo: é na unidade convertida que a soma das datas
        fecha com o total contado.

        `collected_day` é o dia LOCAL da visita, e não o instante UTC: é por ele
        que a coleta se encaixa no meio da história do produto, no mesmo dia em
        que o par se formou.
        """
        if not inputs:
            return []

        sizes = await Repo.package_sizes(
            session, tenant_id, [linha.product_id for linha in inputs]
        )
        dia = consolidation.local_day(visit.visited_at or visit.submitted_at)

        return [
            ProductExpiry(
                id=uuid4(),
                tenant_id=tenant_id,
                customer_id=visit.customer_id,
                product_id=linha.product_id,
                promoter_id=visit.promoter_id,
                visit_id=visit.id,
                collected_day=date.fromisoformat(dia),
                expires_at=linha.expires_at,
                boxes=linha.boxes,
                units=linha.units,
                quantity=(
                    linha.boxes * sizes.get(linha.product_id, Decimal(1)) + linha.units
                ),
            )
            for linha in inputs
        ]

    @staticmethod
    async def submit_visit(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID
    ) -> StockVisitResponse:
        visit = await Repo.get_visit(session, tenant_id, visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")
        if visit.promoter_id != user.id and not _is_admin(user):
            raise HTTPException(status_code=403, detail="Contagem de outro promotor")

        visit.status = StockVisitStatus.SUBMITTED.value
        visit.submitted_at = datetime.now(timezone.utc)
        await Repo.save_visit(session, visit)
        return await MerchandisingService.get_visit(session, tenant_id, visit_id)

    # ── Leitura ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_visit(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> StockVisitResponse:
        row = await Repo.get_visit_detail(session, tenant_id, visit_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")

        visit, customer_name, promoter_name = row

        item_rows = await Repo.list_items(session, visit.id)
        items = [
            StockVisitItemResponse(
                id=item.id, product_id=item.product_id,
                product_name=product.name if product else None,
                boxes=item.boxes, units=item.units,
                quantity=item.quantity, unit_type=item.unit_type,
                expires_at=item.expires_at, notes=item.notes,
            )
            for item, product in item_rows
        ]

        coletadas = (await Repo.list_expiries_for_visits(session, [visit.id])).get(
            visit.id, []
        )
        expiries = [
            ProductExpiryResponse(
                id=linha.id, product_id=linha.product_id, product_name=nome,
                expires_at=linha.expires_at, boxes=linha.boxes,
                units=linha.units, quantity=linha.quantity,
            )
            for linha, nome in coletadas
        ]

        par = await MerchandisingService._pair_of(session, tenant_id, visit)

        return StockVisitResponse(
            id=visit.id, tenant_id=visit.tenant_id, customer_id=visit.customer_id,
            customer_name=customer_name,
            promoter_id=visit.promoter_id, promoter_name=promoter_name,
            visit_type=visit.visit_type, status=visit.status,
            no_products=visit.no_products,
            missing_side=par.missing if par else None,
            visited_at=visit.visited_at,
            submitted_at=visit.submitted_at, exported_at=visit.exported_at,
            notes=visit.notes, client_uuid=visit.client_uuid,
            items=items, items_count=len(items), expiries=expiries,
            created_at=visit.created_at, updated_at=visit.updated_at,
        )

    @staticmethod
    async def list_visits(
        session: AsyncSession, tenant_id: UUID, **filters
    ) -> tuple[list[StockVisitResponse], int]:
        rows, total = await Repo.list_visits(session, tenant_id, **filters)
        faltando = await MerchandisingService._missing_sides(
            session, tenant_id, [v for v, _, _, _ in rows]
        )
        visits = [
            StockVisitResponse(
                id=v.id, tenant_id=v.tenant_id, customer_id=v.customer_id,
                customer_name=c_name,
                promoter_id=v.promoter_id, promoter_name=p_name,
                visit_type=v.visit_type, status=v.status,
                no_products=v.no_products,
                missing_side=faltando.get(v.id),
                visited_at=v.visited_at,
                submitted_at=v.submitted_at, exported_at=v.exported_at,
                notes=v.notes, client_uuid=v.client_uuid,
                items=[], items_count=count,
                created_at=v.created_at, updated_at=v.updated_at,
            )
            for v, c_name, p_name, count in rows
        ]
        return visits, total

    @staticmethod
    async def list_visit_pairs(
        session: AsyncSession, tenant_id: UUID,
        promoter_id: Optional[UUID] = None, customer_id: Optional[UUID] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[VisitPairResponse], int]:
        """A lista do administrador: uma linha por cliente/promotor/dia.

        O promotor conta gôndola e estoque separadamente — são duas visitas no
        banco, e continuam sendo. Mas quem administra recebe uma planilha só, com
        os dois lugares lado a lado, e via duas linhas na tela para a mesma ida à
        loja. Agora a tela conta a mesma história que a planilha.

        A paginação é feita aqui, sobre os pares, e não no SQL sobre as visitas.
        Não é preguiça: o par se forma pelo DIA LOCAL, que só existe em Python
        (`consolidation.local_day`), e um LIMIT aplicado às visitas partiria pares
        ao meio — a gôndola no fim de uma página, o estoque no começo da outra,
        as duas metades marcadas como incompletas.

        Como na planilha, a janela consultada é um dia maior de cada lado e o
        recorte final é por dia local: é isso que faz "até 19/08" incluir a
        contagem das 21h do dia 19, que em UTC já é dia 20.
        """
        visitas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[customer_id] if customer_id else None,
            promoter_ids=[promoter_id] if promoter_id else None,
            date_from=date_from - timedelta(days=1) if date_from else None,
            date_to=date_to + timedelta(days=1) if date_to else None,
        )

        primeiro, ultimo = consolidation.day_bounds(date_from, date_to)
        pares = [
            par for par in consolidation.group_visits(visitas).values()
            if consolidation.within_days(par, primeiro, ultimo)
            and (not status or par.status == status)
        ]

        pagina = consolidation.sort_recent_first(pares)[offset : offset + limit]
        return [_pair_response(par) for par in pagina], len(pares)

    # ── Evolução do estoque do cliente ────────────────────────────────────

    @staticmethod
    async def _stock_series(
        session: AsyncSession, tenant_id: UUID, days: int,
        customer_id: Optional[UUID] = None,
    ) -> tuple[list[evolution.Series], str, str]:
        """As contagens da janela, já viradas em história por produto.

        Duas leituras e nenhum SQL novo: as visitas saem da mesma consulta que
        forma o par da planilha, e os itens da mesma que a alimenta — inclusive
        o `package_size` de hoje, que é o que mantém a série inteira na mesma
        unidade mesmo se o cadastro do produto tiver sido corrigido no meio.
        """
        hoje = consolidation.local_day(datetime.now(timezone.utc))
        primeiro = (date.fromisoformat(hoje) - timedelta(days=days - 1)).isoformat()

        desde, _ = consolidation.day_window(primeiro)
        _, ate = consolidation.day_window(hoje)

        visitas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[customer_id] if customer_id else None,
            date_from=desde, date_to=ate,
        )
        itens = await Repo.list_export_items(
            session, tenant_id, [v.id for v in visitas]
        )
        return evolution.build_series(visitas, itens), primeiro, hoje

    @staticmethod
    async def stock_insights(
        session: AsyncSession, tenant_id: UUID, days: int = 90, limit: int = 20,
    ) -> StockInsightsResponse:
        """O que mudou no estoque dos clientes na janela pedida."""
        series, primeiro, hoje = await MerchandisingService._stock_series(
            session, tenant_id, days
        )

        parados = evolution.stalled(series)
        sumiram, voltaram = evolution.moved(series)
        faltas = evolution.shelf_gap(series)

        return StockInsightsResponse(
            window_days=days,
            from_day=primeiro,
            to_day=hoje,
            customers=[
                StockCustomerResponse(**asdict(c)) for c in evolution.customers(series)
            ],
            stalled=[StalledProductResponse(**asdict(p)) for p in parados[:limit]],
            gone=[MovedProductResponse(**asdict(m)) for m in sumiram[:limit]],
            returned=[MovedProductResponse(**asdict(m)) for m in voltaram[:limit]],
            shelf_gap=[ShelfGapResponse(**asdict(f)) for f in faltas[:limit]],
            stalled_total=len(parados),
            gone_total=len(sumiram),
            returned_total=len(voltaram),
            shelf_gap_total=len(faltas),
        )

    @staticmethod
    async def stock_history(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID,
        product_id: Optional[UUID] = None, days: int = 90,
    ) -> StockHistoryResponse:
        """A linha do tempo de um cliente — de um produto, ou da loja inteira."""
        series, _, _ = await MerchandisingService._stock_series(
            session, tenant_id, days, customer_id=customer_id
        )
        pontos = evolution.history(series, customer_id, product_id)

        # Nome do produto só existe se ele foi contado ali dentro da janela.
        do_produto = next(
            (s for s in series if product_id and s.product_id == product_id), None
        )
        return StockHistoryResponse(
            customer_id=customer_id,
            customer_name=next((s.customer_name for s in series), None),
            product_id=product_id,
            product_name=do_produto.product_name if do_produto else None,
            window_days=days,
            points=[StockPointResponse(**asdict(p)) for p in pontos],
        )

    # ── O par gôndola + estoque ───────────────────────────────────────────

    @staticmethod
    async def _pair_of(
        session: AsyncSession, tenant_id: UUID, visit
    ) -> Optional[consolidation.Pair]:
        """O par a que esta contagem pertence — ela e a do outro lugar, no mesmo
        cliente, mesmo promotor, mesmo dia.

        Devolve None para rascunho: contagem que o promotor ainda não fechou não
        entra em par nenhum, e dizer que "falta o estoque" seria mentira.
        """
        if visit.status == StockVisitStatus.DRAFT.value:
            return None

        dia = consolidation.local_day(visit.visited_at)
        inicio, fim = consolidation.day_window(dia) if dia else (None, None)

        candidatas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[visit.customer_id], promoter_ids=[visit.promoter_id],
            date_from=inicio, date_to=fim,
        )
        return consolidation.group_visits(candidatas).get(consolidation.group_key(visit))

    @staticmethod
    async def _missing_sides(
        session: AsyncSession, tenant_id: UUID, visits: list
    ) -> dict[UUID, Optional[str]]:
        """{visit_id: lado que falta} para uma página inteira da lista.

        Uma consulta só, limitada aos clientes e promotores que aparecem na
        página e à janela de dias que ela cobre — e não uma por linha.
        """
        if not visits:
            return {}

        momentos = [v.visited_at for v in visits if v.visited_at]
        inicio = min(momentos) - timedelta(days=1) if momentos else None
        fim = max(momentos) + timedelta(days=1) if momentos else None

        candidatas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=list({v.customer_id for v in visits}),
            promoter_ids=list({v.promoter_id for v in visits}),
            date_from=inicio, date_to=fim,
        )
        return consolidation.missing_side_by_visit(candidatas)

    # ── Planilha consolidada ──────────────────────────────────────────────

    @staticmethod
    async def consolidated_export(
        session: AsyncSession, tenant_id: UUID,
        promoter_id: Optional[UUID] = None, customer_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    ) -> tuple[list, list[UUID]]:
        """Linhas da planilha do período + as contagens que entraram nela.

        A janela consultada é um dia maior de cada lado do filtro, e o recorte
        final é feito por DIA LOCAL: sem isso, "de 19 a 19/08" traria a contagem
        das 21h do dia 18 (que em UTC já é dia 19) e perderia a das 21h do dia
        19 — e, pior, poderia cortar um par no meio.
        """
        visitas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[customer_id] if customer_id else None,
            promoter_ids=[promoter_id] if promoter_id else None,
            date_from=date_from - timedelta(days=1) if date_from else None,
            date_to=date_to + timedelta(days=1) if date_to else None,
        )

        primeiro, ultimo = consolidation.day_bounds(date_from, date_to)
        pares = [
            par for par in consolidation.group_visits(visitas).values()
            if par.complete and consolidation.within_days(par, primeiro, ultimo)
        ]

        itens = await Repo.list_export_items(
            session, tenant_id, [vid for par in pares for vid in par.visit_ids]
        )
        return consolidation.build_rows(pares, itens)

    @staticmethod
    async def consolidated_export_for_visit(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> tuple[list, list[UUID]]:
        """A planilha de uma contagem é a planilha do par dela — nunca de um
        lado só. Sem o par, o administrador recebe o motivo em vez do arquivo."""
        row = await Repo.get_visit_detail(session, tenant_id, visit_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")

        visit = row[0]
        par = await MerchandisingService._pair_of(session, tenant_id, visit)

        if par is None or not par.complete:
            faltando = par.missing if par else visit.visit_type
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A contagem de "
                    f"{consolidation.SIDE_LABEL.get(faltando, faltando)} deste "
                    "cliente ainda não chegou. A planilha só sai com as duas."
                ),
            )

        itens = await Repo.list_export_items(session, tenant_id, par.visit_ids)
        return consolidation.build_rows([par], itens)

    # ── Guarda de acesso ──────────────────────────────────────────────────

    @staticmethod
    def _assert_not_empty(no_products: bool, items: list) -> None:
        """Contagem fechada tem que dizer alguma coisa: ou os produtos que o
        promotor encontrou, ou o quadrado de que ali não há produto nenhum.

        Uma contagem vazia sem esse quadrado fecharia o par e sairia na planilha
        como se o cliente não tivesse mix — indistinguível de um engano.
        """
        if not no_products and not items:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Contagem vazia: preencha ao menos um produto ou marque "
                    "que não há produtos neste lugar."
                ),
            )


    @staticmethod
    async def _load_editable_visit(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID
    ) -> tuple[StockVisit, Optional[str]]:
        """Visita que este usuário ainda pode alterar — ou o erro que diz por quê.

        Depois de exportada a contagem já virou planilha na mão do administrador:
        mudar o número aqui faria o app discordar do que ele baixou.
        """
        row = await Repo.get_visit_detail(session, tenant_id, visit_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")

        visit, customer_name, _ = row
        if visit.promoter_id != user.id and not _is_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta contagem pertence a outro promotor.",
            )
        if visit.status == StockVisitStatus.EXPORTED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta contagem já foi processada pelo administrador e não pode mais ser alterada.",
            )
        return visit, customer_name

    @staticmethod
    async def _assert_can_access_customer(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID
    ) -> None:
        if _is_admin(user):
            return
        if not await Repo.is_customer_assigned(session, tenant_id, user.id, customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este cliente não está atribuído a você.",
            )
